#!/usr/bin/env python3
"""
PX4 真机平台

适配 PX4 真实无人机
"""
import rospy
import threading
import time
import tf.transformations as tft
from nav_msgs.msg import Odometry
from mavros_msgs.msg import State
from geometry_msgs.msg import PoseStamped
from std_msgs.msg import String

from .base_platform import BasePlatform


class PX4RealPlatform(BasePlatform):
    """PX4 真机平台实现"""
    
    def __init__(self, config):
        super().__init__(config)
        
        # 状态
        self.flight_status = "IDLE"
        self.status_lock = threading.Lock()
        self.odom_received = False
        self.state_received = False
        
        # 参数
        self.takeoff_height = config.get('takeoff_height', 1.5)
        self.odom_topic = config.get('odom_topic', '/mavros/local_position/odom')
        
        rospy.loginfo(f"✅ PX4 真机平台初始化")
    
    def init_ros(self):
        """初始化 ROS 订阅和发布"""
        # 发布者
        self.setpoint_pub = rospy.Publisher('/mavros/setpoint_position/local', PoseStamped, queue_size=10)
        self.status_pub = rospy.Publisher('/agent/status', String, queue_size=10)
        
        # 订阅者
        rospy.loginfo(f"订阅里程计: {self.odom_topic}")
        rospy.Subscriber(self.odom_topic, Odometry, self._on_odom)
        rospy.Subscriber('/mavros/state', State, self._on_mavros_state)
        
        # 启动 setpoint 发布线程（OFFBOARD 模式需要持续发布）
        self.setpoint_thread = threading.Thread(target=self._setpoint_publish_loop, daemon=True)
        self.setpoint_thread.start()
    
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
    
    def _setpoint_publish_loop(self):
        """持续发布 setpoint（OFFBOARD 模式需要）"""
        rate = rospy.Rate(20)  # 20Hz
        while not rospy.is_shutdown():
            if hasattr(self, 'current_setpoint') and self.current_setpoint is not None:
                self.setpoint_pub.publish(self.current_setpoint)
            rate.sleep()
    
    def _create_setpoint(self, x, y, z, yaw=0.0):
        """创建 setpoint"""
        setpoint = PoseStamped()
        setpoint.header.stamp = rospy.Time.now()
        setpoint.header.frame_id = "map"
        setpoint.pose.position.x = x
        setpoint.pose.position.y = y
        setpoint.pose.position.z = z
        
        # 将 yaw 转换为四元数
        q = tft.quaternion_from_euler(0, 0, yaw)
        setpoint.pose.orientation.x = q[0]
        setpoint.pose.orientation.y = q[1]
        setpoint.pose.orientation.z = q[2]
        setpoint.pose.orientation.w = q[3]
        
        return setpoint
    
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
        """起飞到指定高度（真机使用 MAVROS）"""
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
            
            rospy.loginfo(f"🚁 起飞到 {height}m (真机模式)")
            self._set_status("TAKEOFF")
            
            # 真机：使用 MAVROS 的 setpoint
            # 先发送当前位置的 setpoint，然后逐渐增加高度
            current_pos = self.odom.pose.pose.position
            
            # 设置目标高度
            self.current_setpoint = self._create_setpoint(
                current_pos.x, current_pos.y, height, 0.0
            )
            
            # 等待到达目标高度
            rospy.loginfo("等待到达目标高度...")
            rate = rospy.Rate(10)
            timeout = rospy.Time.now() + rospy.Duration(30.0)
            
            while not rospy.is_shutdown():
                if rospy.Time.now() > timeout:
                    rospy.logwarn("起飞超时")
                    break
                
                # 检查是否到达目标高度 (0.3m 误差，真机误差较大)
                if self.odom and abs(self.odom.pose.pose.position.z - height) < 0.3:
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
        """降落到地面（真机使用 MAVROS）"""
        try:
            status = self._get_status()
            if status == "IDLE":
                return {"success": True, "message": "已在地面"}
            
            if self.odom is None:
                return {"success": False, "message": "里程计数据未就绪"}
            
            rospy.loginfo("🛬 降落 (真机模式)")
            self._set_status("LAND")
            
            # 真机：逐渐降低高度
            current_pos = self.odom.pose.pose.position
            
            # 设置目标高度为 0
            self.current_setpoint = self._create_setpoint(
                current_pos.x, current_pos.y, 0.0, 0.0
            )
            
            # 等待接近地面
            rate = rospy.Rate(10)
            timeout = rospy.Time.now() + rospy.Duration(60.0)
            
            while not rospy.is_shutdown():
                if rospy.Time.now() > timeout:
                    rospy.logwarn("降落超时")
                    break
                
                # 检查是否接近地面
                if self.odom and self.odom.pose.pose.position.z < 0.2:
                    break
                
                rate.sleep()
            
            self._set_status("IDLE")
            return {"success": True, "message": "降落成功"}
                
        except Exception as e:
            return {"success": False, "message": f"错误: {e}"}
    
    def set_goal(self, x, y, z, yaw):
        """设置目标点（真机使用 MAVROS setpoint）"""
        try:
            status = self._get_status()
            if status not in ["HOVER", "NAVIGATE"]:
                return {
                    "success": False,
                    "message": f"当前状态 {status}，需要先起飞到 HOVER 状态"
                }
            
            # 创建并发布 setpoint
            self.current_setpoint = self._create_setpoint(x, y, z, yaw)
            
            self._set_status("NAVIGATE")
            
            rospy.loginfo(f"🎯 设置目标: ({x:.2f}, {y:.2f}, {z:.2f}), yaw={yaw:.2f} (真机模式)")
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
