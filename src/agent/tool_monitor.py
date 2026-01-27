#!/usr/bin/env python3
"""工具调用监控模块"""

import time
from collections import defaultdict
from datetime import datetime
import threading

class ToolMonitor:
    """工具调用监控和统计"""
    
    def __init__(self, max_history=100):
        self.max_history = max_history
        self.call_history = []
        self.call_stats = defaultdict(lambda: {
            'total_calls': 0,
            'success_calls': 0,
            'failed_calls': 0,
            'total_duration': 0.0,
            'avg_duration': 0.0,
            'last_call': None
        })
        self.lock = threading.Lock()
    
    def record_call(self, tool_name, params, success, message, duration, data=None):
        """记录工具调用"""
        with self.lock:
            # 记录历史
            record = {
                'timestamp': datetime.now().isoformat(),
                'tool_name': tool_name,
                'params': params,
                'success': success,
                'message': message,
                'duration': round(duration, 3),
                'data': data
            }
            self.call_history.append(record)
            
            # 限制历史记录数量
            if len(self.call_history) > self.max_history:
                self.call_history = self.call_history[-self.max_history:]
            
            # 更新统计
            stats = self.call_stats[tool_name]
            stats['total_calls'] += 1
            if success:
                stats['success_calls'] += 1
            else:
                stats['failed_calls'] += 1
            stats['total_duration'] += duration
            stats['avg_duration'] = stats['total_duration'] / stats['total_calls']
            stats['last_call'] = datetime.now().isoformat()
    
    def get_history(self, limit=20):
        """获取调用历史"""
        with self.lock:
            return self.call_history[-limit:]
    
    def get_stats(self):
        """获取统计信息"""
        with self.lock:
            return dict(self.call_stats)
    
    def get_tool_stats(self, tool_name):
        """获取特定工具的统计"""
        with self.lock:
            return self.call_stats.get(tool_name, None)
    
    def clear_history(self):
        """清除历史记录"""
        with self.lock:
            self.call_history = []
    
    def reset_stats(self):
        """重置统计"""
        with self.lock:
            self.call_stats.clear()
