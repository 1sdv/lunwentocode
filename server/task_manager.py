"""
任务管理器 - 任务注册、并发控制、事件流广播

每个任务对应一个后台线程（内含 asyncio loop 执行工作流），
通过内存中的 asyncio.Queue 向 SSE 订阅者广播进度事件。
"""
import asyncio
import shutil
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core.events import EventBus
from app.core.llm import LLM
from app.core.workflow import ThesisToCodeWorkflow
from app.utils.logger import logger

from server.config import web_settings


@dataclass
class TaskRecord:
    """一个生成任务的完整状态"""

    task_id: str
    status: str = "pending"  # pending / running / done / error
    created_at: float = field(default_factory=time.time)
    finished_at: Optional[float] = None
    title: str = ""
    message: str = ""
    progress: int = 0  # 0-100
    events: List[Dict[str, Any]] = field(default_factory=list)
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    _queue: "asyncio.Queue[Optional[Dict[str, Any]]]" = field(
        default_factory=lambda: asyncio.Queue(maxsize=1000)
    )
    _thread: Optional[threading.Thread] = None

    def public_dict(self) -> Dict[str, Any]:
        """对外暴露的状态（不含内部队列）"""
        return {
            "task_id": self.task_id,
            "status": self.status,
            "title": self.title,
            "message": self.message,
            "progress": self.progress,
            "created_at": self.created_at,
            "finished_at": self.finished_at,
            "error": self.error,
        }


# 事件类型 → 展示前缀与进度权重
EVENT_PREFIX = {
    "system": "◆",
    "code": "▶",
    "code_output": "›",
    "report": "✎",
    "error": "✕",
}

# 打包时跳过这些：Python 缓存与临时文件，对交付无意义
_ZIP_EXCLUDE_DIRS = {"__pycache__", ".ipynb_checkpoints", ".git"}
_ZIP_EXCLUDE_SUFFIX = (".pyc", ".pyo", ".tmp")


def _make_project_zip(archive_base: Path, work_dir: Path) -> Path:
    """把产出目录打包成 zip（跳过缓存文件），返回 zip 路径"""
    import zipfile

    zip_path = Path(f"{archive_base}.zip")
    tmp_path = Path(f"{archive_base}.tmp.zip")
    with zipfile.ZipFile(
        tmp_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6
    ) as zf:
        for path in sorted(work_dir.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(work_dir)
            if any(part in _ZIP_EXCLUDE_DIRS for part in rel.parts):
                continue
            if path.suffix in _ZIP_EXCLUDE_SUFFIX:
                continue
            zf.write(path, arcname=str(rel))
    tmp_path.replace(zip_path)
    return zip_path


class TaskManager:
    """全局任务管理器（进程内单例）"""

    def __init__(self) -> None:
        self._tasks: Dict[str, TaskRecord] = {}
        self._lock = threading.Lock()
        self._semaphore = threading.Semaphore(web_settings.MAX_CONCURRENT_TASKS)
        # 每个 IP 的请求时间戳，用于简单限流
        self._rate: Dict[str, List[float]] = {}
        self._rate_lock = threading.Lock()

    # ---------------------------------------------------------------- 限流

    def check_rate_limit(self, client_ip: str) -> bool:
        """返回 True 表示允许发起任务"""
        now = time.time()
        window = 60.0
        with self._rate_lock:
            stamps = [t for t in self._rate.get(client_ip, []) if now - t < window]
            if len(stamps) >= web_settings.RATE_LIMIT_PER_MINUTE:
                self._rate[client_ip] = stamps
                return False
            stamps.append(now)
            self._rate[client_ip] = stamps
            return True

    # ---------------------------------------------------------------- 任务

    def get(self, task_id: str) -> Optional[TaskRecord]:
        with self._lock:
            return self._tasks.get(task_id)

    def list_recent(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._lock:
            records = sorted(self._tasks.values(), key=lambda r: r.created_at, reverse=True)
        return [r.public_dict() for r in records[:limit]]

    def active_count(self) -> int:
        with self._lock:
            return sum(1 for r in self._tasks.values() if r.status in ("pending", "running"))

    def submit(
        self,
        proposal_path: str,
        data_paths: List[str],
        api_key: str,
        analyzer_model: str,
        coder_model: str,
        writer_model: str,
        base_url: str,
    ) -> TaskRecord:
        """创建并启动一个后台任务"""
        task_id = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        record = TaskRecord(task_id=task_id, status="pending")
        with self._lock:
            self._tasks[task_id] = record

        thread = threading.Thread(
            target=self._run_task,
            args=(
                record,
                proposal_path,
                data_paths,
                api_key,
                analyzer_model,
                coder_model,
                writer_model,
                base_url,
            ),
            daemon=True,
            name=f"task-{task_id}",
        )
        record._thread = thread
        thread.start()
        logger.info(f"[{task_id}] 任务已提交")
        return record

    # ---------------------------------------------------------------- 执行

    def _run_task(
        self,
        record: TaskRecord,
        proposal_path: str,
        data_paths: List[str],
        api_key: str,
        analyzer_model: str,
        coder_model: str,
        writer_model: str,
        base_url: str,
    ) -> None:
        acquired = self._semaphore.acquire(timeout=3600)
        try:
            if not acquired:
                self._finish_error(record, "服务器繁忙：等待超时，请稍后重试")
                return

            record.status = "running"
            self._emit(record, "system", f"任务开始：{record.task_id}")

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                result = loop.run_until_complete(
                    self._execute(
                        record,
                        proposal_path,
                        data_paths,
                        api_key,
                        analyzer_model,
                        coder_model,
                        writer_model,
                        base_url,
                    )
                )
                record.result = result
                record.status = "done"
                record.progress = 100
                record.message = "论文初稿生成完成"
                self._emit(record, "system", "任务完成")
            except Exception as exc:  # noqa: BLE001
                logger.exception(f"[{record.task_id}] 任务失败")
                self._finish_error(record, self._error_text(exc))
            finally:
                loop.close()
        finally:
            if acquired:
                self._semaphore.release()
            record.finished_at = time.time()
            self._close_queue(record)

    async def _execute(
        self,
        record: TaskRecord,
        proposal_path: str,
        data_paths: List[str],
        api_key: str,
        analyzer_model: str,
        coder_model: str,
        writer_model: str,
        base_url: str,
    ) -> Dict[str, Any]:
        bus = EventBus()
        bus.subscribe(lambda ev: self._on_event(record, ev))

        task_root = Path(web_settings.OUTPUT_ROOT) / record.task_id
        task_root.mkdir(parents=True, exist_ok=True)
        work_dir = task_root / "project"

        # 数据文件统一拷入任务目录（原始上传目录稍后清理）
        data_dir = None
        if data_paths:
            data_dir = task_root / "data"
            data_dir.mkdir(exist_ok=True)
            for p in data_paths:
                src = Path(p)
                if src.exists():
                    shutil.copy2(src, data_dir / src.name)

        # LLM 失败回调由工作流统一绑定（错误会推送到事件总线，前端终端可见）
        analyzer_llm = LLM(
            api_key=api_key,
            model=analyzer_model or web_settings.DEFAULT_ANALYZER_MODEL,
            base_url=base_url or web_settings.DEFAULT_BASE_URL or None,
        )
        coder_llm = LLM(
            api_key=api_key,
            model=coder_model or web_settings.DEFAULT_CODER_MODEL,
            base_url=base_url or web_settings.DEFAULT_BASE_URL or None,
        )
        writer_llm = LLM(
            api_key=api_key,
            model=writer_model or analyzer_model or web_settings.DEFAULT_WRITER_MODEL,
            base_url=base_url or web_settings.DEFAULT_BASE_URL or None,
        )

        workflow = ThesisToCodeWorkflow(
            analyzer_llm=analyzer_llm,
            coder_llm=coder_llm,
            writer_llm=writer_llm,
            event_bus=bus,
        )
        result = await workflow.run(
            md_path=proposal_path,
            data_dir=str(data_dir) if data_dir else None,
            output_dir=str(work_dir),
        )

        # 工作流会在 output_dir 下再建一层以自身 task_id 命名的目录，
        # 真正的产物（paper.md / 图表 / 代码）都在那一层里。
        real_work_dir = self._resolve_work_dir(work_dir)

        # 打包整个产出目录供下载（压缩包内为扁平结构，跳过缓存与临时文件）
        archive_base = task_root / "project"
        zip_path = _make_project_zip(archive_base, real_work_dir)

        success = sum(1 for r in result.task_results if r.success)
        total = len(result.task_results)
        return {
            "task_id": record.task_id,
            "title": result.thesis_title or "论文初稿",
            "report": result.report.full_report,
            "requirements": result.requirements,
            "sections": [
                {"key": k, "chars": len(v)} for k, v in result.report.sections.items()
            ],
            "tasks_total": total,
            "tasks_success": success,
            "notebook": result.notebook_file,
            "readme": result.readme,
            "zip_name": Path(zip_path).name,
            "zip_size": Path(zip_path).stat().st_size,
            "files": sorted(p.name for p in real_work_dir.iterdir() if p.is_file()),
        }

    @staticmethod
    def _resolve_work_dir(work_dir: Path) -> Path:
        """定位真正的产物目录。

        工作流输出结构为 <base>/<workflow_task_id>/，产物都在其中；
        若未来结构变扁平，则直接返回 base。
        """
        if not work_dir.exists():
            return work_dir
        # 已有文件 → 扁平结构，直接用
        if any(p.is_file() for p in work_dir.iterdir()):
            return work_dir
        # 否则找唯一的一级子目录
        subdirs = [p for p in work_dir.iterdir() if p.is_dir()]
        if len(subdirs) == 1:
            return subdirs[0]
        return work_dir

    # ---------------------------------------------------------------- 事件

    def _on_event(self, record: TaskRecord, event: Dict[str, Any]) -> None:
        etype = event.get("type", "system")
        content = event.get("content", "")
        self._emit(record, etype, content)

    def _emit(self, record: TaskRecord, etype: str, content: str) -> None:
        payload = {
            "type": etype,
            "prefix": EVENT_PREFIX.get(etype, "•"),
            "content": content,
            "time": time.time(),
        }
        record.events.append(payload)
        # 进度估算：system 阶段推进 5-85%，report 阶段推进到 95%
        self._advance_progress(record, etype, content)
        try:
            record._queue.put_nowait(payload)
        except asyncio.QueueFull:
            logger.warning(f"[{record.task_id}] 事件队列已满，丢弃一条")

    def _advance_progress(self, record: TaskRecord, etype: str, content: str) -> None:
        if record.status != "running":
            return
        if etype == "system":
            if "Phase 1" in content:
                record.progress = max(record.progress, 8)
            elif "Phase 2" in content:
                record.progress = max(record.progress, 14)
            elif "Phase 3" in content:
                record.progress = max(record.progress, 25)
            elif "Phase 4" in content:
                record.progress = max(record.progress, 35)
            elif "Phase 5" in content:
                record.progress = max(record.progress, 45)
            elif "Phase 6" in content:
                record.progress = max(record.progress, 88)
            elif "任务完成" in content:
                record.progress = 95
        elif etype == "report":
            record.progress = max(record.progress, min(94, record.progress + 3))
        record.message = content.split("\n")[0][:200]

    @staticmethod
    def _error_text(exc: Exception) -> str:
        """生成面向用户的错误文案

        RuntimeError 的内容本身已经是可读的中文提示，
        不再重复拼接异常类名。
        """
        if isinstance(exc, RuntimeError):
            return str(exc)
        return f"{type(exc).__name__}: {exc}"

    def _finish_error(self, record: TaskRecord, message: str) -> None:
        record.status = "error"
        record.error = message
        record.message = message
        self._emit(record, "error", message)

    def _close_queue(self, record: TaskRecord) -> None:
        try:
            record._queue.put_nowait(None)
        except asyncio.QueueFull:
            pass

    # ---------------------------------------------------------------- 清理

    def cleanup_expired(self) -> int:
        """清理超过保留期的任务目录"""
        ttl = web_settings.TASK_TTL_HOURS * 3600
        now = time.time()
        removed = 0
        root = Path(web_settings.OUTPUT_ROOT)
        if not root.exists():
            return 0
        for child in root.iterdir():
            if not child.is_dir():
                continue
            # _demo 是演示包的缓存目录，不属于任务产物，保留
            if child.name.startswith("_"):
                continue
            try:
                if now - child.stat().st_mtime > ttl:
                    shutil.rmtree(child, ignore_errors=True)
                    removed += 1
            except OSError:
                continue
        if removed:
            logger.info(f"清理过期任务目录 {removed} 个")
        return removed

    def get_work_dir(self, task_id: str) -> Optional[Path]:
        """任务产物目录（兼容工作流自身再嵌套一层的情况）"""
        base = Path(web_settings.OUTPUT_ROOT) / task_id / "project"
        if not base.exists():
            return None
        return self._resolve_work_dir(base)


task_manager = TaskManager()
