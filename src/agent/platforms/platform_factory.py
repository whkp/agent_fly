#!/usr/bin/env python3
"""
平台工厂

根据配置创建对应的平台实例
"""
import rospy
from .px4_sim_platform import PX4SimPlatform
from .px4_real_platform import PX4RealPlatform
from .cerlab_sim_platform import CERLABSimPlatform


class PlatformFactory:
    """平台工厂类"""
    
    # 支持的平台类型
    PLATFORMS = {
        'px4_sim': PX4SimPlatform,
        'px4_real': PX4RealPlatform,
        'cerlab_sim': CERLABSimPlatform,
        # 未来可以添加更多平台
        # 'dji': DJIPlatform,
        # 'ardupilot': ArduPilotPlatform,
    }
    
    @classmethod
    def create_platform(cls, platform_type, config):
        """
        创建平台实例
        
        Args:
            platform_type: 平台类型（'px4_sim', 'px4_real', 'cerlab_sim'）
            config: 平台配置字典
            
        Returns:
            BasePlatform: 平台实例
            
        Raises:
            ValueError: 不支持的平台类型
        """
        if platform_type not in cls.PLATFORMS:
            raise ValueError(
                f"不支持的平台类型: {platform_type}. "
                f"支持的类型: {list(cls.PLATFORMS.keys())}"
            )
        
        platform_class = cls.PLATFORMS[platform_type]
        rospy.loginfo(f"创建平台: {platform_type}")
        
        return platform_class(config)
    
    @classmethod
    def get_supported_platforms(cls):
        """获取支持的平台列表"""
        return list(cls.PLATFORMS.keys())
