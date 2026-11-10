"""
任务记录持久化 - 让服务重启后仍能查看历史任务

设计要点：
- 记录与产出文件放在一起（web_output/<task_id>/record.json），
  产出目录被清理时记录随之消失，无需额外的保留策略。
- 原子写入（先写 .tmp 再 replace），避免进程被杀时留下坏文件。
- 记录内容不含 API Key 等敏感信息，只有状态、事件与产出摘要。
"""
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from server.config import web_settings

RECORD_NAME = "record.json"
RESULT_NAME = "result.json"
# 单个任务最多保留的事件条数，避免记录文件无限膨胀
MAX_PERSISTED_EVENTS = 500


def record_path(task_id: str) -> Path:
    """任务记录文件路径"""
    return Path(web_settings.OUTPUT_ROOT) / task_id / RECORD_NAME


def result_path(task_id: str) -> Path:
    """任务产出正文文件路径（体积大，与记录分开存放）"""
    return Path(web_settings.OUTPUT_ROOT) / task_id / RESULT_NAME


def save_result(task_id: str, result: Dict[str, Any]) -> bool:
    """原子写入任务产出正文"""
    path = result_path(task_id)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(
            json.dumps(result, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
        os.replace(tmp, path)
        return True
    except OSError:
        return False


def load_result(task_id: str) -> Optional[Dict[str, Any]]:
    """读取任务产出正文"""
    path = result_path(task_id)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return None


def save_record(data: Dict[str, Any]) -> bool:
    """原子写入任务记录，返回是否成功"""
    task_id = data.get("task_id")
    if not task_id:
        return False
    path = record_path(task_id)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = dict(data)
        events = payload.get("events") or []
        if len(events) > MAX_PERSISTED_EVENTS:
            payload["events"] = events[-MAX_PERSISTED_EVENTS:]
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(
            json.dumps(payload, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
        os.replace(tmp, path)
        return True
    except OSError:
        return False


def load_record(task_id: str) -> Optional[Dict[str, Any]]:
    """读取任务记录，不存在或损坏时返回 None"""
    path = record_path(task_id)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return None


def list_records(limit: int = 50) -> List[Dict[str, Any]]:
    """按创建时间倒序列出已持久化的任务"""
    root = Path(web_settings.OUTPUT_ROOT)
    if not root.exists():
        return []
    items: List[Dict[str, Any]] = []
    try:
        children = list(root.iterdir())
    except OSError:
        return []
    for child in children:
        # 下划线开头的是内部目录（如 _demo 缓存），不是任务
        if not child.is_dir() or child.name.startswith("_"):
            continue
        data = load_record(child.name)
        if data:
            items.append(data)
    items.sort(key=lambda d: d.get("created_at") or 0, reverse=True)
    return items[:limit]
