"""
产物目录解析的回归测试

工作流的输出结构是 <base>/<workflow_task_id>/，
后端必须能正确定位到那一层，否则图片 404、文件列表为空。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server.task_manager import TaskManager, _make_project_zip  # noqa: E402


def test_flat_structure(tmp: Path):
    """扁平结构（产物直接位于 base 下）应原样返回"""
    base = tmp / "flat"
    base.mkdir(parents=True)
    (base / "paper.md").write_text("x", encoding="utf-8")
    assert TaskManager._resolve_work_dir(base) == base


def test_nested_structure(tmp: Path):
    """嵌套结构（base/<task_id>/）应下钻一层"""
    base = tmp / "nested"
    inner = base / "20261109_120000_abcdef"
    inner.mkdir(parents=True)
    (inner / "paper.md").write_text("x", encoding="utf-8")
    (inner / "fig1.png").write_bytes(b"\x89PNG")
    assert TaskManager._resolve_work_dir(base) == inner


def test_empty_base(tmp: Path):
    """空目录时返回自身，不报错"""
    base = tmp / "empty"
    base.mkdir(parents=True)
    assert TaskManager._resolve_work_dir(base) == base


def test_zip_excludes_cache(tmp: Path):
    """压缩包应跳过 __pycache__ 与 .pyc"""
    work = tmp / "w"
    (work / "__pycache__").mkdir(parents=True)
    (work / "__pycache__" / "x.cpython-311.pyc").write_bytes(b"junk")
    (work / "a.py").write_text("code", encoding="utf-8")
    (work / "fig.png").write_bytes(b"\x89PNG")

    zip_path = _make_project_zip(tmp / "project", work)
    import zipfile

    names = zipfile.ZipFile(zip_path).namelist()
    assert names == ["a.py", "fig.png"], names


def test_work_dir_lookup(tmp: Path):
    """get_work_dir 应能穿透工作流自身创建的那层目录"""
    import server.task_manager as tm

    orig = tm.web_settings.OUTPUT_ROOT
    try:
        tm.web_settings.OUTPUT_ROOT = str(tmp)
        inner = tmp / "task1" / "project" / "20261109_120000_abcdef"
        inner.mkdir(parents=True)
        (inner / "paper.md").write_text("x", encoding="utf-8")

        mgr = TaskManager()
        got = mgr.get_work_dir("task1")
        assert got == inner, got
        assert mgr.get_work_dir("nope") is None
    finally:
        tm.web_settings.OUTPUT_ROOT = orig


if __name__ == "__main__":
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        test_flat_structure(tmp / "a")
        test_nested_structure(tmp / "b")
        test_empty_base(tmp / "c")
        test_zip_excludes_cache(tmp / "d")
        test_work_dir_lookup(tmp / "e")
    print("全部通过 ✓")
