#!/usr/bin/env python3
"""
工具函数模块 - 将确定性逻辑从提示词移到代码层

包含：
- 坐标计算（安全接近点、方向向量等）
- 空间推理（距离、角度等）
- 数据转换
"""

import math
from typing import Tuple, Dict, Any, Optional


def calculate_approach_point(
    obj_pos: Tuple[float, float, float],
    cur_pos: Tuple[float, float, float],
    safe_distance: float = 2.0,
    min_height: float = 1.0,
    max_height: float = 15.0,
    obj_type: str = None
) -> Tuple[float, float, float]:
    """
    计算安全接近点 - 在物体前方保持安全距离
    
    **重要**: 导航是2D的（XY平面），z坐标保持当前飞行高度
    YOLO检测的z坐标不准确，应该忽略
    
    Args:
        obj_pos: 物体坐标 (x, y, z) - 只使用x,y
        cur_pos: 当前坐标 (x, y, z)
        safe_distance: 安全距离（米），默认2.0m避免导航算法因避障绕后方
        min_height: 最低安全高度（米）- 未使用
        max_height: 最高安全高度（米）- 未使用
        obj_type: 物体类型 - 未使用
    
    Returns:
        目标坐标 (x, y, z) - z保持当前高度
    """
    dx = obj_pos[0] - cur_pos[0]
    dy = obj_pos[1] - cur_pos[1]
    
    dist = math.sqrt(dx**2 + dy**2)
    
    # 如果已经足够近，返回当前位置
    if dist <= safe_distance:
        return cur_pos
    
    # 计算方向单位向量
    ratio = (dist - safe_distance) / dist
    
    target_x = cur_pos[0] + dx * ratio
    target_y = cur_pos[1] + dy * ratio
    
    # 保持当前飞行高度（2D导航）
    target_z = cur_pos[2]
    
    return (target_x, target_y, target_z)


def calculate_distance(pos1: Tuple[float, float, float], 
                       pos2: Tuple[float, float, float]) -> float:
    """计算两点之间的欧氏距离"""
    return math.sqrt(
        (pos1[0] - pos2[0])**2 + 
        (pos1[1] - pos2[1])**2 + 
        (pos1[2] - pos2[2])**2
    )


def calculate_direction_vector(
    from_pos: Tuple[float, float, float],
    to_pos: Tuple[float, float, float]
) -> Tuple[float, float]:
    """
    计算方向单位向量（2D）
    
    Returns:
        (dx, dy) 单位向量
    """
    dx = to_pos[0] - from_pos[0]
    dy = to_pos[1] - from_pos[1]
    dist = math.sqrt(dx**2 + dy**2)
    
    if dist < 0.01:  # 避免除零
        return (0.0, 0.0)
    
    return (dx / dist, dy / dist)


def calculate_relative_position(
    current_pos: Tuple[float, float, float],
    direction: str,
    distance: float = 3.0,
    current_yaw: float = 0.0
) -> Tuple[float, float, float]:
    """
    根据相对方向计算目标坐标
    
    Args:
        current_pos: 当前坐标
        direction: 方向 ("forward", "backward", "left", "right", "up", "down")
        distance: 移动距离
        current_yaw: 当前朝向角度（度）
    
    Returns:
        目标坐标 (x, y, z)
    """
    x, y, z = current_pos
    yaw_rad = math.radians(current_yaw)
    
    if direction == "forward":
        x += distance * math.cos(yaw_rad)
        y += distance * math.sin(yaw_rad)
    elif direction == "backward":
        x -= distance * math.cos(yaw_rad)
        y -= distance * math.sin(yaw_rad)
    elif direction == "left":
        x -= distance * math.sin(yaw_rad)
        y += distance * math.cos(yaw_rad)
    elif direction == "right":
        x += distance * math.sin(yaw_rad)
        y -= distance * math.cos(yaw_rad)
    elif direction == "up":
        z += distance
    elif direction == "down":
        z -= distance
    
    return (x, y, z)


def is_near_target(
    current_pos: Tuple[float, float, float],
    target_pos: Tuple[float, float, float],
    threshold: float = 0.5
) -> bool:
    """判断是否接近目标"""
    dist = calculate_distance(current_pos, target_pos)
    return dist < threshold


def format_position(pos: Tuple[float, float, float]) -> str:
    """格式化坐标为字符串"""
    return f"({pos[0]:.2f}, {pos[1]:.2f}, {pos[2]:.2f})"


def parse_object_detection_result(objects: list) -> Dict[str, Any]:
    """
    解析物体检测结果，提取关键信息
    
    Returns:
        {
            'count': int,
            'types': Dict[str, int],  # 物体类型统计
            'nearest': Dict,  # 最近的物体
            'by_type': Dict[str, list]  # 按类型分组
        }
    """
    if not objects:
        return {
            'count': 0,
            'types': {},
            'nearest': None,
            'by_type': {}
        }
    
    # 统计类型
    types = {}
    by_type = {}
    for obj in objects:
        obj_type = obj.get('name', 'unknown')
        types[obj_type] = types.get(obj_type, 0) + 1
        if obj_type not in by_type:
            by_type[obj_type] = []
        by_type[obj_type].append(obj)
    
    # 找最近的物体
    nearest = min(objects, key=lambda o: o.get('distance', float('inf')))
    
    return {
        'count': len(objects),
        'types': types,
        'nearest': nearest,
        'by_type': by_type
    }


def find_object_by_position(objects: list, target_pos: Tuple[float, float, float], tolerance: float = 0.5) -> Optional[Dict]:
    """
    根据位置查找物体（用于从检测结果中找到对应的物体类型）
    
    Args:
        objects: 检测到的物体列表
        target_pos: 目标位置 (x, y, z)
        tolerance: 位置容差（米）
    
    Returns:
        匹配的物体信息，如果没找到返回None
    """
    if not objects:
        return None
    
    for obj in objects:
        wc = obj.get('world_coordinates', {})
        obj_x = wc.get('x', 0)
        obj_y = wc.get('y', 0)
        
        # 只比较x和y坐标（z坐标可能不准确）
        dist = math.sqrt((obj_x - target_pos[0])**2 + (obj_y - target_pos[1])**2)
        
        if dist <= tolerance:
            return obj
    
    return None
