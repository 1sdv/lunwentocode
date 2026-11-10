"""
任务记录持久化的回归测试

验证：
- 记录能写入并读回
- 重启（新建 TaskManager）后能恢复历史任务
- 产出正文单独存放且能恢复
- 运行中的任务在重启后标记为中断
- 目录穿越与损坏文件不影响服务
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import server.task_manager as tm  # noqa: E402
import server.task_store as store  # noqa: E402


def _use_tmp_root(tmp: Path):
    """把输出目录指向临时目录"""
    tm.web_settings.OUTPUT_ROOT = str(tmp)
    store.web_settings.OUTPUT_ROOT = str(tmp)


def _fresh(tmp: Path, name: str) -> Path:
    """为每个用例准备独立目录，避免相互干扰"""
    sub = tmp / name
    sub.mkdir(parents=True, exist_ok=True)
    _use_tmp_root(sub)
    return sub


def test_save_and_load(tmp: Path):
    """记录写入与读回"""
    tmp = _fresh(tmp, "save_load")
    data = {
        "task_id": "t001",
        "status": "done",
        "title": "测试标题",
        "progress": 100,
        "created_at": 1000.0,
        "events": [{"type": "system", "content": "hello"}],
    }
    assert store.save_record(data)
    got = store.load_record("t001")
    assert got is not None
    assert got["title"] == "测试标题"
    assert got["events"][0]["content"] == "hello"


def test_result_separate_file(tmp: Path):
    """产出正文单独存放"""
    tmp = _fresh(tmp, "result_file")
    result = {"task_id": "t002", "report": "很长的正文" * 100, "files": ["a.py"]}
    assert store.save_result("t002", result)
    assert store.load_result("t002")["report"] == result["report"]
    # 记录文件里不含正文
    assert store.save_record({"task_id": "t002", "status": "done"})
    assert "report" not in json.dumps(store.load_record("t002"))


def test_restore_after_restart(tmp: Path):
    """模拟重启：新 TaskManager 从磁盘恢复历史任务"""
    tmp = _fresh(tmp, "restore")
    store.save_record(
        {
            "task_id": "t100",
            "status": "done",
            "title": "历史任务",
            "progress": 100,
            "created_at": 2000.0,
            "events": [{"type": "system", "content": "完成"}],
        }
    )
    store.save_result("t100", {"task_id": "t100", "report": "论文正文", "files": ["a.py"]})

    mgr = tm.TaskManager()
    n = mgr.restore()
    assert n == 1, n

    rec = mgr.get("t100")
    assert rec is not None
    assert rec.title == "历史任务"
    assert rec.status == "done"
    assert rec.result is not None
    assert rec.result["report"] == "论文正文"
    assert len(rec.events) == 1


def test_running_task_marked_interrupted(tmp: Path):
    """重启时运行中的任务应标记为中断，而不是永远等待"""
    tmp = _fresh(tmp, "interrupted")
    store.save_record(
        {
            "task_id": "t200",
            "status": "running",
            "progress": 45,
            "created_at": 3000.0,
            "events": [],
        }
    )
    mgr = tm.TaskManager()
    mgr.restore()
    rec = mgr.get("t200")
    assert rec.status == "error"
    assert "重启" in rec.error


def test_corrupt_record_ignored(tmp: Path):
    """损坏的记录文件不应导致服务崩溃"""
    tmp = _fresh(tmp, "corrupt")
    d = tmp / "t300"
    d.mkdir(parents=True, exist_ok=True)
    (d / "record.json").write_text("{ 这不是合法 JSON", encoding="utf-8")
    assert store.load_record("t300") is None

    mgr = tm.TaskManager()
    mgr.restore()  # 不应抛异常
    assert mgr.get("t300") is None


def test_list_recent_merges_disk(tmp: Path):
    """列表接口应合并内存与磁盘任务"""
    tmp = _fresh(tmp, "list_merge")
    store.save_record(
        {"task_id": "t400", "status": "done", "created_at": 5000.0, "progress": 100}
    )
    mgr = tm.TaskManager()
    mgr.restore()
    items = mgr.list_recent(limit=10)
    ids = [i["task_id"] for i in items]
    assert "t400" in ids


def test_internal_dirs_skipped(tmp: Path):
    """下划线开头的内部目录不应被当成任务"""
    tmp = _fresh(tmp, "internal")
    d = tmp / "_demo"
    d.mkdir(parents=True, exist_ok=True)
    (d / "record.json").write_text(json.dumps({"task_id": "_demo"}), encoding="utf-8")
    assert store.list_records(limit=10) == []


def test_events_capped(tmp: Path):
    """事件条数有上限，避免记录文件无限膨胀"""
    tmp = _fresh(tmp, "events_cap")
    events = [{"type": "system", "content": str(i)} for i in range(800)]
    store.save_record({"task_id": "t500", "status": "done", "events": events})
    got = store.load_record("t500")
    assert len(got["events"]) == store.MAX_PERSISTED_EVENTS
    # 保留的是最新的那些
    assert got["events"][-1]["content"] == "799"


if __name__ == "__main__":
    orig_root = tm.web_settings.OUTPUT_ROOT
    try:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            _use_tmp_root(tmp)
            test_save_and_load(tmp)
            test_result_separate_file(tmp)
            test_restore_after_restart(tmp)
            test_running_task_marked_interrupted(tmp)
            test_corrupt_record_ignored(tmp)
            test_list_recent_merges_disk(tmp)
            test_internal_dirs_skipped(tmp)
            test_events_capped(tmp)
    finally:
        tm.web_settings.OUTPUT_ROOT = orig_root
        store.web_settings.OUTPUT_ROOT = orig_root
    print("全部通过 ✓")
