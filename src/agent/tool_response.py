#!/usr/bin/env python3
"""统一的工具响应格式"""

class ToolResponse:
    """统一的工具返回格式，参考 typefly"""
    
    def __init__(self, success, message, data=None):
        self.success = success
        self.message = message
        self.data = data
    
    def to_dict(self):
        """转换为字典"""
        result = {
            "success": self.success,
            "message": self.message
        }
        if self.data is not None:
            result["data"] = self.data
        return result
    
    def to_legacy_format(self):
        """转换为旧格式（兼容现有代码）"""
        return {"result": self.message}
    
    @classmethod
    def ok(cls, message, data=None):
        """成功响应"""
        return cls(True, message, data)
    
    @classmethod
    def error(cls, message, data=None):
        """错误响应"""
        return cls(False, message, data)
    
    @classmethod
    def from_legacy(cls, legacy_result):
        """从旧格式转换"""
        if isinstance(legacy_result, dict) and 'result' in legacy_result:
            return cls(True, legacy_result['result'])
        return cls(True, str(legacy_result))
