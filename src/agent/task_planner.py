#!/usr/bin/env python3
"""
任务规划器 - 将高级指令分解为可执行的子任务序列

解决问题：
1. 提供显式的任务规划能力
2. 可追踪任务执行进度
3. 论文可量化"规划能力"
"""

from typing import List, Dict, Any, Optional
from enum import Enum
import rospy


class SubTaskType(Enum):
    """子任务类型"""
    TAKEOFF = "takeoff"
    LAND = "land"
    NAVIGATE = "navigate"
    ROTATE_SEARCH = "rotate_search"
    DETECT_OBJECTS = "detect_objects"
    WAIT = "wait"


class SubTask:
    """子任务"""
    def __init__(self, task_type: SubTaskType, params: Dict[str, Any], description: str = ""):
        self.type = task_type
        self.params = params
        self.description = description
        self.status = "pending"  # pending, running, completed, failed
        self.result = None
    
    def __repr__(self):
        return f"SubTask({self.type.value}, {self.params}, status={self.status})"


class TaskPlanner:
    """
    任务规划器 - 将高级指令分解为子任务序列
    
    示例：
        "搜索房间里的人" → [
            SubTask(ROTATE_SEARCH, {angle: 360}),
            SubTask(NAVIGATE, {x: 5, y: 0}),
            SubTask(ROTATE_SEARCH, {angle: 360}),
            ...
        ]
    """
    
    def __init__(self):
        self.current_plan = []
        self.current_index = 0
        self.search_positions_visited = []  # 记录已搜索的位置
        
        # 环境参数（可通过ROS参数配置）
        self.room_size = rospy.get_param('~room_size', 10.0)  # 房间大小（米）
        self.search_step = rospy.get_param('~search_step', 4.0)  # 搜索步长（米）
        self.patrol_radius = rospy.get_param('~patrol_radius', 6.0)  # 巡视半径（米）
        self.max_range = self.room_size * 0.8  # 最大活动范围（房间大小的80%）
        
        rospy.loginfo(f"📐 TaskPlanner配置: 房间{self.room_size}m, 搜索步长{self.search_step}m, 巡视半径{self.patrol_radius}m")
    
    def decompose(self, instruction: str, context: Dict[str, Any]) -> List[SubTask]:
        """
        将高级指令分解为子任务序列
        
        Args:
            instruction: 用户指令
            context: 上下文信息（当前位置、状态等）
        
        Returns:
            子任务列表
        """
        instruction_lower = instruction.lower()
        
        # 分类任务类型
        task_type = self._classify_task(instruction_lower)
        rospy.loginfo(f"🔍 任务分类: '{instruction}' → {task_type}")
        
        if task_type == "search":
            return self._generate_search_plan(instruction_lower, context)
        elif task_type == "navigate":
            return self._generate_nav_plan(instruction_lower, context)
        elif task_type == "patrol":
            return self._generate_patrol_plan(instruction_lower, context)
        elif task_type == "simple":
            return self._generate_simple_plan(instruction_lower, context)
        else:
            # 默认：单步任务，交给LLM处理
            rospy.loginfo(f"ℹ️ 未识别的任务类型，交给LLM处理")
            return []
    
    def _classify_task(self, instruction: str) -> str:
        """分类任务类型"""
        # 简单指令（优先级最高，避免被其他类型误判）
        if any(kw in instruction for kw in ["起飞", "降落", "旋转", "takeoff", "land", "rotate"]):
            return "simple"
        # 搜索任务
        elif any(kw in instruction for kw in ["搜索", "找", "寻找", "找到", "search", "find", "locate"]):
            return "search"
        # 巡视任务
        elif any(kw in instruction for kw in ["巡视", "巡逻", "巡检", "检查", "patrol", "inspect", "survey"]):
            return "patrol"
        # 导航任务（需要排除搜索和简单指令）
        elif any(kw in instruction for kw in ["飞到", "导航", "移动到", "go to", "navigate", "move to"]) and \
             not any(kw in instruction for kw in ["搜索", "找", "寻找", "起飞", "降落"]):
            return "navigate"
        else:
            return "unknown"
    
    def _generate_search_plan(self, instruction: str, context: Dict[str, Any]) -> List[SubTask]:
        """
        生成搜索任务计划
        
        策略：网格搜索
        1. 当前位置 360° 旋转搜索
        2. 移动到新位置
        3. 重复
        """
        plan = []
        current_pos = context.get('position', (0, 0, 1.5))
        
        # 定义搜索点（相对于当前位置）
        # 策略：十字形搜索 + 对角线
        search_offsets = [
            (0, 0),                          # 当前位置
            (self.search_step, 0),           # 前方
            (self.search_step, self.search_step),  # 右前
            (0, self.search_step),           # 右侧
            (-self.search_step, self.search_step), # 右后
            (-self.search_step, 0),          # 后方
        ]
        
        for i, (dx, dy) in enumerate(search_offsets):
            target_x = current_pos[0] + dx
            target_y = current_pos[1] + dy
            target_z = current_pos[2]
            
            # 边界检查：限制在最大范围内
            if abs(target_x) > self.max_range or abs(target_y) > self.max_range:
                rospy.logwarn(f"⚠️ 搜索点 ({target_x:.1f}, {target_y:.1f}) 超出范围±{self.max_range:.1f}m，跳过")
                continue
            
            # 如果不是当前位置，先导航
            if i > 0:
                plan.append(SubTask(
                    SubTaskType.NAVIGATE,
                    {'x': target_x, 'y': target_y, 'z': target_z},
                    f"移动到搜索点 {i+1}"
                ))
            
            # 360° 旋转搜索（6次 × 60°）
            for j in range(6):
                plan.append(SubTask(
                    SubTaskType.ROTATE_SEARCH,
                    {'angle': 60},
                    f"搜索点 {i+1} - 旋转 {(j+1)*60}°"
                ))
        
        rospy.loginfo(f"📋 生成搜索计划：{len(plan)} 个子任务")
        return plan
    
    def _generate_patrol_plan(self, instruction: str, context: Dict[str, Any]) -> List[SubTask]:
        """
        生成巡视任务计划
        
        策略：矩形巡视路径
        """
        plan = []
        current_pos = context.get('position', (0, 0, 1.5))
        
        # 定义巡视路径（矩形，8个点）
        patrol_points = [
            (self.patrol_radius, 0, 1.5),
            (self.patrol_radius, self.patrol_radius, 1.5),
            (0, self.patrol_radius, 1.5),
            (-self.patrol_radius, self.patrol_radius, 1.5),
            (-self.patrol_radius, 0, 1.5),
            (-self.patrol_radius, -self.patrol_radius, 1.5),
            (0, -self.patrol_radius, 1.5),
            (self.patrol_radius, -self.patrol_radius, 1.5),
        ]
        
        for i, (x, y, z) in enumerate(patrol_points):
            # 边界检查
            if abs(x) > self.max_range or abs(y) > self.max_range:
                rospy.logwarn(f"⚠️ 巡视点 ({x:.1f}, {y:.1f}) 超出范围±{self.max_range:.1f}m，跳过")
                continue
            
            # 导航到巡视点
            plan.append(SubTask(
                SubTaskType.NAVIGATE,
                {'x': x, 'y': y, 'z': z},
                f"巡视点 {i+1}"
            ))
            
            # 360° 检测（可选：只检测关键方向以节省时间）
            # 这里保持360°全方位检测
            for j in range(6):
                plan.append(SubTask(
                    SubTaskType.ROTATE_SEARCH,
                    {'angle': 60},
                    f"巡视点 {i+1} - 旋转 {(j+1)*60}°"
                ))
        
        rospy.loginfo(f"📋 生成巡视计划：{len(plan)} 个子任务")
        return plan
    
    def _generate_nav_plan(self, instruction: str, context: Dict[str, Any]) -> List[SubTask]:
        """生成导航任务计划（简单导航）"""
        # 导航任务通常由 LLM 直接处理，这里返回空列表
        return []
    
    def _generate_simple_plan(self, instruction: str, context: Dict[str, Any]) -> List[SubTask]:
        """生成简单任务计划（起飞、降落等）"""
        # 简单任务由 LLM 直接处理
        return []
    
    def get_next_subtask(self) -> Optional[SubTask]:
        """获取下一个待执行的子任务"""
        if self.current_index >= len(self.current_plan):
            return None
        
        task = self.current_plan[self.current_index]
        if task.status == "pending":
            return task
        
        # 跳过已完成的任务
        self.current_index += 1
        return self.get_next_subtask()
    
    def mark_completed(self, result: Any = None):
        """标记当前子任务为完成"""
        if self.current_index < len(self.current_plan):
            self.current_plan[self.current_index].status = "completed"
            self.current_plan[self.current_index].result = result
            self.current_index += 1
    
    def mark_failed(self, reason: str = ""):
        """标记当前子任务为失败"""
        if self.current_index < len(self.current_plan):
            self.current_plan[self.current_index].status = "failed"
            self.current_plan[self.current_index].result = reason
            self.current_index += 1
    
    def get_progress(self) -> Dict[str, Any]:
        """获取任务进度"""
        total = len(self.current_plan)
        completed = sum(1 for t in self.current_plan if t.status == "completed")
        failed = sum(1 for t in self.current_plan if t.status == "failed")
        
        return {
            'total': total,
            'completed': completed,
            'failed': failed,
            'current_index': self.current_index,
            'progress_percent': (completed / total * 100) if total > 0 else 0
        }
    
    def reset(self):
        """重置规划器"""
        self.current_plan = []
        self.current_index = 0
        self.search_positions_visited = []
