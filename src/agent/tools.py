#!/usr/bin/env python3
"""
Agent 工具接口 - 支持 PX4（真机）和 CERLAB（仿真）两种模式

架构:
    tools.py ──Topic──▶ navigation_node.py ──▶ 避障导航

模式:
    PX4（真机）:
        - /mavros/local_position/odom: 里程计
        - /mavros/setpoint_position/local: 位置控制
        - /move_base_simple/goal: 导航目标点 → navigation_node
    
    CERLAB（仿真）:
        - /CERLAB/quadcopter/odom: 里程计
        - /CERLAB/quadcopter/setpoint_pose: 位置控制
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
from typing import Dict, Any, Callable, List


# ==============================================================================
# 工具基类（面向对象封装）
# ==============================================================================
class Tool:
    """工具基类 - 面向对象封装工具定义"""
    def __init__(self, name: str, description: str, func: Callable):
        self.name = name
        self.description = description
        self.func = func
    
    def __call__(self, *args, **kwargs):
        """使工具对象可调用"""
        return self.func(*args, **kwargs)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式（用于序列化）"""
        return {
            "name": self.name,
            "description": self.description
        }
    
    def __repr__(self):
        return f"Tool(name='{self.name}')"
    
    def __str__(self):
        return f"{self.name}: {self.description}"
    
    def __eq__(self, other):
        """比较工具是否相同（基于名称）"""
        if isinstance(other, Tool):
            return self.name == other.name
        elif isinstance(other, str):
            return self.name == other
        return False
    
    def __hash__(self):
        """使 Tool 对象可哈希（可用于 set/dict）"""
        return hash(self.name)


class AgentTools:
    """Agent 工具接口 - 支持仿真和真机两种模式"""
    
    def __init__(self):
        # 状态
        self.odom = None
        self.flight_status = "IDLE"  # IDLE, TAKEOFF, HOVER, NAVIGATE, LAND
        self.status_lock = threading.Lock()
        self.odom_received = False
        
        # 模式选择：从ros参数读取
        self.use_px4 = rospy.get_param('rl/use_px4', False)
        self.use_real_drone = rospy.get_param('~use_real_drone', False)  # 是否使用真机
        self.takeoff_height = rospy.get_param('autonomous_flight/takeoff_height', 1.5)
        
        # 真机脚本路径（如果使用真机）
        if self.use_real_drone:
            self.real_drone_scripts = {
                'takeoff': rospy.get_param('~real_drone_takeoff_script', ''),
                'land': rospy.get_param('~real_drone_land_script', ''),
                'hover': rospy.get_param('~real_drone_hover_script', ''),
            }
            rospy.loginfo("🚁 使用真机模式")
            rospy.loginfo(f"   起飞脚本: {self.real_drone_scripts['takeoff']}")
            rospy.loginfo(f"   降落脚本: {self.real_drone_scripts['land']}")
        
        # 话题配置：优先使用自定义配置，否则根据模式选择默认值
        # 里程计话题
        self.odom_topic = rospy.get_param('~odom_topic', None)
        if self.odom_topic is None:
            if self.use_px4:
                self.odom_topic = '/mavros/local_position/odom'
            else:
                self.odom_topic = '/CERLAB/quadcopter/odom'
        
        # 位置控制话题
        self.pose_topic = rospy.get_param('~pose_topic', None)
        if self.pose_topic is None:
            if self.use_px4:
                self.pose_topic = '/mavros/setpoint_position/local'
            else:
                self.pose_topic = '/CERLAB/quadcopter/setpoint_pose'
        
        # 导航目标话题
        self.goal_topic = rospy.get_param('~goal_topic', '/move_base_simple/goal')
        
        # 日志输出配置信息
        if self.use_real_drone:
            rospy.loginfo("🚁 模式: 真机")
        elif self.use_px4:
            rospy.loginfo("🚁 模式: PX4仿真")
        else:
            rospy.loginfo("🚁 模式: CERLAB仿真")
        
        rospy.loginfo(f"📡 里程计话题: {self.odom_topic}")
        rospy.loginfo(f"📡 位置控制话题: {self.pose_topic}")
        rospy.loginfo(f"📡 导航目标话题: {self.goal_topic}")
        
        # 发布者
        self.goal_pub = rospy.Publisher(self.goal_topic, PoseStamped, queue_size=1)
        self.pose_pub = rospy.Publisher(self.pose_topic, PoseStamped, queue_size=10)
        self.status_pub = rospy.Publisher('/agent/status', String, queue_size=10)
        self.vision_cmd_pub = rospy.Publisher('/agent_node/vision_command', String, queue_size=1)
        self.direct_tool_pub = rospy.Publisher('/agent_node/direct_tool_call', String, queue_size=1)
        
        # 订阅者
        rospy.loginfo(f"📥 订阅里程计: {self.odom_topic}")
        rospy.Subscriber(self.odom_topic, Odometry, self._on_odom)
        
        # 视觉响应缓存
        self.vision_response = None
        self.vision_response_lock = threading.Lock()
        rospy.Subscriber('/vision_node/env_description', String, self._on_vision_response)
        
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
    
    def _execute_real_drone_script(self, script_type, *args):
        """
        执行真机脚本
        
        Args:
            script_type: 脚本类型 ('takeoff', 'land', 'hover')
            *args: 传递给脚本的参数
        
        Returns:
            dict: {'result': str, 'success': bool}
        """
        import subprocess
        
        if not self.use_real_drone:
            return {"result": "非真机模式", "success": False}
        
        script_path = self.real_drone_scripts.get(script_type, '')
        if not script_path:
            return {"result": f"未配置{script_type}脚本", "success": False}
        
        try:
            # 构建命令
            cmd = [script_path] + [str(arg) for arg in args]
            rospy.loginfo(f"🚁 执行真机脚本: {' '.join(cmd)}")
            
            # 执行脚本
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30.0
            )
            
            if result.returncode == 0:
                rospy.loginfo(f"✅ 脚本执行成功: {script_type}")
                return {
                    "result": result.stdout.strip() or f"{script_type}成功",
                    "success": True
                }
            else:
                rospy.logerr(f"❌ 脚本执行失败: {result.stderr}")
                return {
                    "result": f"{script_type}失败: {result.stderr}",
                    "success": False
                }
        
        except subprocess.TimeoutExpired:
            return {"result": f"{script_type}超时", "success": False}
        except Exception as e:
            return {"result": f"{script_type}错误: {e}", "success": False}
    
    def _on_odom(self, msg):
        self.odom = msg
        if not self.odom_received:
            self.odom_received = True
        # 自动更新飞行状态
        if self.odom.pose.pose.position.z > 0.5:
            current_status = self._get_status()
            if current_status == "IDLE":
                self._set_status("HOVER")
    
    def _on_vision_response(self, msg):
        """接收vision节点的响应"""
        with self.vision_response_lock:
            self.vision_response = msg.data
    
    def _set_status(self, status):
        with self.status_lock:
            self.flight_status = status
        self.status_pub.publish(status)
    
    def _get_status(self):
        with self.status_lock:
            return self.flight_status
    
    def _init_tools(self) -> List[Tool]:
        """初始化工具列表（使用面向对象封装）"""
        return [
            Tool(
                name="takeoff",
                description="起飞到指定高度。参数: {'height': float}，例如 {'height': 2.0}，默认使用配置高度",
                func=self.takeoff
            ),
            Tool(
                name="land",
                description="降落。无参数。",
                func=self.land
            ),
            Tool(
                name="set_goal",
                description="设置导航目标点（异步）。参数: {'x': float, 'y': float, 'z': float}。navigation_node.py 使用 RL 策略自动避障导航。调用后立即返回，导航在后台进行。",
                func=self.set_goal
            ),
            Tool(
                name="get_current_position",
                description="获取当前位置。无参数。",
                func=self.get_current_position
            ),
            Tool(
                name="get_flight_status",
                description="获取飞行状态。无参数。返回: IDLE/HOVER/NAVIGATE 等",
                func=self.get_flight_status
            ),
            Tool(
                name="get_detected_objects",
                description="获取检测到的物体列表及其世界坐标。无参数。返回格式：[{'name': '物体名称', 'x': float, 'y': float, 'z': float, 'distance': float}]。用于识别'柱子'、'桌子'、'椅子'等物体的位置。",
                func=self.get_detected_objects
            ),
            Tool(
                name="rotate",
                description="原地旋转指定角度以搜索目标物体。默认 60° 步长（建议 360° 搜索时旋转 6 次）。参数: {'angle': float}，例如 {'angle': 60} 表示右转60度。用于视觉搜索时扩大视野。旋转完成后自动检测物体。",
                func=self.rotate
            ),
            Tool(
                name="describe_scene",
                description="【可选工具】使用 VLM 获取详细场景描述。注意：你已经可以直接看到画面（第一轮自动附加图像），大多数情况下无需调用此工具。仅在以下情况使用：1) 需要非常详细的场景描述 2) 需要回答关于场景的具体问题 3) 多轮对话中需要重新观察。参数: {'query': str}，例如 {'query': '墙的材质是什么？'}。",
                func=self.describe_scene
            ),
            # 注意：移除了 move_until_obstacle 工具
            # 原因：端到端导航系统（navigation_node）已包含避障功能
            # Agent 只需调用 set_goal，导航系统会自动处理障碍物
        ]
    
    def get_tool_by_name(self, name: str) -> Tool:
        """根据名称获取工具对象"""
        for tool in self.tools:
            if tool.name == name:
                return tool
        return None
    
    def has_tool(self, name: str) -> bool:
        """检查是否存在指定名称的工具"""
        return self.get_tool_by_name(name) is not None
    
    def get_tool_names(self) -> List[str]:
        """获取所有工具名称列表"""
        return [tool.name for tool in self.tools]
    
    def get_tools_description(self) -> str:
        """获取工具描述（JSON 格式）"""
        return json.dumps([tool.to_dict() for tool in self.tools], 
                         indent=2, ensure_ascii=False)
    
    def list_tools(self) -> str:
        """列出所有工具（人类可读格式）"""
        result = "可用工具列表:\n"
        for i, tool in enumerate(self.tools, 1):
            result += f"{i}. {tool.name}: {tool.description}\n"
        return result
    
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
        起飞 - 支持仿真和真机两种模式
        仿真: 发布目标位置到 setpoint_pose
        真机: 调用真机起飞脚本
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
            
            # 真机模式：调用脚本
            if self.use_real_drone:
                rospy.loginfo(f"🚁 真机起飞到 {height}m")
                self._set_status("TAKEOFF")
                
                result = self._execute_real_drone_script('takeoff', height)
                
                if result['success']:
                    self._set_status("HOVER")
                    rospy.loginfo("✅ 真机起飞成功!")
                    return {"result": f"起飞成功，目标高度 {height:.2f}m，状态: HOVER"}
                else:
                    self._set_status("IDLE")
                    return {"result": result['result']}
            
            # 仿真模式：发布位置指令
            if self.odom is None:
                return {"result": "里程计数据未就绪"}
            
            rospy.loginfo(f"🚁 仿真起飞到 {height}m")
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
        降落 - 支持仿真和真机两种模式
        仿真: 发布高度为0的目标点
        真机: 调用真机降落脚本
        """
        try:
            status = self._get_status()
            if status == "IDLE":
                return {"result": "已在地面"}
            
            # 真机模式：调用脚本
            if self.use_real_drone:
                rospy.loginfo("🛬 真机降落")
                self._set_status("LAND")
                
                result = self._execute_real_drone_script('land')
                
                if result['success']:
                    self._set_status("IDLE")
                    rospy.loginfo("✅ 真机降落成功!")
                    return {"result": "降落成功"}
                else:
                    return {"result": result['result']}
            
            # 仿真模式：发布位置指令
            if self.odom is None:
                return {"result": "里程计数据未就绪"}
            
            rospy.loginfo("🛬 仿真降落")
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

    def get_detected_objects(self, _=None):
        """获取检测物体及其位置 - 调用vision节点的YOLO检测"""
        try:
            # 清空之前的响应
            with self.vision_response_lock:
                self.vision_response = None
            
            # 发送命令到vision节点
            self.vision_cmd_pub.publish("get_objects")
            rospy.loginfo("🔍 请求物体检测...")
            
            # 等待响应（最多5秒）
            timeout = rospy.Time.now() + rospy.Duration(5.0)
            while rospy.Time.now() < timeout:
                with self.vision_response_lock:
                    if self.vision_response is not None:
                        try:
                            # 解析JSON响应
                            data = json.loads(self.vision_response)
                            
                            if data['status'] == 'ok':
                                objects = data['objects']
                                # 格式化输出
                                result_str = f"检测到 {len(objects)} 个物体：\n"
                                for i, obj in enumerate(objects, 1):
                                    wc = obj['world_coordinates']
                                    result_str += (
                                        f"{i}. {obj['name']} (置信度:{obj['confidence']:.2f}) - "
                                        f"位置:({wc['x']:.2f}, {wc['y']:.2f}, {wc['z']:.2f}), "
                                        f"距离:{obj['depth']:.2f}m\n"
                                    )
                                
                                rospy.loginfo(f"✅ 检测到 {len(objects)} 个物体")
                                return {
                                    "result": result_str.strip(),
                                    "objects": objects  # 返回结构化数据供Agent使用
                                }
                            else:
                                message = data.get('message', '未检测到物体')
                                rospy.loginfo(f"ℹ️ {message}")
                                return {"result": message}
                                
                        except json.JSONDecodeError as e:
                            rospy.logerr(f"JSON解析失败: {e}")
                            return {"result": f"错误: 响应格式错误 - {self.vision_response}"}
                
                rospy.sleep(0.1)
            
            return {"result": "超时：未收到vision节点响应，请确认vision节点是否运行"}
            
        except Exception as e:
            rospy.logerr(f"物体检测失败: {e}")
            return {"result": f"错误: {str(e)}"}
    
    def rotate(self, args):
        """
        原地旋转指定角度 - 支持仿真和真机两种模式
        仿真: 通过发布带旋转的位置指令实现
        真机: 通过mavros服务或自定义接口实现
        参数:
            angle: 旋转角度（度），正数为左转，负数为右转
            detect: 是否在旋转后检测物体（默认True，用于搜索；GUI调用时设为False）
        """
        try:
            if not isinstance(args, dict):
                return {"result": "参数格式错误，需要 {'angle': float, 'detect': bool}"}
            
            angle = float(args.get('angle', 60))  # 默认右转60度
            detect_objects = args.get('detect', True)  # 默认检测物体（用于LLM搜索）
            
            if self.odom is None:
                return {"result": "里程计数据未就绪"}
            
            status = self._get_status()
            if status not in ["HOVER", "NAVIGATE"]:
                return {"result": f"当前状态 {status}，需要先起飞到 HOVER 状态"}
            
            # 真机模式：使用mavros或自定义接口
            if self.use_real_drone or self.use_px4:
                return self._rotate_real_drone(angle, detect_objects)
            
            # 仿真模式：发布位置指令
            return self._rotate_simulation(angle, detect_objects)
            
        except Exception as e:
            return {"result": f"旋转错误: {e}"}
    
    def _rotate_real_drone(self, angle, detect_objects):
        """真机旋转实现"""
        try:
            # 获取当前朝向
            q = self.odom.pose.pose.orientation
            _, _, current_yaw = tft.euler_from_quaternion([q.x, q.y, q.z, q.w])
            
            # 计算新朝向
            new_yaw = current_yaw + math.radians(angle)
            while new_yaw > math.pi:
                new_yaw -= 2 * math.pi
            while new_yaw < -math.pi:
                new_yaw += 2 * math.pi
            
            rospy.loginfo(f"🔄 真机旋转: 当前yaw={math.degrees(current_yaw):.1f}°, 目标yaw={math.degrees(new_yaw):.1f}°, 旋转角度={angle:.1f}°")
            
            # 方案1: 尝试使用mavros设置yaw
            try:
                from mavros_msgs.srv import CommandLong
                from mavros_msgs.msg import State
                
                # 等待mavros服务
                rospy.wait_for_service('/mavros/cmd/command', timeout=1.0)
                command_service = rospy.ServiceProxy('/mavros/cmd/command', CommandLong)
                
                # MAV_CMD_CONDITION_YAW (115)
                # param1: target yaw (degrees)
                # param2: yaw speed (deg/s)
                # param3: direction (-1: ccw, 1: cw)
                # param4: relative (0: absolute, 1: relative)
                
                response = command_service(
                    broadcast=False,
                    command=115,  # MAV_CMD_CONDITION_YAW
                    confirmation=0,
                    param1=math.degrees(new_yaw),  # 目标角度
                    param2=30.0,  # 旋转速度 30度/秒
                    param3=1.0 if angle > 0 else -1.0,  # 方向
                    param4=0.0,  # 绝对角度
                    param5=0.0,
                    param6=0.0,
                    param7=0.0
                )
                
                if response.success:
                    rospy.loginfo("✅ mavros旋转命令发送成功")
                    
                    # 等待旋转完成
                    timeout = rospy.Time.now() + rospy.Duration(abs(angle) / 30.0 + 2.0)
                    rate = rospy.Rate(10)
                    
                    while not rospy.is_shutdown() and rospy.Time.now() < timeout:
                        if self.odom:
                            q_current = self.odom.pose.pose.orientation
                            _, _, yaw_current = tft.euler_from_quaternion([q_current.x, q_current.y, q_current.z, q_current.w])
                            
                            yaw_diff = new_yaw - yaw_current
                            if yaw_diff > math.pi:
                                yaw_diff -= 2 * math.pi
                            elif yaw_diff < -math.pi:
                                yaw_diff += 2 * math.pi
                            
                            if abs(math.degrees(yaw_diff)) < 5.0:
                                rospy.loginfo(f"✅ 旋转完成: 当前yaw={math.degrees(yaw_current):.1f}°")
                                break
                        
                        rate.sleep()
                    
                    # 检测物体
                    if detect_objects:
                        rospy.sleep(0.5)
                        detection_result = self.get_detected_objects({})
                        
                        if 'objects' in detection_result and len(detection_result['objects']) > 0:
                            return {
                                "result": f"原地旋转完成（旋转{angle:.1f}°），检测到 {len(detection_result['objects'])} 个物体。{detection_result.get('result', '')}",
                                "objects": detection_result['objects']
                            }
                        else:
                            return {"result": f"原地旋转完成（旋转{angle:.1f}°），未检测到物体。建议继续旋转搜索其他方向。"}
                    else:
                        return {"result": f"旋转完成（旋转{angle:.1f}°），当前朝向 {math.degrees(new_yaw):.1f}°"}
                
            except Exception as e:
                rospy.logwarn(f"mavros旋转失败: {e}，尝试使用位置控制")
            
            # 方案2: 回退到位置控制（与仿真相同）
            rospy.loginfo("使用位置控制方式旋转...")
            return self._rotate_simulation(angle, detect_objects)
            
        except Exception as e:
            return {"result": f"真机旋转错误: {e}"}
    
    def _rotate_simulation(self, angle, detect_objects):
        """仿真旋转实现"""
        try:
            # 获取当前位置和朝向
            current_x = self.odom.pose.pose.position.x
            current_y = self.odom.pose.pose.position.y
            current_z = self.odom.pose.pose.position.z
            
            q = self.odom.pose.pose.orientation
            _, _, current_yaw = tft.euler_from_quaternion([q.x, q.y, q.z, q.w])
            
            # 计算新朝向（转换角度为弧度）
            new_yaw = current_yaw + math.radians(angle)
            
            # 归一化到 [-pi, pi]
            while new_yaw > math.pi:
                new_yaw -= 2 * math.pi
            while new_yaw < -math.pi:
                new_yaw += 2 * math.pi
            
            rospy.loginfo(f"🔄 原地旋转: 当前yaw={math.degrees(current_yaw):.1f}°, 目标yaw={math.degrees(new_yaw):.1f}°, 旋转角度={angle:.1f}°")
            
            # 创建目标姿态（保持当前位置，只改变朝向）
            pose_target = PoseStamped()
            pose_target.header.frame_id = "map"
            pose_target.pose.position.x = current_x
            pose_target.pose.position.y = current_y
            pose_target.pose.position.z = current_z
            
            # 将目标 yaw 转换为四元数
            q_target = tft.quaternion_from_euler(0, 0, new_yaw)
            pose_target.pose.orientation.x = q_target[0]
            pose_target.pose.orientation.y = q_target[1]
            pose_target.pose.orientation.z = q_target[2]
            pose_target.pose.orientation.w = q_target[3]
            
            # 持续发布目标姿态直到旋转完成
            rospy.loginfo("   开始原地旋转...")
            rate = rospy.Rate(30)  # 30Hz 控制频率
            timeout = rospy.Time.now() + rospy.Duration(15.0)  # 15秒超时
            
            while not rospy.is_shutdown() and rospy.Time.now() < timeout:
                # 更新时间戳并发布
                pose_target.header.stamp = rospy.Time.now()
                self.pose_pub.publish(pose_target)
                
                # 检查是否到达目标角度
                if self.odom:
                    q_current = self.odom.pose.pose.orientation
                    _, _, yaw_current = tft.euler_from_quaternion([q_current.x, q_current.y, q_current.z, q_current.w])
                    
                    # 计算角度差
                    yaw_diff = new_yaw - yaw_current
                    # 处理跨越 -pi/pi 边界的情况
                    if yaw_diff > math.pi:
                        yaw_diff -= 2 * math.pi
                    elif yaw_diff < -math.pi:
                        yaw_diff += 2 * math.pi
                    
                    # 检查是否到达目标角度（允许3度误差）
                    if abs(math.degrees(yaw_diff)) < 3.0:
                        rospy.loginfo(f"   ✅ 旋转完成: 当前yaw={math.degrees(yaw_current):.1f}°, 误差={math.degrees(yaw_diff):.1f}°")
                        break
                
                rate.sleep()
            
            # 检查是否超时
            if rospy.Time.now() >= timeout:
                rospy.logwarn("   ⚠️ 旋转超时")
            
            # 旋转完成，继续发布姿态以锁定朝向
            rospy.loginfo("   旋转完成，锁定姿态...")
            
            # 根据参数决定是否检测物体
            if detect_objects:
                # 在检测期间持续发布姿态，防止漂移
                detection_start = rospy.Time.now()
                detection_timeout = 2.0  # 检测超时时间
                
                # 启动检测（异步）
                detection_result = None
                
                # 在检测期间持续发布姿态
                while not rospy.is_shutdown() and (rospy.Time.now() - detection_start).to_sec() < detection_timeout:
                    # 更新当前位置（防止XY漂移）
                    if self.odom:
                        pose_target.pose.position.x = self.odom.pose.pose.position.x
                        pose_target.pose.position.y = self.odom.pose.pose.position.y
                        pose_target.pose.position.z = self.odom.pose.pose.position.z
                    
                    pose_target.header.stamp = rospy.Time.now()
                    self.pose_pub.publish(pose_target)
                    
                    # 第一次循环时启动检测
                    if detection_result is None and (rospy.Time.now() - detection_start).to_sec() > 0.3:
                        detection_result = self.get_detected_objects({})
                        break
                    
                    rate.sleep()
                
                # 如果还没有检测结果，立即获取
                if detection_result is None:
                    detection_result = self.get_detected_objects({})
                
                if 'objects' in detection_result and len(detection_result['objects']) > 0:
                    detected_objects = detection_result['objects']
                    rospy.loginfo(f"✅ 旋转搜索完成，检测到 {len(detected_objects)} 个物体")
                    return {
                        "result": f"原地旋转完成（旋转{angle:.1f}°），检测到 {len(detected_objects)} 个物体。{detection_result.get('result', '')}",
                        "objects": detected_objects
                    }
                else:
                    rospy.loginfo(f"ℹ️ 旋转搜索完成，未检测到物体")
                    return {
                        "result": f"原地旋转完成（旋转{angle:.1f}°），未检测到物体。建议继续旋转搜索其他方向。"
                    }
            else:
                # GUI 调用：只旋转，不检测
                # 继续发布1秒以稳定姿态
                stabilize_start = rospy.Time.now()
                while not rospy.is_shutdown() and (rospy.Time.now() - stabilize_start).to_sec() < 1.0:
                    if self.odom:
                        pose_target.pose.position.x = self.odom.pose.pose.position.x
                        pose_target.pose.position.y = self.odom.pose.pose.position.y
                        pose_target.pose.position.z = self.odom.pose.pose.position.z
                    
                    pose_target.header.stamp = rospy.Time.now()
                    self.pose_pub.publish(pose_target)
                    rate.sleep()
                
                rospy.loginfo(f"✅ 旋转完成（旋转{angle:.1f}°）")
                return {
                    "result": f"旋转完成（旋转{angle:.1f}°），当前朝向 {math.degrees(new_yaw):.1f}°"
                }
            
        except Exception as e:
            rospy.logerr(f"旋转搜索失败: {e}")
            return {"result": f"错误: {e}"}
    
    def describe_scene(self, args=None):
        """
        使用视觉语言模型（VLM）描述当前场景
        用于 YOLO 无法识别的物体（如墙、门、窗、颜色等）
        
        注意：此工具会触发 agent.py 的多模态 VLM 调用
        实际的 VLM 推理在 agent.py 中完成
        """
        try:
            # 解析查询参数
            query = None
            if isinstance(args, dict):
                query = args.get('query', None)
            
            # 发送命令到 agent 节点请求 VLM 描述
            # 使用特殊话题通知 agent 需要 VLM 处理
            vlm_request = {
                'type': 'scene_description',
                'query': query or '描述当前画面中的主要物体、颜色和场景'
            }
            
            # 清空之前的响应
            with self.vision_response_lock:
                self.vision_response = None
            
            # 发送 VLM 请求
            self.vision_cmd_pub.publish(json.dumps(vlm_request))
            rospy.loginfo(f"🎨 请求 VLM 场景描述: {vlm_request['query']}")
            
            # 等待响应（最多 10 秒，VLM 推理较慢）
            timeout = rospy.Time.now() + rospy.Duration(10.0)
            while rospy.Time.now() < timeout:
                with self.vision_response_lock:
                    if self.vision_response is not None:
                        try:
                            # 解析响应
                            data = json.loads(self.vision_response)
                            
                            if data.get('type') == 'vlm_description':
                                description = data.get('description', '')
                                rospy.loginfo(f"✅ VLM 描述: {description[:100]}...")
                                return {
                                    "result": f"场景描述: {description}",
                                    "description": description
                                }
                        except json.JSONDecodeError:
                            # 如果不是 JSON，直接返回文本
                            rospy.loginfo(f"✅ VLM 描述: {self.vision_response[:100]}...")
                            return {
                                "result": f"场景描述: {self.vision_response}",
                                "description": self.vision_response
                            }
                
                rospy.sleep(0.2)
            
            # 超时：返回提示信息，让 agent.py 直接处理
            rospy.logwarn("⚠️ VLM 响应超时，将由 agent.py 直接处理")
            return {
                "result": "VLM_REQUEST",  # 特殊标记，告诉 agent.py 需要 VLM
                "query": query or '描述当前画面中的主要物体、颜色和场景',
                "note": "此请求需要 agent.py 的多模态模型处理"
            }
            
        except Exception as e:
            rospy.logerr(f"VLM 场景描述失败: {e}")
            return {"result": f"错误: {e}"}
    
    
    # ==================== 工具调用接口 ====================
    
    def call_tool(self, name: str, args=None) -> Dict[str, Any]:
        """通过名称调用工具（使用面向对象接口）"""
        tool = self.get_tool_by_name(name)
        if tool:
            return tool(args)  # 直接调用 Tool 对象
        return {"result": f"未知工具: {name}"}
