"""
后端日志配置

- 控制台：stdout，便于在终端直接观察
- 文件：logs/web.log，按大小滚动，保留 5 份
"""
import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
LOG_FILE = LOG_DIR / "web.log"
MAX_BYTES = 10 * 1024 * 1024
BACKUP_COUNT = 5
LOG_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"


def setup_logging() -> None:
    """初始化后端日志（幂等，可重复调用）"""
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
    except OSError:
        return

    root = logging.getLogger()
    if getattr(root, "_lunwen_configured", False):
        return

    formatter = logging.Formatter(LOG_FORMAT, datefmt="%Y-%m-%d %H:%M:%S")

    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.INFO)
    console.setFormatter(formatter)

    try:
        file_handler = RotatingFileHandler(
            LOG_FILE, maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT, encoding="utf-8"
        )
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(formatter)
    except OSError:
        file_handler = None

    root.setLevel(logging.INFO)
    root.addHandler(console)
    if file_handler is not None:
        root.addHandler(file_handler)
    root._lunwen_configured = True


def get_logger(name: str = "lunwen") -> logging.Logger:
    setup_logging()
    return logging.getLogger(name)
