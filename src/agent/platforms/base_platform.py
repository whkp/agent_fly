#!/usr/bin/env python3
"""
基础平台接口

定义所有平台必须实现的接口
"""
from abc import ABC, abstractmethod
import rospy
from geometry_msgs.msg import PoseStamped
from quadrotor_msgs.msg import PositionCommand, TakeoffLand


class BasePlatform(ABC):
    """
    基础平台接口
    
    所有平台（仿真、真机）都必须实现这个接口
    """
    
    def __init__(self, config):
        """
        初始化平台
        
        Args:
            config: 平台配置字典
        """
        self.config = config
        self.odom = None
        self.mavros_state = None
        
    @abstractmethod
    def init_ros(self):
        """初始化 ROS 订阅和发布"""
        pass
    
    @abstractmethod
    def takeoff(self, height):
        """
        起飞到指定高度
        
        Args:
            height: 目标高度（米）
            
        Returns:
            dict: {"success": bool, "message": str}
        """
        pass
    
    @abstractmethod
    def land(self):
        """
        降落到地面
        
        Returns:
            dict: {"success": bool, "message": str}
        """
        pass
    
    @abstractmethod
    def set_goal(self, x, y, z, yaw):
        """
        设置目标点
        
        Args:
            x, y, z: 目标坐标（米）
            yaw: 目标偏航角（弧度）
            
        Returns:
            dict: {"success": bool, "message": str}
        """
        pass
    
    @abstractmethod
    def get_current_position(self):
        """
        获取当前位置
        
        Returns:
            dict: {"x": float, "y": float, "z": float, "yaw": float}
        """
        pass
    
    @abstractmethod
    def get_flight_status(self):
        """
        获取飞行状态
        
        Returns:
            str: IDLE/TAKEOFF/HOVER/NAVIGATE/LAND
        """
        pass
    
    # 可选方法（有默认实现）
    
    def wait_for_data(self, timeout=30.0):
        """等待数据就绪"""
        rospy.loginfo("等待数据...")
        rate = rospy.Rate(10)
        timeout_time = rospy.Time.now() + rospy.Duration(timeout)
        while not rospy.is_shutdown():
            if self._is_data_ready():
                rospy.loginfo("✅ 数据就绪")
                return True
            if rospy.Time.now() > timeout_time:
                rospy.logwarn("⚠️ 数据等待超时")
                return False
            rate.sleep()
        return False
    
    def _is_data_ready(self):
        """检查数据是否就绪（子类可重写）"""
        return self.odom is not None
