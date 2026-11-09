"""
Web 服务配置 - 面向公网部署的安全与资源限制

所有配置均可用环境变量覆盖（也支持 .env 文件）。
"""
from pathlib import Path
from typing import List, Optional

from pydantic_settings import BaseSettings

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class WebSettings(BaseSettings):
    """Web 服务配置"""

    # ---------- 访问控制 ----------
    # 站点访问令牌：设置后所有 API 请求需带 X-Access-Token 头（留空 = 不启用）
    SITE_TOKEN: str = ""
    # 允许的跨域来源（前后端同域部署时留空即可）
    CORS_ORIGINS: str = ""

    # ---------- 资源限制 ----------
    # 同时运行的任务数（每个任务会开一个 Jupyter 内核 + 一个工作线程）
    MAX_CONCURRENT_TASKS: int = 2
    # 单个上传文件大小上限（MB）
    MAX_UPLOAD_MB: int = 20
    # 单次任务允许上传的数据文件数量
    MAX_DATA_FILES: int = 10
    # 任务结果保留时长（小时），超时后清理工作目录
    TASK_TTL_HOURS: int = 24
    # 每个 IP 每分钟允许发起的任务数
    RATE_LIMIT_PER_MINUTE: int = 5

    # ---------- 路径 ----------
    # 任务产出根目录（每个任务在其下建独立子目录）
    OUTPUT_ROOT: str = str(PROJECT_ROOT / "web_output")
    # 站点展示页目录
    SITE_DIR: str = str(PROJECT_ROOT / "site")
    # 应用界面目录
    WEB_DIR: str = str(PROJECT_ROOT / "web")
    # 上传临时目录
    UPLOAD_ROOT: str = str(PROJECT_ROOT / "web_uploads")
    # 演示用产出目录（"运行示例"按钮读取此目录，展示一次真实运行的结果）
    DEMO_DIR: str = str(PROJECT_ROOT / "output" / "20261109_111122_91dfac")
    # 演示任务的虚拟 ID
    DEMO_TASK_ID: str = "demo_20261109_111122_91dfac"

    # ---------- 默认模型 ----------
    DEFAULT_ANALYZER_MODEL: str = "gpt-4o"
    DEFAULT_CODER_MODEL: str = "gpt-4o"
    DEFAULT_WRITER_MODEL: str = ""
    DEFAULT_BASE_URL: str = ""

    class Config:
        env_file = str(PROJECT_ROOT / ".env")
        env_file_encoding = "utf-8"
        extra = "allow"

    # ---------- 派生属性 ----------

    @property
    def cors_origin_list(self) -> List[str]:
        if not self.CORS_ORIGINS.strip():
            return []
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def max_upload_bytes(self) -> int:
        return self.MAX_UPLOAD_MB * 1024 * 1024

    def ensure_dirs(self) -> None:
        for path in (self.OUTPUT_ROOT, self.UPLOAD_ROOT):
            Path(path).mkdir(parents=True, exist_ok=True)


web_settings = WebSettings()
