#!/usr/bin/env python3
"""
LLM 封装层

参考 typefly 设计，提供统一的 LLM 接口
"""
import os
from enum import Enum
from datetime import datetime
from langchain_openai import ChatOpenAI


class ModelType(Enum):
    """支持的模型类型"""
    QWEN_MAX = "qwen-max"
    QWEN3_MAX = "qwen3-max"
    GPT4 = "gpt-4"
    GPT4O = "gpt-4o"


class LLMWrapper:
    """
    LLM 封装类
    
    功能：
    - 统一的模型管理
    - 自动日志记录
    - API Key 检查
    """
    
    def __init__(self, model_type: ModelType | str = ModelType.QWEN3_MAX, temperature: float = 0.1):
        """
        初始化 LLM 封装
        
        Args:
            model_type: 模型类型
            temperature: 温度参数
        """
        # 检查 API Key
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise ValueError(
                "OPENAI_API_KEY 未设置。请设置环境变量：\n"
                "export OPENAI_API_KEY='your-api-key'"
            )
        
        # 检查 API Base（可选）
        api_base = os.environ.get("OPENAI_API_BASE")
        if not api_base:
            print("⚠️ OPENAI_API_BASE 未设置，使用默认值")
        
        # 模型类型
        if isinstance(model_type, ModelType):
            self.model_name = model_type.value
        else:
            self.model_name = model_type
        
        self.temperature = temperature
        
        # 创建 LangChain LLM
        self.llm = ChatOpenAI(
            model=self.model_name,
            temperature=self.temperature
        )
        
        # 日志文件
        log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
        os.makedirs(log_dir, exist_ok=True)
        self.log_file = os.path.join(log_dir, 'llm_chat_log.txt')
        
        print(f"✅ LLM 初始化完成: {self.model_name} (temperature={self.temperature})")
    
    def get_llm(self):
        """获取 LangChain LLM 对象"""
        return self.llm
    
    def log_interaction(self, prompt: str, response: str):
        """
        记录 LLM 交互日志
        
        Args:
            prompt: 输入提示词
            response: LLM 响应
        """
        try:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with open(self.log_file, "a", encoding='utf-8') as f:
                f.write(f"\n{'='*80}\n")
                f.write(f"[{timestamp}] Model: {self.model_name}\n")
                f.write(f"{'='*80}\n")
                f.write("PROMPT:\n")
                f.write(prompt + "\n")
                f.write(f"{'-'*80}\n")
                f.write("RESPONSE:\n")
                f.write(response + "\n")
                f.write(f"{'='*80}\n")
        except Exception as e:
            print(f"⚠️ 日志记录失败: {e}")
    
    @staticmethod
    def check_environment():
        """
        检查环境配置
        
        Returns:
            bool: 配置是否完整
        """
        api_key = os.environ.get("OPENAI_API_KEY")
        api_base = os.environ.get("OPENAI_API_BASE")
        
        if not api_key:
            print("❌ OPENAI_API_KEY 未设置")
            return False
        
        if not api_base:
            print("⚠️ OPENAI_API_BASE 未设置（使用默认值）")
        
        print("✅ 环境配置检查通过")
        return True
