#!/usr/bin/env python3
"""配置管理器 - 统一管理所有配置"""

import json
import os
import rospy

class ConfigManager:
    """统一配置管理"""
    
    def __init__(self, config_dir=None):
        if config_dir is None:
            config_dir = os.path.join(os.path.dirname(__file__), 'cfg')
        self.config_dir = config_dir
        self._configs = {}
        self._load_all_configs()
    
    def _load_all_configs(self):
        """加载所有配置文件"""
        config_files = {
            'tools': 'tools.json',
            'questions': 'questions.json',
        }
        
        for key, filename in config_files.items():
            filepath = os.path.join(self.config_dir, filename)
            if os.path.exists(filepath):
                with open(filepath, 'r', encoding='utf-8') as f:
                    self._configs[key] = json.load(f)
            else:
                rospy.logwarn(f"配置文件不存在: {filepath}")
                self._configs[key] = {}
    
    def get_tools(self):
        """获取工具配置"""
        return self._configs.get('tools', {}).get('tools', [])
    
    def get_enabled_tools(self):
        """获取启用的工具"""
        tools = self.get_tools()
        # 如果配置中有 activation 字段，则过滤
        if tools and 'activation' in tools[0]:
            return [t for t in tools if t.get('activation', True)]
        return tools
    
    def get_questions(self):
        """获取预设问题"""
        return self._configs.get('questions', {}).get('questions', [])
    
    def get_param(self, key, default=None):
        """获取参数（优先从 ROS 参数服务器）"""
        return rospy.get_param(f'~{key}', default)
    
    def reload(self):
        """重新加载配置"""
        rospy.loginfo("重新加载配置...")
        self._load_all_configs()
