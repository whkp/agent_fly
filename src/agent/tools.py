#!/usr/bin/env python3
"""
Agent 工具接口 - 使用平台适配层

架构:
    tools.py ──▶ Platform ──▶ 实际机器人
"""

import rospy
from std_msgs.msg import String
import json
import threading
import math
import time
import os
import sys

# 导入配置管理和监控
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config_manager import ConfigManager
from tool_monitor import ToolMonitor
from tool_response import ToolResponse
from platforms.platform_factory import PlatformFactory


class AgentTools:
    """Agent 工具接口 - 使用平台适配层"""
    
    def __init__(self):
        # 配置管理
        self.config = ConfigManager()
        
        # 监控
        self.monitor = ToolMonitor(max_history=100)
        
        # 加载平台配置
        platform_config_file = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), 
            'cfg/platform_config.json'
        )
        with open(platform_config_file, 'r', encoding='utf-8') as f:
            platform_config = json.load(f)
        
        # 获取平台类型（可以从 ROS 参数或环境变量获取）
        platform_type = rospy.get_param('~platform_type', platform_config['platform_type'])
        rospy.loginfo(f"平台类型: {platform_type}")
        
        # 创建平台实例
        platform_cfg = platform_config['platforms'][platform_type]
        self.platform = PlatformFactory.create_platform(platform_type, platform_cfg)
        
        # 初始化平台
        self.platform.init_ros()
        
        # 等待数据就绪
        self.platform.wait_for_data()
        
        # 工具列表（从配置加载）
        self.tools = self._init_tools()
        
        rospy.loginfo(f"✅ 工具系统初始化完成，已加载 {len(self.tools)} 个工具")
        rospy.loginfo(f"✅ 使用平台: {platform_cfg['name']}")
    
    
    def _init_tools(self):
        """从配置初始化工具"""
        tool_configs = self.config.get_enabled_tools()
        tools = []
        
        # 工具实现映射
        tool_funcs = {
            'takeoff': self.takeoff,
            'land': self.land,
            'set_goal': self.set_goal,
            'move_relative': self.move_relative,
            'get_current_position': self.get_current_position,
            'get_flight_status': self.get_flight_status,
            'wait': self.wait,
            'hover': self.hover,
            'rotate_yaw': self.rotate_yaw,
            'describe_scene': self.describe_scene,
            'get_detected_objects': self.get_detected_objects,
            'is_object_visible': self.is_object_visible,
        }
        
        for cfg in tool_configs:
            name = cfg['name']
            if name in tool_funcs:
                tools.append({
                    'name': name,
                    'description': cfg['description'],
                    'func': tool_funcs[name],
                    'activation': cfg.get('activation', True)
                })
        
        return tools
    
    def get_tools_description(self):
        """获取工具描述（增强版）"""
        tools_list = []
        for tool in self.tools:
            tool_info = {
                "name": tool["name"],
                "description": tool["description"]
            }
            
            # 从配置中获取详细信息
            tool_config = next((t for t in self.config.get_enabled_tools() if t['name'] == tool['name']), None)
            if tool_config:
                # 添加参数信息
                if 'parameters' in tool_config and tool_config['parameters']:
                    params_desc = []
                    for param_name, param_info in tool_config['parameters'].items():
                        param_str = f"{param_name}: {param_info.get('type', 'any')}"
                        if 'range' in param_info:
                            param_str += f" (范围: {param_info['range']})"
                        if 'unit' in param_info:
                            param_str += f" {param_info['unit']}"
                        if 'description' in param_info:
                            param_str += f" - {param_info['description']}"
                        params_desc.append(param_str)
                    tool_info["parameters"] = ", ".join(params_desc)
                
                # 添加示例
                if 'example' in tool_config:
                    tool_info["example"] = tool_config['example']
                
                # 添加注意事项
                if 'notes' in tool_config:
                    tool_info["notes"] = tool_config['notes']
            
            tools_list.append(tool_info)
        
        return json.dumps(tools_list, indent=2, ensure_ascii=False)
    
    def get_status_dict(self):
        """获取状态字典"""
        pos = self.platform.get_current_position()
        status = self.platform.get_flight_status()
        
        if pos:
            return {
                "x": pos["x"],
                "y": pos["y"],
                "z": pos["z"],
                "yaw": round(pos["yaw"] * 180.0 / math.pi, 1),
                "status": status
            }
        else:
            return {
                "x": 0.0,
                "y": 0.0,
                "z": 0.0,
                "yaw": 0.0,
                "status": "Unknown"
            }
    
    def takeoff(self, args=None):
        """起飞 - 使用平台接口"""
        height = self.platform.config.get('takeoff_height', 1.5)
        try:
            if isinstance(args, dict):
                height = float(args.get('height', height))
            elif isinstance(args, (float, int)):
                height = float(args)
            
            if not 0.5 <= height <= 20.0:
                return {"result": f"高度 {height}m 超出允许范围 (0.5-20m)"}
            
            result = self.platform.takeoff(height)
            return {"result": result["message"]}
                
        except Exception as e:
            return {"result": f"错误: {e}"}
    
    def land(self, _=None):
        """降落 - 使用平台接口"""
        try:
            result = self.platform.land()
            return {"result": result["message"]}
                
        except Exception as e:
            return {"result": f"错误: {e}"}
    
    def set_goal(self, args):
        """设置目标点 - 使用平台接口"""
        try:
            if not isinstance(args, dict):
                return {"result": "参数格式错误，需要 {'x': float, 'y': float, 'z': float, 'yaw': float(可选)}"}
            
            x = float(args.get('x', 0))
            y = float(args.get('y', 0))
            z = float(args.get('z', 1.5))
            yaw = float(args.get('yaw', 0.0))
            
            result = self.platform.set_goal(x, y, z, yaw)
            return {"result": result["message"]}
            
        except Exception as e:
            return {"result": f"错误: {e}"}
    
    def move_relative(self, args):
        """相对当前位置移动"""
        try:
            if not isinstance(args, dict):
                return {"result": "参数格式错误，需要 {'dx': float, 'dy': float, 'dz': float}"}
            
            pos = self.platform.get_current_position()
            if pos is None:
                return {"result": "位置数据未就绪"}
            
            dx = float(args.get('dx', 0))
            dy = float(args.get('dy', 0))
            dz = float(args.get('dz', 0))
            
            # 计算目标位置
            target_x = pos['x'] + dx
            target_y = pos['y'] + dy
            target_z = pos['z'] + dz
            
            # 调用 set_goal
            return self.set_goal({
                'x': target_x,
                'y': target_y,
                'z': target_z,
                'yaw': pos['yaw']
            })
            
        except Exception as e:
            return {"result": f"错误: {e}"}
    
    def get_current_position(self, _=None):
        """获取当前位置"""
        try:
            pos = self.platform.get_current_position()
            if pos is None:
                return {"result": "无位置数据"}
            
            yaw_deg = pos['yaw'] * 180 / math.pi
            return {"result": f"x={pos['x']:.2f}, y={pos['y']:.2f}, z={pos['z']:.2f}m, yaw={yaw_deg:.0f}°"}
        except Exception as e:
            return {"result": f"错误: {e}"}
    
    def get_flight_status(self, _=None):
        """获取飞行状态"""
        status = self.platform.get_flight_status()
        pos = self.platform.get_current_position()
        pos_info = ""
        if pos:
            pos_info = f", 位置: ({pos['x']:.1f}, {pos['y']:.1f}, {pos['z']:.1f})"
        return {"result": f"状态: {status}{pos_info}"}
    
    def wait(self, args):
        """等待指定秒数"""
        try:
            seconds = float(args.get('seconds', 1.0)) if isinstance(args, dict) else float(args)
            
            if seconds > 60:
                return {"result": "等待时间过长，最多 60 秒"}
            if seconds < 0.1:
                return {"result": "等待时间过短，最少 0.1 秒"}
            
            rospy.loginfo(f"⏱️ 等待 {seconds} 秒")
            time.sleep(seconds)
            return {"result": f"等待 {seconds} 秒完成"}
        except Exception as e:
            return {"result": f"错误: {e}"}
    
    def hover(self, args):
        """在当前位置悬停指定时间"""
        try:
            duration = float(args.get('duration', 5.0)) if isinstance(args, dict) else float(args)
            
            if duration > 60:
                return {"result": "悬停时间过长，最多 60 秒"}
            if duration < 1.0:
                return {"result": "悬停时间过短，最少 1 秒"}
            
            status = self.platform.get_flight_status()
            if status not in ["HOVER", "NAVIGATE"]:
                return {"result": f"当前状态 {status}，需要先起飞到 HOVER 状态"}
            
            pos = self.platform.get_current_position()
            if pos is None:
                return {"result": "位置数据未就绪"}
            
            # 设置当前位置为目标（保持悬停）
            self.platform.set_goal(pos['x'], pos['y'], pos['z'], pos['yaw'])
            
            rospy.loginfo(f"🚁 悬停 {duration} 秒")
            time.sleep(duration)
            
            return {"result": f"悬停 {duration} 秒完成，位置: ({pos['x']:.2f}, {pos['y']:.2f}, {pos['z']:.2f})"}
        except Exception as e:
            return {"result": f"错误: {e}"}
    
    def rotate_yaw(self, args):
        """旋转指定角度（相对当前朝向）"""
        try:
            angle = float(args.get('angle', 0)) if isinstance(args, dict) else float(args)
            
            if abs(angle) > 360:
                return {"result": "旋转角度过大，范围 -360 到 360 度"}
            
            status = self.platform.get_flight_status()
            if status not in ["HOVER", "NAVIGATE"]:
                return {"result": f"当前状态 {status}，需要先起飞到 HOVER 状态"}
            
            pos = self.platform.get_current_position()
            if pos is None:
                return {"result": "位置数据未就绪"}
            
            # 计算目标朝向
            target_yaw = pos['yaw'] + math.radians(angle)
            
            # 设置目标
            self.platform.set_goal(pos['x'], pos['y'], pos['z'], target_yaw)
            
            rospy.loginfo(f"🔄 旋转 {angle}°")
            
            # 等待旋转完成
            time.sleep(abs(angle) / 90.0 + 0.5)  # 估算旋转时间
            
            return {"result": f"旋转 {angle}° 完成，当前朝向 {math.degrees(target_yaw):.1f}°"}
        except Exception as e:
            return {"result": f"错误: {e}"}
    
    def describe_scene(self, _=None):
        """使用 VLM 描述场景"""
        try:
            # 发送命令给 vision_node
            cmd_pub = rospy.Publisher('/agent_node/vision_command', String, queue_size=1, latch=True)
            rospy.sleep(0.1)  # 等待发布者建立
            cmd_pub.publish("describe_scene")
            
            # 等待结果
            rospy.loginfo("🔍 请求场景描述...")
            result = rospy.wait_for_message('/vision_node/env_description', String, timeout=10.0)
            
            return {"result": result.data}
        except rospy.ROSException:
            return {"result": "超时：vision_node 未响应，请确保 vision_node 已启动"}
        except Exception as e:
            return {"result": f"错误: {e}"}

    def get_detected_objects(self, _=None):
        """获取 YOLO 检测到的物体及其世界坐标"""
        try:
            # 发送命令给 vision_node
            cmd_pub = rospy.Publisher('/agent_node/vision_command', String, queue_size=1, latch=True)
            rospy.sleep(0.1)
            cmd_pub.publish("get_objects")
            
            # 等待结果
            rospy.loginfo("🔍 请求物体检测...")
            result = rospy.wait_for_message('/vision_node/env_description', String, timeout=10.0)
            
            # 解析 JSON 结果
            data = json.loads(result.data)
            
            if data['status'] == 'ok':
                objects = data['objects']
                summary = f"检测到 {data['count']} 个物体: "
                obj_list = []
                for obj in objects:
                    obj_list.append(f"{obj['name']}(位置: {obj['world_coordinates']['x']:.1f}, {obj['world_coordinates']['y']:.1f}, {obj['world_coordinates']['z']:.1f})")
                summary += ", ".join(obj_list)
                return {"result": summary, "objects": objects}
            else:
                return {"result": data.get('message', '未检测到物体')}
                
        except rospy.ROSException:
            return {"result": "超时：vision_node 未响应，请确保 vision_node 已启动"}
        except json.JSONDecodeError:
            return {"result": f"数据解析错误: {result.data}"}
        except Exception as e:
            return {"result": f"错误: {e}"}
    
    def is_object_visible(self, args):
        """检查指定物体是否在视野中"""
        try:
            object_name = args.get('object_name', '') if isinstance(args, dict) else str(args)
            
            if not object_name:
                return {"result": "错误：未指定物体名称"}
            
            # 获取检测到的物体
            result = self.get_detected_objects()
            
            if 'objects' not in result:
                return {"result": f"否，{object_name} 不在视野中（未检测到任何物体）"}
            
            # 检查是否有匹配的物体
            for obj in result['objects']:
                if object_name.lower() in obj['name'].lower():
                    coords = obj['world_coordinates']
                    return {"result": f"是，{obj['name']} 在视野中，世界坐标: ({coords['x']:.2f}, {coords['y']:.2f}, {coords['z']:.2f})，距离: {obj['depth']:.2f}m"}
            
            return {"result": f"否，{object_name} 不在视野中"}
        except Exception as e:
            return {"result": f"错误: {e}"}
    
    # ==================== 工具调用接口 ====================
    
    def call_tool(self, name, args=None):
        """通过名称调用工具"""
        for tool in self.tools:
            if tool["name"] == name:
                return tool["func"](args)
        return {"result": f"未知工具: {name}"}
