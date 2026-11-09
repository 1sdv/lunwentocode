"""
日志工具

统一复用 server.logging_setup 的配置（控制台 + logs/web.log 文件），
避免同一日志在控制台输出两次。
"""
import logging

from app.config.settings import settings
from server.logging_setup import setup_logging


def setup_logger(name: str = "biyetocode") -> logging.Logger:
    """设置日志器"""
    setup_logging()
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO))
    # 交给 root logger 的 handler 输出（控制台 + 文件）
    logger.propagate = True
    return logger


logger = setup_logger()
