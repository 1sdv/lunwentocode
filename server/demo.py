"""
演示模式 - 回放一次真实运行的完整流程

「运行示例」按钮的后端支撑：
- 提供脚本化的事件时间线（与真实工作流的 EventBus 事件类型一一对应）
- 提供真实产出目录的读取（论文正文、图表、依赖清单）
- 按需把产出目录打包成 zip 供下载（与真实任务的下载包结构一致）
"""
import json
import re
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from server.config import web_settings

# 事件前缀与后端 EventBus 保持一致
PREFIX = {
    "system": "◆",
    "code": "▶",
    "code_output": "›",
    "report": "✎",
    "error": "✕",
}


def _demo_dir() -> Path:
    return Path(web_settings.DEMO_DIR)


def demo_available() -> bool:
    return (_demo_dir() / "paper.md").exists()


def _read(name: str) -> str:
    path = _demo_dir() / name
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return ""


def _analysis() -> Dict[str, Any]:
    raw = _read("analysis_result.json")
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


# ---------------------------------------------------------------- 事件时间线

def build_timeline() -> List[Dict[str, Any]]:
    """构造脚本化的执行事件序列。

    内容取自 output/20261109_111122_91dfac 的真实 analysis_result.json，
    保证演示与真实运行的阶段划分、任务标题、图表文件名完全一致。
    """
    analysis = _analysis()
    tasks = analysis.get("code_tasks", [])
    tl: List[Dict[str, Any]] = []

    def add(etype: str, content: str) -> None:
        tl.append({"type": etype, "prefix": PREFIX.get(etype, "·"), "content": content})

    add("system", "开始任务: 20261109_111122_91dfac")
    add("system", "Phase 1/6: 读取研究方案")
    add("system", "Phase 2/6: 扫描数据文件")
    add("system", "发现 0 个数据文件")
    add("system", "Phase 3/6: 分析研究方案，拆解论文支撑任务")

    thesis_type = analysis.get("thesis_type", "system_design")
    add(
        "system",
        f"分析完成: 研究类型={thesis_type}, 共 {len(tasks)} 个支撑任务",
    )

    add("system", "Phase 4/6: 启动 Jupyter 内核执行环境")
    add("code_output", "执行成功:\nMatplotlib 已注入学术配色与 300dpi 设置，中文字体加载完成")

    # 逐任务执行：代码手 → 写作手
    chart_by_task = {
        "统一系统假设、物理量单位与实验配置": [],
        "构造RIS辅助多用户MIMO信道与可复现实验样本": ["fig1_node_deployment.png"],
        "实现接收信号、有效速率、采集能量与能效模型": [],
        "建立联合优化问题与约束可行性检查": [],
        "实现多初值交替优化与可行解恢复": [
            "fig1_multistart_trajectories.png",
            "fig1_fixed_phase_feasible_region.png",
        ],
        "开展基线对照、参数扫描与组件消融实验": [
            "fig1_baseline_comparison.png",
            "fig2_RIS_scale_power_ablation.png",
            "fig2_link_gain_validation.png",
        ],
        "统计评估性能差异与数值结果稳定性": [
            "fig3_power_energy_sensitivity.png",
            "fig3_stopping_threshold_sensitivity.png",
        ],
        "生成论文图表、实验结果表与可复现材料": [
            "fig2_initial_budget_sensitivity.png",
            "fig1_rho_weighting_validation.png",
            "fig4_net_power_margin_sensitivity.png",
        ],
    }

    section_names = {
        "统一系统假设、物理量单位与实验配置": "系统假设与参数定义",
        "构造RIS辅助多用户MIMO信道与可复现实验样本": "系统架构与信道模型",
        "实现接收信号、有效速率、采集能量与能效模型": "信号传输与能效评价模型",
        "建立联合优化问题与约束可行性检查": "能效联合优化问题构建",
        "实现多初值交替优化与可行解恢复": "联合优化求解方法",
        "开展基线对照、参数扫描与组件消融实验": "仿真实验设计与性能对比",
        "统计评估性能差异与数值结果稳定性": "结果可靠性与敏感性分析",
        "生成论文图表、实验结果表与可复现材料": "实验结果展示与讨论",
    }

    code_snip = {
        "构造RIS辅助多用户MIMO信道与可复现实验样本":
            "```\nimport numpy as np\nrng = np.random.default_rng(20261109)\n"
            "# 直射链路 + RIS 反射链路，复数信道采样\nH = (rng.normal(size=(U, T, N)) + 1j*rng.normal(size=(U, T, N))) / np.sqrt(2)\n"
            "G = (rng.normal(size=(U, T, M, N)) + 1j*rng.normal(size=(U, T, M, N))) / np.sqrt(2)\n```",
        "实现多初值交替优化与可行解恢复":
            "```\nfor it in range(MAX_IT):\n    V = project_unit_mod(V + mu * grad)\n"
            "    B = project_soc(B + rho * grad_B)\n    eta = dinkelbach_update(R_sum, P_net)\n```",
        "开展基线对照、参数扫描与组件消融实验":
            "```\nfor name, scheme in baselines.items():\n"
            "    for _ in range(NUM_SAMPLES):\n        res = solve(scheme, sample)\n"
            "        energy_eff.append(res.rate / res.net_power)\n```",
    }

    total = len(tasks)
    for i, task in enumerate(tasks, 1):
        title = task.get("title", "")
        section = section_names.get(title, task.get("paper_section", title))
        add("system", f"Phase 5/6: 支撑任务 {i}/{total}: {title}")
        add("code", f"代码手开始执行: 任务{i}：{section}")

        snip = code_snip.get(title)
        if snip:
            add("code", f"执行代码:\n{snip}")

        charts = chart_by_task.get(title, [])
        if charts:
            add("code_output", f"执行成功:\n生成 {len(charts)} 张图表 · " + "、".join(charts))
        else:
            add("code_output", "执行成功:\n约束检查通过，数值在容差范围内")

        add("report", f"写作手开始撰写章节（图片 {len(charts)} 张）")
        add("report", f"写作手完成章节（{1800 + i * 260} 字）")

    add("system", "Phase 6/6: 撰写论文摘要、引言与结论")
    add("report", "写作手完成章节（摘要与关键词）")
    add("report", "写作手完成章节（引言）")
    add("report", "写作手完成章节（结论）")
    add("system", "任务完成: 20261109_111122_91dfac")
    add("system", f"输出目录: {web_settings.DEMO_DIR}")

    return tl


# ---------------------------------------------------------------- 结果

def build_result() -> Dict[str, Any]:
    """构造与真实任务结果同构的 payload"""
    analysis = _analysis()
    report = _read("paper.md")
    requirements = [
        line.strip()
        for line in _read("requirements.txt").splitlines()
        if line.strip()
    ]

    demo_dir = _demo_dir()
    files = sorted(
        p.name for p in demo_dir.iterdir() if p.is_file()
    ) if demo_dir.exists() else []

    # 章节统计：按 Markdown 一级/二级标题切分
    sections = []
    for m in re.finditer(r"^#\s+(.+)$", report, re.M):
        title = m.group(1).strip()
        start = m.end()
        nxt = re.search(r"^#\s+", report[start:], re.M)
        end = start + (nxt.start() if nxt else len(report) - start)
        sections.append({"key": title, "chars": end - start})

    total_chars = len(report)
    png_count = len([f for f in files if f.endswith(".png")])
    zip_info = demo_zip_info()

    return {
        "task_id": web_settings.DEMO_TASK_ID,
        "title": "时隙分割下 RIS 辅助多用户 MIMO 系统的能效联合优化",
        "report": report,
        "requirements": requirements,
        "sections": sections,
        "tasks_total": len(analysis.get("code_tasks", [])),
        "tasks_success": len(analysis.get("code_tasks", [])),
        "notebook": "notebook.ipynb",
        "readme": _read("README.md"),
        "zip_name": zip_info["zip_name"],
        "zip_size": zip_info["zip_size"],
        "files": files,
        "demo": True,
        "metrics": {
            "正文字数": f"{total_chars:,}",
            "论文章节": len(sections),
            "LaTeX 公式块": report.count("$$") // 2 + report.count("\\begin{"),
            "实验图表": png_count,
            "Notebook 代码单元": 101,
        },
    }


def demo_file_path(name: str) -> Optional[Path]:
    """按文件名取演示产出，防止目录穿越"""
    demo_dir = _demo_dir().resolve()
    target = (demo_dir / name).resolve()
    if not str(target).startswith(str(demo_dir)):
        return None
    return target if target.is_file() else None


# ---------------------------------------------------------------- 打包下载

# 打包时跳过这些：Python 缓存与临时文件，对交付无意义
_ZIP_EXCLUDE_DIRS = {"__pycache__", ".ipynb_checkpoints", ".git"}
_ZIP_EXCLUDE_SUFFIX = (".pyc", ".pyo", ".tmp")


def _iter_zip_files(root: Path):
    """产出目录里所有该进包的文件"""
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        if any(part in _ZIP_EXCLUDE_DIRS for part in rel.parts):
            continue
        if path.suffix in _ZIP_EXCLUDE_SUFFIX:
            continue
        yield path, rel


def demo_zip_path() -> Optional[Path]:
    """把演示产出打包成 zip（带缓存，重复下载不重复打包）。

    返回 None 表示演示数据不可用。
    """
    demo_dir = _demo_dir()
    if not (demo_dir / "paper.md").exists():
        return None

    # 缓存放在产出目录之外，避免被打进包自己里
    cache_dir = Path(web_settings.OUTPUT_ROOT) / "_demo"
    cache_dir.mkdir(parents=True, exist_ok=True)
    zip_path = cache_dir / "demo_project.zip"

    # 源目录里最新的文件时间，用作缓存失效判据
    newest = max(
        (p.stat().st_mtime for p in demo_dir.rglob("*") if p.is_file()),
        default=0.0,
    )

    if zip_path.exists() and zip_path.stat().st_mtime >= newest:
        return zip_path

    # 先写临时文件再替换，避免中途被打断留下坏包
    tmp_path = cache_dir / "demo_project.tmp.zip"
    with zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for path, rel in _iter_zip_files(demo_dir):
            zf.write(path, arcname=str(rel))
    tmp_path.replace(zip_path)
    return zip_path


def demo_zip_info() -> Dict[str, Any]:
    """演示包的名称与大小（供前端展示）"""
    path = demo_zip_path()
    if not path or not path.exists():
        return {"zip_name": "", "zip_size": 0}
    return {"zip_name": path.name, "zip_size": path.stat().st_size}
