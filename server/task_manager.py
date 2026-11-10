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
from server.task_store import (
    list_records,
    load_record,
    load_result as _load_result,
    save_record,
    save_result,
)


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
    # 上次落盘时间，用于事件持久化节流
    _last_persist_at: float = 0.0

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

    def to_dict(self) -> Dict[str, Any]:
        """完整快照：用于持久化到磁盘"""
        return {
            "task_id": self.task_id,
            "status": self.status,
            "title": self.title,
            "message": self.message,
            "progress": self.progress,
            "created_at": self.created_at,
            "finished_at": self.finished_at,
            "error": self.error,
            "events": list(self.events),
            # result 里含完整论文正文，体积较大；单独存到 result.json
            "has_result": self.result is not None,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskRecord":
        """从磁盘快照还原（内存态重建，事件历史一并恢复）"""
        return cls(
            task_id=data.get("task_id", ""),
            status=data.get("status", "pending"),
            created_at=data.get("created_at") or time.time(),
            finished_at=data.get("finished_at"),
            title=data.get("title", ""),
            message=data.get("message", ""),
            progress=data.get("progress", 0),
            events=list(data.get("events") or []),
            error=data.get("error"),
        )


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

    # ---------------------------------------------------------------- 持久化

    def restore(self) -> int:
        """启动时从磁盘恢复历史任务记录。

        只恢复「已完成/失败」的任务；运行中的任务在进程退出时已丢失，
        恢复成 error 更诚实，避免前端一直等待一个永远不会来的进度。
        """
        restored = 0
        for data in list_records(limit=200):
            task_id = data.get("task_id")
            if not task_id:
                continue
            status = data.get("status")
            if status in ("pending", "running"):
                data = dict(data)
                data["status"] = "error"
                data["error"] = "服务重启，任务已中断"
                data["message"] = "服务重启，任务已中断"
                data["finished_at"] = data.get("finished_at") or time.time()
            record = TaskRecord.from_dict(data)
            # 产出正文单独存放，按需读取
            result = _load_result(task_id)
            if result is not None:
                record.result = result
            with self._lock:
                self._tasks[task_id] = record
            restored += 1
        if restored:
            logger.info(f"已从磁盘恢复 {restored} 条历史任务记录")
        return restored

    def _persist(self, record: TaskRecord) -> None:
        """把任务状态写入磁盘（失败不影响主流程）"""
        try:
            save_record(record.to_dict())
            # 产出正文体积大，单独存一个文件
            if record.result is not None:
                save_result(record.task_id, record.result)
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"持久化任务 {record.task_id} 失败: {exc}")

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
        """取任务：先看内存，没有则从磁盘恢复"""
        with self._lock:
            record = self._tasks.get(task_id)
        if record is not None:
            return record
        # 内存没有 → 可能是服务重启前的历史任务
        data = load_record(task_id)
        if not data:
            return None
        record = TaskRecord.from_dict(data)
        result = _load_result(task_id)
        if result is not None:
            record.result = result
        with self._lock:
            self._tasks[task_id] = record
        return record

    def list_recent(self, limit: int = 50) -> List[Dict[str, Any]]:
        """列出最近任务：内存 + 磁盘合并去重"""
        with self._lock:
            records = sorted(
                self._tasks.values(), key=lambda r: r.created_at, reverse=True
            )
        seen = {r.task_id for r in records}
        merged = [r.public_dict() for r in records]

        # 补充内存中没有的持久化任务
        for data in list_records(limit=limit):
            tid = data.get("task_id")
            if not tid or tid in seen:
                continue
            seen.add(tid)
            merged.append(
                {
                    "task_id": tid,
                    "status": data.get("status", "pending"),
                    "title": data.get("title", ""),
                    "message": data.get("message", ""),
                    "progress": data.get("progress", 0),
                    "created_at": data.get("created_at") or 0,
                    "finished_at": data.get("finished_at"),
                    "error": data.get("error"),
                    "restored": True,
                }
            )
        merged.sort(key=lambda d: d.get("created_at") or 0, reverse=True)
        return merged[:limit]

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
        self._persist(record)
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
                self._persist(record)
            except Exception as exc:  # noqa: BLE001
                logger.exception(f"[{record.task_id}] 任务失败")
                self._finish_error(record, self._error_text(exc))
            finally:
                loop.close()
        finally:
            if acquired:
                self._semaphore.release()
            record.finished_at = time.time()
            # 兜底落盘：确保结束时状态一定写进磁盘
            self._persist(record)
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
        # 事件高频，落盘做节流；错误与结束事件立即写入
        if etype in ("error", "system") or self._should_persist(record):
            self._persist(record)

    def _should_persist(self, record: TaskRecord) -> bool:
        """事件落盘节流：最多每 2 秒写一次"""
        now = time.time()
        if now - record._last_persist_at < 2.0:
            return False
        record._last_persist_at = now
        return True

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
        self._persist(record)

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
