#!/usr/bin/env python3
"""
Agent 工具接口 - 使用 CERLAB autonomous_flight 导航系统 (Non-PX4 仿真器)

架构:
    tools.py ──Topic──▶ navigation_node ──▶ tracking_controller ──▶ 仿真器

话题 (Non-PX4 仿真器):
    - /CERLAB/quadcopter/odom: 里程计
    - /CERLAB/quadcopter/cmd_acc: 加速度控制指令 (tracking_controller)
    - /CERLAB/quadcopter/setpoint_pose: 位置控制指令 (直接控制)
    - /move_base_simple/goal: 导航目标点 → navigation_node
"""

import rospy
from std_msgs.msg import String
from geometry_msgs.msg import PoseStamped
from nav_msgs.msg import Odometry
import tf.transformations as tft
import json
import threading
import math


class AgentTools:
    """Agent 工具接口 - 使用 CERLAB autonomous_flight (Non-PX4)"""
    
    def __init__(self):
        # 状态
        self.odom = None
        self.flight_status = "IDLE"  # IDLE, TAKEOFF, HOVER, NAVIGATE, LAND
        self.status_lock = threading.Lock()
        self.odom_received = False
        
        # 参数
        self.takeoff_height = rospy.get_param('autonomous_flight/takeoff_height', 1.5)
        self.odom_topic = rospy.get_param('~odom_topic', '/CERLAB/quadcopter/odom')
        
        # 发布者
        self.goal_pub = rospy.Publisher('/move_base_simple/goal', PoseStamped, queue_size=1)
        self.pose_pub = rospy.Publisher('/CERLAB/quadcopter/setpoint_pose', PoseStamped, queue_size=10)
        self.status_pub = rospy.Publisher('/agent/status', String, queue_size=10)
        
        # 订阅者
        rospy.loginfo(f"订阅里程计话题: {self.odom_topic}")
        rospy.Subscriber(self.odom_topic, Odometry, self._on_odom)
        
        # 路径记录
        self.path_record = []
        
        # 工具列表
        self.tools = self._init_tools()
        
        # 等待数据就绪
        self._wait_for_data()
    
    def _wait_for_data(self):
        """等待里程计数据"""
        rospy.loginfo("等待 Odom 数据...")
        rate = rospy.Rate(10)
        timeout = rospy.Time.now() + rospy.Duration(30.0)
        while not rospy.is_shutdown() and not self.odom_received:
            if rospy.Time.now() > timeout:
                rospy.logwarn("⚠️ 等待数据超时，继续运行...")
                break
            rate.sleep()
        if self.odom_received:
            rospy.loginfo("✅ Odom 数据就绪")
    
    def _on_odom(self, msg):
        self.odom = msg
        if not self.odom_received:
            self.odom_received = True
        # 自动更新飞行状态
        if self.odom.pose.pose.position.z > 0.5:
            current_status = self._get_status()
            if current_status == "IDLE":
                self._set_status("HOVER")
    
    def _set_status(self, status):
        with self.status_lock:
            self.flight_status = status
        self.status_pub.publish(status)
    
    def _get_status(self):
        with self.status_lock:
            return self.flight_status
    
    def _init_tools(self):
        return [
            {
                "name": "takeoff", 
                "description": "起飞到指定高度。参数: {'height': float}，例如 {'height': 2.0}，默认使用配置高度", 
                "func": self.takeoff
            },
            {
                "name": "land", 
                "description": "降落。无参数。", 
                "func": self.land
            },
            {
                "name": "set_goal", 
                "description": "设置导航目标点。参数: {'x': float, 'y': float, 'z': float}。navigation_node 会自动规划避障轨迹。", 
                "func": self.set_goal
            },
            {
                "name": "get_current_position", 
                "description": "获取当前位置。无参数。", 
                "func": self.get_current_position
            },
            {
                "name": "get_flight_status", 
                "description": "获取飞行状态。无参数。返回: IDLE/HOVER/NAVIGATE 等", 
                "func": self.get_flight_status
            },
            {
                "name": "describe_scene", 
                "description": "调用视觉模型描述前方场景。无参数。", 
                "func": self.describe_scene
            },
            {
                "name": "get_detected_objects", 
                "description": "获取检测到的物体列表。无参数。", 
                "func": self.get_detected_objects
            },
        ]
    
    def get_tools_description(self):
        return json.dumps([{"name": t["name"], "description": t["description"]} for t in self.tools], 
                         indent=2, ensure_ascii=False)
    
    def get_status_dict(self):
        """返回字典格式的状态"""
        state = {"x": 0.0, "y": 0.0, "z": 0.0, "yaw": 0.0, "status": "Unknown"}
        
        if self.odom:
            p = self.odom.pose.pose.position
            q = self.odom.pose.pose.orientation
            _, _, yaw = tft.euler_from_quaternion([q.x, q.y, q.z, q.w])
            state.update({
                "x": round(p.x, 2),
                "y": round(p.y, 2),
                "z": round(p.z, 2),
                "yaw": round(yaw * 180.0 / math.pi, 1)
            })
        
        state["status"] = self._get_status()
        return state

    # ==================== 工具实现 ====================
    
    def takeoff(self, args=None):
        """
        起飞 - 发布目标位置到 CERLAB/quadcopter/setpoint_pose
        Non-PX4 仿真器会直接响应位置指令
        """
        height = self.takeoff_height
        try:
            if isinstance(args, dict):
                height = float(args.get('height', self.takeoff_height))
            elif isinstance(args, (float, int)):
                height = float(args)
            
            if not 0.5 <= height <= 20.0:
                return {"result": f"高度 {height}m 超出允许范围 (0.5-20m)"}
            
            # 检查是否已经在空中
            if self.odom and self.odom.pose.pose.position.z > 0.5:
                self._set_status("HOVER")
                return {"result": f"已在空中，当前高度 {self.odom.pose.pose.position.z:.2f}m，状态: HOVER"}
            
            if self.odom is None:
                return {"result": "里程计数据未就绪"}
            
            rospy.loginfo(f"🚁 起飞到 {height}m")
            self._set_status("TAKEOFF")
            
            # 设置目标位置
            pose_tgt = PoseStamped()
            pose_tgt.header.frame_id = "map"
            pose_tgt.pose.position.x = self.odom.pose.pose.position.x
            pose_tgt.pose.position.y = self.odom.pose.pose.position.y
            pose_tgt.pose.position.z = height
            pose_tgt.pose.orientation = self.odom.pose.pose.orientation
            
            # 持续发布目标位置直到到达
            rate = rospy.Rate(30)
            timeout = rospy.Time.now() + rospy.Duration(30.0)
            
            while not rospy.is_shutdown():
                if rospy.Time.now() > timeout:
                    rospy.logwarn("起飞超时")
                    break
                
                pose_tgt.header.stamp = rospy.Time.now()
                self.pose_pub.publish(pose_tgt)
                
                # 检查是否到达目标高度 (0.1m 误差)
                if self.odom and abs(self.odom.pose.pose.position.z - height) < 0.1:
                    break
                
                rate.sleep()
            
            # 悬停稳定
            rospy.loginfo("悬停稳定中...")
            start_time = rospy.Time.now()
            while not rospy.is_shutdown():
                if (rospy.Time.now() - start_time).to_sec() >= 2.0:
                    break
                pose_tgt.header.stamp = rospy.Time.now()
                self.pose_pub.publish(pose_tgt)
                rate.sleep()
            
            self._set_status("HOVER")
            current_z = self.odom.pose.pose.position.z if self.odom else height
            rospy.loginfo("✅ 起飞成功!")
            return {"result": f"起飞成功，当前高度 {current_z:.2f}m，状态: HOVER"}
                
        except Exception as e:
            self._set_status("IDLE")
            return {"result": f"错误: {e}"}
    
    def land(self, _=None):
        """
        降落 - 发布高度为0的目标点
        """
        try:
            status = self._get_status()
            if status == "IDLE":
                return {"result": "已在地面"}
            
            if self.odom is None:
                return {"result": "里程计数据未就绪"}
            
            rospy.loginfo("🛬 降落")
            self._set_status("LAND")
            
            # 发布降落目标点
            pose = PoseStamped()
            pose.header.frame_id = "map"
            pose.pose.position.x = self.odom.pose.pose.position.x
            pose.pose.position.y = self.odom.pose.pose.position.y
            pose.pose.position.z = 0.0
            pose.pose.orientation = self.odom.pose.pose.orientation
            
            # 持续发布降落目标
            rate = rospy.Rate(30)
            timeout = rospy.Time.now() + rospy.Duration(60.0)
            while not rospy.is_shutdown():
                if rospy.Time.now() > timeout:
                    rospy.logwarn("降落超时")
                    break
                
                # 更新当前 xy 位置，保持 z=0
                if self.odom:
                    pose.pose.position.x = self.odom.pose.pose.position.x
                    pose.pose.position.y = self.odom.pose.pose.position.y
                
                pose.header.stamp = rospy.Time.now()
                self.pose_pub.publish(pose)
                
                # 检查是否接近地面
                if self.odom and self.odom.pose.pose.position.z < 0.15:
                    break
                
                rate.sleep()
            
            self._set_status("IDLE")
            return {"result": "降落成功"}
                
        except Exception as e:
            return {"result": f"错误: {e}"}
    
    def set_goal(self, args):
        """
        设置导航目标 - 发布到 /move_base_simple/goal
        由 navigation_node 的 clickCB() 接收，触发轨迹规划
        """
        try:
            if not isinstance(args, dict):
                return {"result": "参数格式错误，需要 {'x': float, 'y': float, 'z': float}"}
            
            x = float(args.get('x', 0))
            y = float(args.get('y', 0))
            z = float(args.get('z', self.takeoff_height))
            
            status = self._get_status()
            if status not in ["HOVER", "NAVIGATE"]:
                return {"result": f"当前状态 {status}，需要先起飞到 HOVER 状态"}
            
            self.path_record.append([x, y, z])
            
            # 发布目标点到 /move_base_simple/goal
            pose = PoseStamped()
            pose.header.stamp = rospy.Time.now()
            pose.header.frame_id = "map"
            pose.pose.position.x = x
            pose.pose.position.y = y
            pose.pose.position.z = z
            pose.pose.orientation.w = 1.0
            
            self.goal_pub.publish(pose)
            self._set_status("NAVIGATE")
            
            rospy.loginfo(f"🎯 设置目标: ({x}, {y}, {z})")
            return {"result": f"已设置导航目标 ({x}, {y}, {z})，navigation_node 开始规划轨迹"}
            
        except Exception as e:
            return {"result": f"错误: {e}"}
    
    def get_current_position(self, _=None):
        """获取当前位置"""
        try:
            if self.odom is None:
                return {"result": "无位置数据"}
            
            p = self.odom.pose.pose.position
            q = self.odom.pose.pose.orientation
            _, _, yaw = tft.euler_from_quaternion([q.x, q.y, q.z, q.w])
            
            return {"result": f"x={p.x:.2f}, y={p.y:.2f}, z={p.z:.2f}m, yaw={yaw*180/math.pi:.0f}°"}
        except Exception as e:
            return {"result": f"错误: {e}"}
    
    def get_flight_status(self, _=None):
        """获取飞行状态"""
        status = self._get_status()
        pos_info = ""
        if self.odom:
            p = self.odom.pose.pose.position
            pos_info = f", 位置: ({p.x:.1f}, {p.y:.1f}, {p.z:.1f})"
        return {"result": f"状态: {status}{pos_info}"}
    
    def describe_scene(self, _=None):
        """描述场景 (占位)"""
        return {"result": "仿真场景：前方空旷区域"}

    def get_detected_objects(self, _=None):
        """获取检测物体 (占位)"""
        return {"result": "未检测到物体"}
    
    # ==================== 工具调用接口 ====================
    
    def call_tool(self, name, args=None):
        """通过名称调用工具"""
        for tool in self.tools:
            if tool["name"] == name:
                return tool["func"](args)
        return {"result": f"未知工具: {name}"}
