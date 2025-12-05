"""
系统配置文件
"""
from pydantic_settings import BaseSettings
from typing import Optional
import os


class Settings(BaseSettings):
    """系统配置"""
    
    # Mineru API 配置
    MINERU_API_TOKEN: str = ""
    MINERU_API_URL: str = "https://mineru.net/api/v4/extract/task"
    
    # 分析LLM配置（用于论文分析）
    ANALYZER_LLM_API_KEY: str = ""
    ANALYZER_LLM_MODEL: str = "intern-latest"
    ANALYZER_LLM_BASE_URL: Optional[str] = None
    
    # 代码LLM配置（用于代码生成和修复）
    CODER_LLM_API_KEY: str = ""
    CODER_LLM_MODEL: str = "intern-latest"
    CODER_LLM_BASE_URL: Optional[str] = None
    
    # 兼容旧配置（如果只设置一组，两个LLM使用相同配置）
    LLM_API_KEY: str = ""
    LLM_MODEL: str = "intern-latest"
    LLM_BASE_URL: Optional[str] = None
    
    # 代码执行配置
    MAX_CODE_RETRIES: int = 5  # 代码最大重试次数
    MAX_CHAT_TURNS: int = 30   # 最大对话轮次
    CODE_TIMEOUT: int = 300    # 代码执行超时(秒)
    
    # 路径配置
    UPLOAD_DIR: str = "uploads"
    OUTPUT_DIR: str = "output"
    
    # 日志配置
    LOG_LEVEL: str = "INFO"
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "allow"


settings = Settings()
