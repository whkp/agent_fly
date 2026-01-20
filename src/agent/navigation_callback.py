#!/usr/bin/env python3
"""
导航回调管理器 - 解决导航闭环反馈问题

功能：
1. 监控导航状态
2. 导航完成后触发回调
3. 支持多点导航序列
"""

import rospy
import threading
import time
from typing import Callable, Optional, Dict, Any
from enum import Enum


class NavigationStatus(Enum):
    """导航状态"""
    IDLE = "idle"
    NAVIGATING = "navigating"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"


class NavigationCallback:
    """
    导航回调管理器
    
    使用方式：
        nav_callback = NavigationCallback()
        nav_callback.start_navigation(
            goal={'x': 5, 'y': 0, 'z': 1.5},
            on_complete=lambda: print("到达！"),
            on_fail=lambda reason: print(f"失败：{reason}")
        )
    """
    
    def __init__(self, agent_tools):
        self.agent_tools = agent_tools
        self.status = NavigationStatus.IDLE
        self.current_goal = None
        self.start_time = None
        self.timeout = 60.0  # 默认超时时间
        
        # 回调函数
        self.on_complete_callback = None
        self.on_fail_callback = None
        
        # 线程锁
        self.lock = threading.Lock()
        
        # 监控线程
        self.monitor_thread = None
        self.stop_monitor = False
    
    def start_navigation(
        self,
        goal: Dict[str, float],
        on_complete: Optional[Callable] = None,
        on_fail: Optional[Callable[[str], None]] = None,
        timeout: float = 60.0
    ):
        """
        开始导航并设置回调
        
        Args:
            goal: 目标坐标 {'x': float, 'y': float, 'z': float}
            on_complete: 完成回调
            on_fail: 失败回调（参数为失败原因）
            timeout: 超时时间（秒）
        """
        with self.lock:
            self.status = NavigationStatus.NAVIGATING
            self.current_goal = goal
            self.start_time = time.time()
            self.timeout = timeout
            self.on_complete_callback = on_complete
            self.on_fail_callback = on_fail
        
        # 启动监控线程
        if self.monitor_thread is None or not self.monitor_thread.is_alive():
            self.stop_monitor = False
            self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
            self.monitor_thread.start()
        
        rospy.loginfo(f"🚁 开始导航到 ({goal['x']:.1f}, {goal['y']:.1f}, {goal['z']:.1f})")
    
    def _monitor_loop(self):
        """监控导航状态（后台线程）"""
        rate = rospy.Rate(5)  # 5Hz
        
        while not rospy.is_shutdown() and not self.stop_monitor:
            with self.lock:
                if self.status != NavigationStatus.NAVIGATING:
                    break
                
                # 检查超时
                if self.start_time and time.time() - self.start_time > self.timeout:
                    rospy.logwarn("⏱️ 导航超时")
                    self.status = NavigationStatus.TIMEOUT
                    if self.on_fail_callback:
                        try:
                            self.on_fail_callback("timeout")
                        except Exception as e:
                            rospy.logerr(f"失败回调执行异常: {e}")
                    break
                
                # 检查是否到达（不依赖flight_status）
                if self.current_goal:
                    current_state = self.agent_tools.get_status_dict()
                    
                    # 计算距离
                    dx = current_state['x'] - self.current_goal.get('x', 0)
                    dy = current_state['y'] - self.current_goal.get('y', 0)
                    dz = current_state['z'] - self.current_goal.get('z', 0)
                    dist_xy = (dx**2 + dy**2) ** 0.5
                    dist_3d = (dx**2 + dy**2 + dz**2) ** 0.5
                    
                    # 到达判断：XY平面距离 < 0.8m 且 Z轴距离 < 0.3m
                    if dist_xy < 0.8 and abs(dz) < 0.3:
                        elapsed = time.time() - self.start_time
                        rospy.loginfo(f"✅ 导航完成（用时 {elapsed:.1f}s，XY误差 {dist_xy:.2f}m，Z误差 {abs(dz):.2f}m）")
                        self.status = NavigationStatus.COMPLETED
                        
                        # 触发完成回调
                        if self.on_complete_callback:
                            try:
                                self.on_complete_callback()
                            except Exception as e:
                                rospy.logerr(f"完成回调执行失败: {e}")
                        break
            
            rate.sleep()
    
    def cancel(self):
        """取消当前导航"""
        with self.lock:
            if self.status == NavigationStatus.NAVIGATING:
                self.status = NavigationStatus.FAILED
                self.stop_monitor = True
                
                # 清空目标和回调
                self.current_goal = None
                self.on_complete_callback = None
                self.on_fail_callback = None
                
                rospy.loginfo("🛑 导航已取消")
                
                # 注意：这里不发送悬停指令，因为：
                # 1. navigation_node 会在目标点被清除后自动悬停
                # 2. 或者新任务会立即发送新的导航指令
                # 如果需要立即悬停，可以在这里调用 agent_tools 的悬停功能
    
    def get_status(self) -> NavigationStatus:
        """获取当前导航状态"""
        with self.lock:
            return self.status
    
    def is_navigating(self) -> bool:
        """是否正在导航"""
        with self.lock:
            return self.status == NavigationStatus.NAVIGATING
    
    def reset(self):
        """重置状态"""
        with self.lock:
            self.status = NavigationStatus.IDLE
            self.current_goal = None
            self.start_time = None
            self.on_complete_callback = None
            self.on_fail_callback = None
            self.stop_monitor = True


class NavigationSequence:
    """
    多点导航序列管理器
    
    使用方式：
        seq = NavigationSequence(nav_callback)
        seq.add_waypoint({'x': 5, 'y': 0, 'z': 1.5})
        seq.add_waypoint({'x': 5, 'y': 5, 'z': 1.5})
        seq.start(on_all_complete=lambda: print("全部完成！"))
    """
    
    def __init__(self, nav_callback: NavigationCallback):
        self.nav_callback = nav_callback
        self.waypoints = []
        self.current_index = 0
        self.on_all_complete_callback = None
    
    def add_waypoint(self, goal: Dict[str, float]):
        """添加航点"""
        self.waypoints.append(goal)
    
    def start(self, on_all_complete: Optional[Callable] = None):
        """开始执行导航序列"""
        self.current_index = 0
        self.on_all_complete_callback = on_all_complete
        self._navigate_next()
    
    def _navigate_next(self):
        """导航到下一个航点"""
        if self.current_index >= len(self.waypoints):
            # 全部完成
            rospy.loginfo("🎉 导航序列全部完成")
            if self.on_all_complete_callback:
                self.on_all_complete_callback()
            return
        
        goal = self.waypoints[self.current_index]
        rospy.loginfo(f"📍 导航到航点 {self.current_index + 1}/{len(self.waypoints)}")
        
        self.nav_callback.start_navigation(
            goal=goal,
            on_complete=self._on_waypoint_complete,
            on_fail=self._on_waypoint_fail
        )
    
    def _on_waypoint_complete(self):
        """航点完成回调"""
        self.current_index += 1
        self._navigate_next()
    
    def _on_waypoint_fail(self, reason: str):
        """航点失败回调"""
        rospy.logerr(f"❌ 航点 {self.current_index + 1} 导航失败: {reason}")
        # 可以选择：1) 跳过继续 2) 终止序列
        # 这里选择终止
        if self.on_all_complete_callback:
            self.on_all_complete_callback()
    
    def reset(self):
        """重置序列"""
        self.waypoints = []
        self.current_index = 0
        self.on_all_complete_callback = None
