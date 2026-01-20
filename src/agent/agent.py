#!/usr/bin/env python3
"""
Agent 主程序 - 精简版

特点:
- 使用多模态大模型处理文本和视觉
- 集成任务规划器和导航回调
- 精简提示词模板
- 确定性逻辑代码化
"""
import os, json, threading, queue, time, sys, base64, re
import numpy as np
from typing import Dict, Any, Optional
from enum import Enum

import rospy
from std_msgs.msg import String
from sensor_msgs.msg import Image as ROSImage
from geometry_msgs.msg import Point
import cv2
from cv_bridge import CvBridge

from langchain_openai import ChatOpenAI
from langchain.memory import ConversationBufferWindowMemory
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.pydantic_v1 import BaseModel, Field
from langchain_core.messages import HumanMessage, SystemMessage

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tools import AgentTools
from utils import calculate_approach_point, find_object_by_position
from task_planner import TaskPlanner
from navigation_callback import NavigationCallback
from prompts import get_prompt

# 导入地图服务
try:
    from map_manager.srv import CheckPosCollision, GetStaticObstacles
    MAP_SERVICES_AVAILABLE = True
except ImportError:
    MAP_SERVICES_AVAILABLE = False
    print("⚠️ map_manager服务未找到，地图感知功能将不可用")

# 导入检测服务
try:
    from onboard_detector.srv import GetDynamicObstacles
    DETECTOR_SERVICES_AVAILABLE = True
except ImportError:
    DETECTOR_SERVICES_AVAILABLE = False
    print("⚠️ onboard_detector服务未找到，动态障碍物感知功能将不可用")

# 清除代理
for proxy_var in ["HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"]:
    os.environ.pop(proxy_var, None)


# ==============================================================================
# 数据结构
# ==============================================================================
class TaskState(Enum):
    IDLE = "idle"
    FAILED = "failed"
    STOPPED = "stopped"

class TaskContext:
    def __init__(self):
        self.state = TaskState.IDLE
        self.turn = 0
        self.last_action = None
        self.action_count = {}
    
    def reset(self, question: str = None):
        self.state = TaskState.IDLE
        self.turn = 0
        self.last_action = None
        self.action_count = {}

class AgentActionSchema(BaseModel):
    thought: str = Field(description="思考过程")
    action_name: str = Field(description="工具名称或Final")
    action_params: Dict[str, Any] = Field(description="工具参数")
    final_message: Optional[str] = Field(description="最终回复", default=None)


# ==============================================================================
# 工具函数
# ==============================================================================
def fallback_parse_json(text: str) -> Optional[Dict[str, Any]]:
    """降级JSON解析"""
    try:
        return json.loads(text)
    except:
        pass
    
    patterns = [
        r'```json\s*(\{.*?\})\s*```',
        r'```\s*(\{.*?\})\s*```',
        r'(\{[^{}]*"thought"[^{}]*\})',
        r'(\{.*\})',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except:
                continue
    return None


# ==============================================================================
# 安全管理
# ==============================================================================
class SafetyManager:
    def __init__(self):
        self.MIN_Z = rospy.get_param('~safety_min_z', 1.0)
        self.MAX_Z = rospy.get_param('~safety_max_z', 15.0)
        self.SAFE_XY_RANGE = rospy.get_param('~safety_xy_range', 50.0)
        self.MAX_SINGLE_MOVE = rospy.get_param('~safety_max_single_move', 20.0)
        rospy.loginfo(f"🛡️ 安全参数: 高度[{self.MIN_Z}, {self.MAX_Z}]m, XY±{self.SAFE_XY_RANGE}m, 单次≤{self.MAX_SINGLE_MOVE}m")
    
    def check_image_quality(self, image: np.ndarray) -> tuple:
        if image is None or image.shape[0] < 10 or image.shape[1] < 10:
            return False, "图像无效"
        
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image
        brightness = np.mean(gray)
        
        if brightness < 10:
            return False, f"图像过暗({brightness:.1f})"
        if brightness > 245:
            return False, f"图像过曝({brightness:.1f})"
        
        blur = cv2.Laplacian(gray, cv2.CV_64F).var()
        if blur < 10:
            return False, f"图像模糊({blur:.1f})"
        
        return True, "OK"

    def validate(self, action_name: str, params: dict, current_state: dict) -> tuple:
        # 高度检查
        if action_name == "takeoff":
            # 起飞高度检查
            target_z = params.get("height")
            if target_z is not None:
                try:
                    z_val = float(target_z)
                    if z_val < self.MIN_Z or z_val > self.MAX_Z:
                        return False, f"起飞高度{z_val}m超出范围[{self.MIN_Z}, {self.MAX_Z}]m"
                except:
                    return False, f"高度参数无效'{target_z}'"
        
        # 注意：set_goal 的 z 坐标不在这里检查，因为会在后面自动修正
        # 这样可以避免 LLM 因为检测到的物体高度不合法而反复思考

        # XY坐标检查
        if action_name == "set_goal":
            try:
                cur_x, cur_y = current_state.get('x', 0), current_state.get('y', 0)
                tar_x, tar_y = float(params.get('x', cur_x)), float(params.get('y', cur_y))
                
                if abs(tar_x) > self.SAFE_XY_RANGE or abs(tar_y) > self.SAFE_XY_RANGE:
                    return False, f"坐标({tar_x:.1f}, {tar_y:.1f})超出范围±{self.SAFE_XY_RANGE}m"
                
                dist = ((tar_x - cur_x)**2 + (tar_y - cur_y)**2) ** 0.5
                if dist > self.MAX_SINGLE_MOVE:
                    return False, f"移动距离{dist:.1f}m超过限制{self.MAX_SINGLE_MOVE}m"
            except Exception as e:
                return False, f"坐标参数错误: {e}"

        return True, "Safe"


# ==============================================================================
# Agent 主类
# ==============================================================================
class AgentRobot:
    def __init__(self):
        # 图像处理
        self.cv_bridge = CvBridge()
        self.current_image = None
        self.image_lock = threading.Lock()
        
        # 任务上下文
        self.task_ctx = TaskContext()
        self.task_ctx_lock = threading.Lock()
        
        # 统计
        self.stats = {'total_tasks': 0, 'successful_tasks': 0, 'failed_tasks': 0, 
                     'vision_calls': 0, 'tool_calls': 0}
        self.stats_lock = threading.Lock()
        
        # 事件队列
        self.event_queue = queue.Queue()
        
        # 初始化ROS
        self._init_ros()
        
        # 核心组件
        self.agent_tool = AgentTools()
        self.safety = SafetyManager()
        self.planner = TaskPlanner()
        self.nav_callback = NavigationCallback(self.agent_tool)
        rospy.loginfo("✅ 组件已加载")
        
        # LLM
        self.model_name = rospy.get_param('~model_name', 'qwen3-vl-flash')
        self.api_base = rospy.get_param('~api_base', 'https://dashscope.aliyuncs.com/compatible-mode/v1')
        rospy.loginfo(f"🤖 模型: {self.model_name}")
        
        self.llm = ChatOpenAI(model=self.model_name, temperature=0.1, base_url=self.api_base)
        self.parser = PydanticOutputParser(pydantic_object=AgentActionSchema)
        self.memory = ConversationBufferWindowMemory(k=5, return_messages=True)
        
        # 启动统计线程
        threading.Thread(target=self._publish_stats_loop, daemon=True).start()
        
        # 地图感知配置
        self.enable_map_awareness = rospy.get_param('~enable_map_awareness', True)
        self.obstacle_detection_range = rospy.get_param('~obstacle_detection_range', 5.0)
        if self.enable_map_awareness:
            rospy.loginfo(f"🗺️ 地图感知已启用，检测范围: {self.obstacle_detection_range}m")

    def _init_ros(self):
        rospy.init_node('agent_node', anonymous=False)
        self.log_pub = rospy.Publisher('/agent_node/agent_log', String, queue_size=50)
        self.stats_pub = rospy.Publisher('/agent_node/stats', String, queue_size=10)
        
        rospy.Subscriber('/agent_node/user_command', String, lambda msg: self.event_queue.put(("command", msg.data)))
        rospy.Subscriber('/agent_node/emergency_stop', String, lambda msg: self.event_queue.put(("stop", None)) if msg.data.lower() in ["stop", "emergency", "halt", "abort"] else None)
        rospy.Subscriber('/camera/color/image_raw', ROSImage, self._on_image)
        
        # 输出服务可用性警告
        if not MAP_SERVICES_AVAILABLE:
            rospy.logwarn("⚠️ map_manager服务未找到，地图感知功能将不可用")
        if not DETECTOR_SERVICES_AVAILABLE:
            rospy.logwarn("⚠️ onboard_detector服务未找到，动态障碍物感知功能将不可用")
    
    def _on_image(self, msg):
        try:
            with self.image_lock:
                self.current_image = self.cv_bridge.imgmsg_to_cv2(msg, "bgr8")
        except Exception as e:
            if "libgdal" in str(e) or "TIFF" in str(e):
                try:
                    img_array = np.frombuffer(msg.data, dtype=np.uint8)
                    with self.image_lock:
                        if msg.encoding == "bgr8":
                            self.current_image = img_array.reshape((msg.height, msg.width, 3))
                        elif msg.encoding == "rgb8":
                            img_rgb = img_array.reshape((msg.height, msg.width, 3))
                            self.current_image = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2BGR)
                except:
                    pass
    
    def get_image_base64(self):
        with self.image_lock:
            if self.current_image is None:
                return None, "图像为空"
            
            is_valid, reason = self.safety.check_image_quality(self.current_image)
            if not is_valid:
                return None, reason
            
            try:
                img = cv2.resize(self.current_image, (640, 480))
                _, buffer = cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, 85])
                return base64.b64encode(buffer).decode('utf-8'), "OK"
            except Exception as e:
                return None, str(e)
    
    def check_needs_vision(self, question):
        q = question.lower()
        state_kw = ["状态", "电量", "坐标", "位置", "高度", "yaw", "朝向"]
        vision_kw = ["看", "描述", "画面", "场景", "环境", "前方", "周围", "视野", "观察", "障碍", "物体", "检测", "识别"]
        no_vision_kw = ["起飞", "降落", "飞到", "坐标"]
        
        if any(kw in q for kw in state_kw) and not any(kw in q for kw in vision_kw):
            return False
        if any(kw in q for kw in vision_kw):
            return True
        if any(kw in q for kw in no_vision_kw):
            return False
        return False

    def publish_log(self, role, type_str, content):
        self.log_pub.publish(json.dumps({"role": role, "type": type_str, "content": content}, ensure_ascii=False))
    
    def _execute_plan(self, plan):
        """执行显式任务计划"""
        self.planner.current_plan = plan
        self.planner.current_index = 0
        
        print(f"📋 开始执行计划（共 {len(plan)} 个子任务）")
        
        while self.planner.current_index < len(plan) and not rospy.is_shutdown():
            # 检查停止事件
            try:
                event_type, event_data = self.event_queue.get(timeout=0.1)
                if event_type == "stop":
                    rospy.logwarn("🚨 计划执行被停止")
                    
                    # 取消当前导航
                    if self.nav_callback.is_navigating():
                        self.nav_callback.cancel()
                        rospy.loginfo("🛑 已取消当前导航")
                    
                    self.publish_log("system", "Stopped", "计划执行已停止")
                    self._update_stats(failed_tasks=1)
                    return
                elif event_type == "command":
                    rospy.logwarn(f"⏸ 计划执行被中断，切换到新任务: {event_data}")
                    
                    # 取消当前导航
                    if self.nav_callback.is_navigating():
                        self.nav_callback.cancel()
                        rospy.loginfo("🛑 已取消当前导航")
                    
                    self.publish_log("system", "Interrupted", f"计划执行被中断，切换到新任务")
                    self._update_stats(failed_tasks=1)
                    
                    # 将新命令放回队列，让run_one_task处理
                    self.event_queue.put(("command", event_data))
                    return
            except queue.Empty:
                pass
            
            subtask = self.planner.get_next_subtask()
            if subtask is None:
                break
            
            print(f"\n▶️ 子任务 {self.planner.current_index + 1}/{len(plan)}: {subtask.description}")
            self.publish_log("system", "SubTask", f"{subtask.type.value}: {subtask.description}")
            
            # 执行子任务
            success = self._execute_subtask(subtask)
            
            if success:
                self.planner.mark_completed()
                print(f"✅ 子任务完成")
            else:
                self.planner.mark_failed("执行失败")
                print(f"❌ 子任务失败")
                # 可以选择：继续执行 or 终止计划
                # 这里选择继续
        
        # 计划执行完成
        progress = self.planner.get_progress()
        print(f"\n🎉 计划执行完成！完成率：{progress['progress_percent']:.1f}%")
        self.publish_log("system", "PlanComplete", f"完成 {progress['completed']}/{progress['total']} 个子任务")
        self._update_stats(successful_tasks=1)
    
    def _execute_subtask(self, subtask):
        """执行单个子任务"""
        from task_planner import SubTaskType
        
        try:
            if subtask.type == SubTaskType.NAVIGATE:
                # 导航子任务
                goal = subtask.params
                self.nav_callback.start_navigation(
                    goal=goal,
                    on_complete=lambda: None,  # 回调在这里不需要做什么
                    on_fail=lambda r: rospy.logerr(f"导航失败: {r}")
                )
                
                # 等待导航完成
                timeout = 60.0
                start_time = time.time()
                while self.nav_callback.is_navigating() and not rospy.is_shutdown():
                    if time.time() - start_time > timeout:
                        rospy.logwarn("导航超时")
                        return False
                    time.sleep(0.5)
                
                return self.nav_callback.get_status().value == "completed"
            
            elif subtask.type == SubTaskType.ROTATE_SEARCH:
                # 旋转搜索子任务
                angle = subtask.params.get('angle', 60)
                
                # 调用旋转工具
                rotate_tool = self.agent_tool.get_tool_by_name('rotate')
                if rotate_tool:
                    result = rotate_tool({'angle': angle})
                    print(f"🔄 旋转 {angle}°")
                    
                    # 检测物体
                    detect_tool = self.agent_tool.get_tool_by_name('get_detected_objects')
                    if detect_tool:
                        objects = detect_tool({})
                        obj_list = objects.get('result', [])
                        if obj_list:
                            print(f"🔍 检测到 {len(obj_list)} 个物体")
                    
                    return True
                return False
            
            elif subtask.type == SubTaskType.TAKEOFF:
                # 起飞子任务
                height = subtask.params.get('height', 1.5)
                takeoff_tool = self.agent_tool.get_tool_by_name('takeoff')
                if takeoff_tool:
                    result = takeoff_tool({'height': height})
                    time.sleep(3)  # 等待起飞稳定
                    return True
                return False
            
            elif subtask.type == SubTaskType.LAND:
                # 降落子任务
                land_tool = self.agent_tool.get_tool_by_name('land')
                if land_tool:
                    result = land_tool({})
                    return True
                return False
            
            else:
                rospy.logwarn(f"未知子任务类型: {subtask.type}")
                return False
        
        except Exception as e:
            rospy.logerr(f"子任务执行异常: {e}")
            return False


    def _get_nearby_obstacles(self, range_m=5.0):
        """获取周围障碍物信息（方案一：增强状态感知）"""
        obstacles = []
        
        if not self.enable_map_awareness:
            return obstacles
        
        try:
            state = self.agent_tool.get_status_dict()
            current_pos = (state['x'], state['y'], state['z'])
            
            # 1. 获取静态障碍物
            if MAP_SERVICES_AVAILABLE:
                try:
                    rospy.wait_for_service('/occupancy_map/get_static_obstacles', timeout=0.5)
                    get_static = rospy.ServiceProxy('/occupancy_map/get_static_obstacles', GetStaticObstacles)
                    resp = get_static()
                    
                    for i, pos in enumerate(resp.position):
                        dist = ((pos.x - current_pos[0])**2 + (pos.y - current_pos[1])**2)**0.5
                        if dist <= range_m:
                            obstacles.append({
                                'type': 'static',
                                'x': pos.x,
                                'y': pos.y,
                                'z': pos.z,
                                'distance': dist,
                                'size': resp.size[i] if i < len(resp.size) else None
                            })
                except Exception as e:
                    rospy.logdebug(f"静态障碍物查询失败: {e}")
            
            # 2. 获取动态障碍物
            if DETECTOR_SERVICES_AVAILABLE:
                try:
                    rospy.wait_for_service('/onboard_detector/get_dynamic_obstacles', timeout=0.5)
                    get_dynamic = rospy.ServiceProxy('/onboard_detector/get_dynamic_obstacles', GetDynamicObstacles)
                    resp = get_dynamic(Point(current_pos[0], current_pos[1], current_pos[2]), range_m)
                    
                    for i, pos in enumerate(resp.position):
                        dist = ((pos.x - current_pos[0])**2 + (pos.y - current_pos[1])**2)**0.5
                        vel = resp.velocity[i] if i < len(resp.velocity) else None
                        speed = (vel.x**2 + vel.y**2)**0.5 if vel else 0.0
                        
                        obstacles.append({
                            'type': 'dynamic',
                            'x': pos.x,
                            'y': pos.y,
                            'z': pos.z,
                            'distance': dist,
                            'speed': speed,
                            'velocity': (vel.x, vel.y, vel.z) if vel else None
                        })
                except Exception as e:
                    rospy.logdebug(f"动态障碍物查询失败: {e}")
            
            # 3. 按距离排序
            obstacles.sort(key=lambda x: x['distance'])
            
        except Exception as e:
            rospy.logwarn_throttle(10.0, f"障碍物查询异常: {e}")
        
        return obstacles
    
    def _check_goal_collision(self, goal):
        """检查目标点是否有碰撞（方案一：路径验证）"""
        if not self.enable_map_awareness or not MAP_SERVICES_AVAILABLE:
            return False
        
        try:
            rospy.wait_for_service('/occupancy_map/check_collision', timeout=0.5)
            check_collision = rospy.ServiceProxy('/occupancy_map/check_collision', CheckPosCollision)
            
            resp = check_collision(goal['x'], goal['y'], goal['z'], True)  # inflated=True
            return resp.occupied
        except Exception as e:
            rospy.logdebug(f"碰撞检测失败: {e}")
            return False
    
    def _get_direction(self, from_pos, to_pos):
        """计算障碍物相对方向（前/后/左/右）"""
        dx = to_pos['x'] - from_pos['x']
        dy = to_pos['y'] - from_pos['y']
        yaw = from_pos['yaw']
        
        # 转换到机体坐标系
        cos_yaw = np.cos(np.radians(yaw))
        sin_yaw = np.sin(np.radians(yaw))
        local_x = dx * cos_yaw + dy * sin_yaw
        local_y = -dx * sin_yaw + dy * cos_yaw
        
        if abs(local_x) > abs(local_y):
            return "前" if local_x > 0 else "后"
        else:
            return "左" if local_y > 0 else "右"
    
    def get_enhanced_state_str(self):
        """获取增强的状态字符串（包含障碍物信息）"""
        state = self.agent_tool.get_status_dict()
        state_str = f"坐标({state['x']:.1f}, {state['y']:.1f}, {state['z']:.1f}) | Yaw:{state['yaw']}° | 状态:{state['status']}"
        
        # 添加障碍物信息
        if self.enable_map_awareness:
            obstacles = self._get_nearby_obstacles(self.obstacle_detection_range)
            
            if obstacles:
                state_str += f" | 障碍物:{len(obstacles)}个"
                
                # 显示最近的3个障碍物
                for obs in obstacles[:3]:
                    direction = self._get_direction(state, obs)
                    obs_type = "动态" if obs['type'] == 'dynamic' else "静态"
                    
                    if obs['type'] == 'dynamic' and obs.get('speed', 0) > 0.1:
                        state_str += f" [{obs_type}{direction}{obs['distance']:.1f}m,速度{obs['speed']:.1f}m/s]"
                    else:
                        state_str += f" [{obs_type}{direction}{obs['distance']:.1f}m]"
        
        return state_str

    def _check_if_needs_verification(self, user_question: str, llm_response) -> bool:
        """
        判断是否需要导航后视觉确认
        
        规则：
        - 物体导航任务（"飞到XX前面"）需要确认
        - 坐标导航任务（"飞到(x,y,z)"）不需要确认
        """
        question_lower = user_question.lower()
        
        # 物体导航关键词
        object_nav_keywords = ["前面", "旁边", "附近", "桌子", "椅子", "人", "物体", 
                              "near", "front", "beside", "table", "chair", "person"]
        
        # 坐标导航关键词
        coord_nav_keywords = ["坐标", "coordinate", "(", "x", "y", "z"]
        
        # 如果包含坐标关键词，不需要确认
        if any(kw in question_lower for kw in coord_nav_keywords):
            return False
        
        # 如果包含物体导航关键词，需要确认
        if any(kw in question_lower for kw in object_nav_keywords):
            return True
        
        # 默认不需要确认
        return False

    def _update_stats(self, **kwargs):
        with self.stats_lock:
            for key, value in kwargs.items():
                if key in self.stats:
                    self.stats[key] += value if isinstance(value, (int, float)) else 0

    def _publish_stats_loop(self):
        rate = rospy.Rate(0.2)
        while not rospy.is_shutdown():
            try:
                with self.stats_lock:
                    self.stats_pub.publish(json.dumps(self.stats, ensure_ascii=False))
            except:
                pass
            rate.sleep()

    def run_one_task(self, user_question):
        """执行单个任务（支持显式规划或LLM循环）"""
        with self.task_ctx_lock:
            self.task_ctx.reset()
        
        print(f"\n🚀 任务: {user_question}")
        self.publish_log("user", "Question", user_question)
        self._update_stats(total_tasks=1)
        
        # 尝试生成显式任务计划
        state = self.agent_tool.get_status_dict()
        context = {
            'position': (state['x'], state['y'], state['z']),
            'yaw': state['yaw'],
            'status': state['status']
        }
        
        # 添加障碍物信息到上下文
        if self.enable_map_awareness:
            context['obstacles'] = self._get_nearby_obstacles(self.obstacle_detection_range)
        
        plan = self.planner.decompose(user_question, context)
        
        if plan:
            # 有显式计划，执行计划
            print(f"📋 生成任务计划：{len(plan)} 个子任务")
            self.publish_log("system", "Plan", f"生成 {len(plan)} 个子任务")
            self._execute_plan(plan)
            return
        else:
            # 无显式计划，使用 LLM 循环
            print("🤖 使用 LLM 规划（TaskPlanner未识别任务类型）")
        
        needs_vision = self.check_needs_vision(user_question)
        if needs_vision:
            print("👁️ 视觉模式")
            self._update_stats(vision_calls=1)
        
        self.memory.chat_memory.add_user_message(user_question)
        max_turns = 10
        
        while self.task_ctx.turn < max_turns and not rospy.is_shutdown():
            # 检查事件
            try:
                event_type, event_data = self.event_queue.get(timeout=0.1)
                if event_type == "stop":
                    rospy.logwarn("🚨 停止")
                    self.publish_log("system", "Stopped", "已停止")
                    
                    # 取消当前导航
                    if self.nav_callback.is_navigating():
                        self.nav_callback.cancel()
                        rospy.loginfo("🛑 已取消当前导航")
                    
                    self._update_stats(failed_tasks=1)
                    return
                elif event_type == "command":
                    print(f"⏸ 切换任务: {event_data}")
                    
                    # 取消当前导航
                    if self.nav_callback.is_navigating():
                        self.nav_callback.cancel()
                        rospy.loginfo("🛑 已取消当前导航，开始新任务")
                        self.publish_log("system", "Navigation", "已取消当前导航")
                    
                    self.task_ctx.reset()
                    user_question = event_data
                    self.memory.chat_memory.clear()
                    self.memory.chat_memory.add_user_message(event_data)
                    needs_vision = self.check_needs_vision(event_data)
                    continue
            except queue.Empty:
                pass
            
            # 获取状态和提示词
            state = self.agent_tool.get_status_dict()
            state_str = self.get_enhanced_state_str()  # 使用增强状态（包含障碍物）
            tools_str = self.agent_tool.get_tools_description()
            system_prompt = get_prompt(state_str, tools_str, self.parser.get_format_instructions(), needs_vision)
            
            print(f"\n--- Round {self.task_ctx.turn + 1} [{state_str}] {'[视觉]' if needs_vision else ''} ---")

            try:
                history = self.memory.load_memory_variables({})['history']
                
                # 构建消息
                # 视觉刷新策略：
                # 1. 第一轮：自动附加图像
                # 2. 后续轮次：如果上一轮是导航/旋转，刷新图像
                should_refresh_vision = False
                if needs_vision:
                    if self.task_ctx.turn == 0:
                        should_refresh_vision = True  # 第一轮
                    elif self.task_ctx.last_action in ['set_goal', 'rotate']:
                        should_refresh_vision = True  # 导航/旋转后刷新
                        print("🔄 视觉刷新（位置/朝向已改变）")
                
                if should_refresh_vision:
                    image_b64, img_status = self.get_image_base64()
                    if image_b64:
                        user_message = HumanMessage(content=[
                            {"type": "text", "text": "请分析并执行"},
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}}
                        ])
                        print("📷 已附加画面")
                    else:
                        user_message = HumanMessage(content="请分析并执行")
                        print(f"⚠️ 图像不可用({img_status})")
                else:
                    user_message = HumanMessage(content="请继续执行" if self.task_ctx.turn > 0 else "请分析并执行")
                
                messages = [SystemMessage(content=system_prompt)] + history + [user_message]
                llm_response = self.llm.invoke(messages)
                
                # 解析响应
                try:
                    response = self.parser.parse(llm_response.content)
                except:
                    parsed_dict = fallback_parse_json(llm_response.content)
                    if parsed_dict:
                        response = AgentActionSchema(
                            thought=parsed_dict.get('thought', '解析失败'),
                            action_name=parsed_dict.get('action_name', 'Final'),
                            action_params=parsed_dict.get('action_params', {}),
                            final_message=parsed_dict.get('final_message')
                        )
                    else:
                        raise
                
            except Exception as e:
                if "AllocationQuota" in str(e) or "403" in str(e):
                    print("❌ API配额用完")
                    self._update_stats(failed_tasks=1)
                    break
                else:
                    print(f"⚠️ 错误: {e}")
                    self.memory.chat_memory.add_ai_message("格式错误，请输出纯JSON")
                    time.sleep(1)
                    self.task_ctx.turn += 1
                    continue

            thought, action, params = response.thought, response.action_name, response.action_params
            print(f"🧠 {thought}")
            self.publish_log("assistant", "Thought", thought)
            
            # 检测重复
            with self.task_ctx_lock:
                if action == self.task_ctx.last_action and action != "Final":
                    self.task_ctx.action_count[action] = self.task_ctx.action_count.get(action, 0) + 1
                    if self.task_ctx.action_count[action] >= 3:
                        print(f"⚠️ 重复动作'{action}'")
                        self.publish_log("assistant", "Final", "检测到重复操作")
                        self._update_stats(failed_tasks=1)
                        break
                else:
                    self.task_ctx.action_count = {action: 1}
                self.task_ctx.last_action = action

            if action == "Final":
                final_msg = response.final_message or "完成"
                print(f"✅ {final_msg}")
                self.publish_log("assistant", "Final", final_msg)
                self.memory.chat_memory.add_ai_message(final_msg)
                self._update_stats(successful_tasks=1)
                break

            # 执行工具
            tool_obj = self.agent_tool.get_tool_by_name(action)
            if tool_obj:
                self._update_stats(tool_calls=1)
                is_safe, warning = self.safety.validate(action, params, state)
                
                if is_safe:
                    # 导航任务额外检查碰撞
                    if action == "set_goal" and self.enable_map_awareness:
                        if self._check_goal_collision(params):
                            observation = f"⚠️ 目标点({params.get('x', 0):.1f}, {params.get('y', 0):.1f})有障碍物，请重新规划"
                            print(f"🛡️ {observation}")
                            self.publish_log("assistant", "Observation", observation)
                            self.memory.chat_memory.add_user_message(f"[{action}] {observation}")
                            self.task_ctx.turn += 1
                            time.sleep(0.5)
                            continue
                    
                    print(f"🛠 {action} {params}")
                    self.publish_log("assistant", "Action", f"{action} {params}")
                    
                    try:
                        res = tool_obj(params)
                        observation = str(res['result']) if isinstance(res, dict) and 'result' in res else str(res)
                        
                        # VLM场景描述
                        if action == "describe_scene" and isinstance(res, dict) and res.get('result') == 'VLM_REQUEST':
                            image_b64, img_status = self.get_image_base64()
                            if image_b64:
                                query = res.get('query', '描述画面')
                                vlm_msg = HumanMessage(content=[
                                    {"type": "text", "text": query},
                                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}}
                                ])
                                try:
                                    vlm_resp = self.llm.invoke([vlm_msg])
                                    observation = f"场景: {vlm_resp.content}"
                                except Exception as e:
                                    observation = f"VLM失败: {e}"
                            else:
                                observation = f"图像不可用({img_status})"
                        
                        # 导航任务 - 2D导航（只使用XY，保持当前高度）
                        if action == "set_goal":
                            current_pos = (state['x'], state['y'], state['z'])
                            target_pos = (params.get('x', 0), params.get('y', 0), params.get('z', 0))
                            
                            # 计算安全接近点（2D导航，保持当前高度）
                            # safe_distance=2.0 避免导航算法因避障绕到物体后方导致超时
                            safe_pos = calculate_approach_point(
                                target_pos, 
                                current_pos, 
                                safe_distance=2.0
                            )
                            params = {'x': safe_pos[0], 'y': safe_pos[1], 'z': safe_pos[2]}
                            
                            rospy.loginfo(f"🎯 2D导航目标: ({safe_pos[0]:.2f}, {safe_pos[1]:.2f}, {safe_pos[2]:.2f})")
                            
                            # 检查是否需要导航后视觉确认（物体导航任务）
                            needs_verification = self._check_if_needs_verification(user_question, res)
                            
                            if needs_verification:
                                # 物体导航：导航完成后继续LLM循环进行视觉确认
                                self.nav_callback.start_navigation(
                                    goal=params,
                                    on_complete=lambda: self.memory.chat_memory.add_user_message("[导航完成，请视觉确认目标]"),
                                    on_fail=lambda r: self.memory.chat_memory.add_user_message(f"[导航失败:{r}]")
                                )
                                
                                observation = f"导航启动: ({params['x']:.1f}, {params['y']:.1f}, {params['z']:.1f})，到达后将视觉确认"
                                print(f"👀 {observation}")
                                self.publish_log("assistant", "Observation", observation)
                                self.memory.chat_memory.add_user_message(f"[{action}] {observation}")
                                
                                # 等待导航完成（异步）
                                timeout = rospy.Time.now() + rospy.Duration(60.0)
                                rate = rospy.Rate(5)
                                while not rospy.is_shutdown() and rospy.Time.now() < timeout:
                                    if not self.nav_callback.is_navigating():
                                        break
                                    rate.sleep()
                                
                                # 导航完成，继续LLM循环（不break）
                                
                            else:
                                # 坐标导航：导航启动后立即结束任务
                                self.nav_callback.start_navigation(
                                    goal=params,
                                    on_complete=lambda: self.memory.chat_memory.add_user_message("[导航完成]"),
                                    on_fail=lambda r: self.memory.chat_memory.add_user_message(f"[导航失败:{r}]")
                                )
                                
                                observation = f"已启动导航至 ({params['x']:.1f}, {params['y']:.1f}, {params['z']:.1f})，navigation_node 正在自动避障导航中..."
                                print(f"👀 {observation}")
                                self.publish_log("assistant", "Observation", observation)
                                
                                # 立即结束任务
                                final_msg = f"正在导航至目标点 ({params['x']:.1f}, {params['y']:.1f}, {params['z']:.1f})，请等待到达"
                                print(f"✅ {final_msg}")
                                self.publish_log("assistant", "Final", final_msg)
                                self.memory.chat_memory.add_ai_message(final_msg)
                                self._update_stats(successful_tasks=1)
                                break  # 退出思考循环
                        
                    except Exception as err:
                        observation = f"工具错误: {err}"
                else:
                    print(f"🛡️ {warning}")
                    observation = f"安全拦截: {warning}"
            else:
                observation = f"未知工具: {action}"

            print(f"👀 {observation}")
            self.publish_log("assistant", "Observation", observation)
            self.memory.chat_memory.add_user_message(f"[{action}] {observation[:150]}")
            
            self.task_ctx.turn += 1
            time.sleep(0.5)
        
        if self.task_ctx.turn >= max_turns:
            print("⚠️ 超过最大轮次")
            self._update_stats(failed_tasks=1)

    def run_loop(self):
        rospy.loginfo("🤖 Agent就绪，等待用户命令...")
        print("🤖 Agent就绪，等待用户命令...")
        print("📝 发送命令到话题: /agent_node/user_command")
        print("=" * 60)
        
        while not rospy.is_shutdown():
            try:
                event_type, event_data = self.event_queue.get(timeout=1.0)
                
                if event_type == "stop":
                    rospy.logwarn("🛑 收到停止信号")
                    continue
                elif event_type == "command":
                    if event_data.lower() in ["q", "quit", "exit"]:
                        rospy.loginfo("👋 退出Agent")
                        break
                    
                    rospy.loginfo(f"📥 收到命令: {event_data}")
                    print(f"\n{'='*60}")
                    print(f"📥 收到命令: {event_data}")
                    print(f"{'='*60}\n")
                    
                    self.run_one_task(event_data)
                    
            except queue.Empty:
                continue
            except KeyboardInterrupt:
                rospy.loginfo("👋 键盘中断，退出Agent")
                break


if __name__ == "__main__":
    try:
        print("=" * 60)
        print("🚀 启动 Agent 节点...")
        print("=" * 60)
        
        agent = AgentRobot()
        
        print("✅ Agent 初始化完成")
        print("⏳ 等待1秒...")
        rospy.sleep(1)
        
        print("🤖 进入主循环，等待用户命令...")
        print("=" * 60)
        
        agent.run_loop()
        
    except Exception as e:
        print(f"\n❌ Agent 启动失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
