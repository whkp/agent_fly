#!/usr/bin/env python3
"""
PX4 仿真平台

适配 PX4 仿真环境（Gazebo）
"""
import rospy
import threading
import time
import tf.transformations as tft
from nav_msgs.msg import Odometry
from mavros_msgs.msg import State
from quadrotor_msgs.msg import PositionCommand, TakeoffLand
from std_msgs.msg import String

from .base_platform import BasePlatform


class PX4SimPlatform(BasePlatform):
    """PX4 仿真平台实现"""
    
    def __init__(self, config):
        super().__init__(config)
        
        # 状态
        self.flight_status = "IDLE"
        self.status_lock = threading.Lock()
        self.odom_received = False
        self.state_received = False
        
        # 当前目标点
        self.current_goal = None
        self.goal_lock = threading.Lock()
        
        # 参数
        self.takeoff_height = config.get('takeoff_height', 1.5)
        self.odom_topic = config.get('odom_topic', '/vins_fusion/imu_propagate')
        self.cmd_topic = config.get('cmd_topic', '/position_cmd')
        
        rospy.loginfo(f"✅ PX4 仿真平台初始化")
    
    def init_ros(self):
        """初始化 ROS 订阅和发布"""
        # 发布者
        self.cmd_pub = rospy.Publisher(self.cmd_topic, PositionCommand, queue_size=10)
        self.takeoff_land_pub = rospy.Publisher('/px4ctrl/takeoff_land', TakeoffLand, queue_size=10)
        self.status_pub = rospy.Publisher('/agent/status', String, queue_size=10)
        
        # 订阅者
        rospy.loginfo(f"订阅里程计: {self.odom_topic}")
        rospy.Subscriber(self.odom_topic, Odometry, self._on_odom)
        rospy.Subscriber('/mavros/state', State, self._on_mavros_state)
        
        # 启动命令发布线程
        self.cmd_thread = threading.Thread(target=self._cmd_publish_loop, daemon=True)
        self.cmd_thread.start()
    
    def _on_odom(self, msg):
        """里程计回调"""
        self.odom = msg
        if not self.odom_received:
            self.odom_received = True
        if self.odom.pose.pose.position.z > 0.5:
            if self._get_status() == "IDLE":
                self._set_status("HOVER")
    
    def _on_mavros_state(self, msg):
        """MAVROS 状态回调"""
        self.mavros_state = msg
        if not self.state_received:
            self.state_received = True
    
    def _cmd_publish_loop(self):
        """持续发布目标点"""
        rate = rospy.Rate(30)
        while not rospy.is_shutdown():
            with self.goal_lock:
                if self.current_goal is not None:
                    self.cmd_pub.publish(self.current_goal)
            rate.sleep()
    
    def _create_position_command(self, x, y, z, yaw=0.0, vx=0.0, vy=0.0, vz=0.0):
        """创建位置命令"""
        cmd = PositionCommand()
        cmd.header.stamp = rospy.Time.now()
        cmd.header.frame_id = "map"
        cmd.position.x = x
        cmd.position.y = y
        cmd.position.z = z
        cmd.velocity.x = vx
        cmd.velocity.y = vy
        cmd.velocity.z = vz
        cmd.acceleration.x = 0.0
        cmd.acceleration.y = 0.0
        cmd.acceleration.z = 0.0
        cmd.yaw = yaw
        cmd.yaw_dot = 0.0
        cmd.kx = [0.0, 0.0, 0.0]
        cmd.kv = [0.0, 0.0, 0.0]
        return cmd
    
    def _set_current_goal(self, cmd):
        with self.goal_lock:
            self.current_goal = cmd
    
    def _clear_current_goal(self):
        with self.goal_lock:
            self.current_goal = None
    
    def _get_status(self):
        with self.status_lock:
            return self.flight_status
    
    def _set_status(self, status):
        with self.status_lock:
            self.flight_status = status
        self.status_pub.publish(status)
    
    def _is_data_ready(self):
        """检查数据是否就绪"""
        return self.odom_received and self.state_received
    
    # 实现抽象方法
    
    def takeoff(self, height):
        """起飞到指定高度"""
        try:
            # 检查是否已经在空中
            if self.odom and self.odom.pose.pose.position.z > 0.5:
                self._set_status("HOVER")
                return {
                    "success": True,
                    "message": f"已在空中，当前高度 {self.odom.pose.pose.position.z:.2f}m"
                }
            
            if self.odom is None:
                return {"success": False, "message": "里程计数据未就绪"}
            
            rospy.loginfo(f"🚁 起飞到 {height}m")
            self._set_status("TAKEOFF")
            
            # 发布起飞命令
            takeoff_msg = TakeoffLand()
            takeoff_msg.takeoff_land_cmd = TakeoffLand.TAKEOFF
            takeoff_msg.header.stamp = rospy.Time.now()
            
            # 持续发布起飞命令
            for _ in range(10):
                self.takeoff_land_pub.publish(takeoff_msg)
                rospy.sleep(0.1)
            
            # 设置目标高度位置
            if self.odom:
                cmd = self._create_position_command(
                    x=self.odom.pose.pose.position.x,
                    y=self.odom.pose.pose.position.y,
                    z=height,
                    yaw=0.0
                )
                self._set_current_goal(cmd)
            
            # 等待到达目标高度
            rospy.loginfo("等待到达目标高度...")
            rate = rospy.Rate(10)
            timeout = rospy.Time.now() + rospy.Duration(30.0)
            
            while not rospy.is_shutdown():
                if rospy.Time.now() > timeout:
                    rospy.logwarn("起飞超时")
                    break
                
                # 检查是否到达目标高度 (0.2m 误差)
                if self.odom and abs(self.odom.pose.pose.position.z - height) < 0.2:
                    break
                
                rate.sleep()
            
            self._set_status("HOVER")
            current_z = self.odom.pose.pose.position.z if self.odom else height
            rospy.loginfo("✅ 起飞成功!")
            return {
                "success": True,
                "message": f"起飞成功，当前高度 {current_z:.2f}m"
            }
                
        except Exception as e:
            self._set_status("IDLE")
            return {"success": False, "message": f"错误: {e}"}
    
    def land(self):
        """降落到地面"""
        try:
            status = self._get_status()
            if status == "IDLE":
                return {"success": True, "message": "已在地面"}
            
            if self.odom is None:
                return {"success": False, "message": "里程计数据未就绪"}
            
            rospy.loginfo("🛬 降落")
            self._set_status("LAND")
            
            # 清除当前目标
            self._clear_current_goal()
            
            # 发布降落命令
            land_msg = TakeoffLand()
            land_msg.takeoff_land_cmd = TakeoffLand.LAND
            land_msg.header.stamp = rospy.Time.now()
            
            # 持续发布降落命令
            rate = rospy.Rate(10)
            timeout = rospy.Time.now() + rospy.Duration(60.0)
            
            while not rospy.is_shutdown():
                if rospy.Time.now() > timeout:
                    rospy.logwarn("降落超时")
                    break
                
                self.takeoff_land_pub.publish(land_msg)
                
                # 检查是否接近地面
                if self.odom and self.odom.pose.pose.position.z < 0.15:
                    break
                
                rate.sleep()
            
            self._set_status("IDLE")
            return {"success": True, "message": "降落成功"}
                
        except Exception as e:
            return {"success": False, "message": f"错误: {e}"}
    
    def set_goal(self, x, y, z, yaw):
        """设置目标点"""
        try:
            status = self._get_status()
            if status not in ["HOVER", "NAVIGATE"]:
                return {
                    "success": False,
                    "message": f"当前状态 {status}，需要先起飞到 HOVER 状态"
                }
            
            # 创建并发布位置命令
            cmd = self._create_position_command(x, y, z, yaw)
            self._set_current_goal(cmd)
            
            self._set_status("NAVIGATE")
            
            rospy.loginfo(f"🎯 设置目标: ({x:.2f}, {y:.2f}, {z:.2f}), yaw={yaw:.2f}")
            return {
                "success": True,
                "message": f"已设置目标点 ({x:.2f}, {y:.2f}, {z:.2f})"
            }
            
        except Exception as e:
            return {"success": False, "message": f"错误: {e}"}
    
    def get_current_position(self):
        """获取当前位置"""
        try:
            if self.odom is None:
                return None
            
            p = self.odom.pose.pose.position
            q = self.odom.pose.pose.orientation
            _, _, yaw = tft.euler_from_quaternion([q.x, q.y, q.z, q.w])
            
            return {
                "x": round(p.x, 2),
                "y": round(p.y, 2),
                "z": round(p.z, 2),
                "yaw": round(yaw, 3)
            }
        except Exception as e:
            rospy.logerr(f"获取位置失败: {e}")
            return None
    
    def get_flight_status(self):
        """获取飞行状态"""
        return self._get_status()
