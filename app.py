"""
LunwenToCode - 科研论文/毕业论文复现系统 (Web版)

将论文转换为可执行的 Jupyter Notebook 与图文复现报告，
进度实时流式推送到界面。
"""
import asyncio
import os
import shutil
import sys
import tempfile
import threading
import queue

# httpx(gradio 依赖) 无法解析 NO_PROXY 中的 IPv6 字面量 [::1]，导入 gradio 前先清理
for _key in ("NO_PROXY", "no_proxy"):
    _val = os.environ.get(_key, "")
    if "[::1]" in _val:
        _cleaned = _val.replace("[::1],", "").replace("[::1]", "").strip(",")
        if _cleaned:
            os.environ[_key] = _cleaned
        else:
            os.environ.pop(_key, None)

import gradio as gr

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.core.events import EventBus
from app.core.workflow import ThesisToCodeWorkflow
from app.core.llm import LLM
from app.config.settings import settings


def run_process(md_file, data_files, api_key, analyzer_model, coder_model, writer_model, base_url):
    """同步生成器：后台线程执行工作流，实时 yield 进度事件"""
    if md_file is None:
        yield "❌ 请上传论文文件（Markdown或PDF）", None, None, None
        return

    final_api_key = api_key.strip() if api_key and api_key.strip() else settings.LLM_API_KEY
    if not final_api_key:
        yield "❌ 请输入API Key或设置环境变量 LLM_API_KEY", None, None, None
        return

    analyzer_model = analyzer_model.strip() if analyzer_model and analyzer_model.strip() \
        else settings.ANALYZER_LLM_MODEL or "gpt-4o"
    coder_model = coder_model.strip() if coder_model and coder_model.strip() \
        else settings.CODER_LLM_MODEL or "gpt-4o"
    writer_model = writer_model.strip() if writer_model and writer_model.strip() \
        else settings.WRITER_LLM_MODEL or analyzer_model
    final_base_url = base_url.strip() if base_url and base_url.strip() else settings.LLM_BASE_URL

    # 进度事件队列：工作流线程 → Gradio 生成器
    event_queue: "queue.Queue" = queue.Queue()

    def on_event(event):
        event_queue.put(event)

    holder = {}

    def worker():
        async def main():
            bus = EventBus()
            bus.subscribe(on_event)

            temp_dir = tempfile.mkdtemp()
            output_dir = os.path.join(temp_dir, "output")
            data_dir = None

            if data_files:
                data_dir = os.path.join(temp_dir, "data")
                os.makedirs(data_dir, exist_ok=True)
                for data_file in data_files:
                    if data_file is not None:
                        shutil.copy(
                            data_file if isinstance(data_file, str) else data_file.name,
                            os.path.join(data_dir, os.path.basename(
                                data_file if isinstance(data_file, str) else data_file.name)),
                        )

            analyzer_llm = LLM(api_key=final_api_key, model=analyzer_model, base_url=final_base_url)
            coder_llm = LLM(api_key=final_api_key, model=coder_model, base_url=final_base_url)
            writer_llm = LLM(api_key=final_api_key, model=writer_model, base_url=final_base_url)

            workflow = ThesisToCodeWorkflow(
                analyzer_llm=analyzer_llm,
                coder_llm=coder_llm,
                writer_llm=writer_llm,
                event_bus=bus,
            )
            result = await workflow.run(
                md_path=md_file if isinstance(md_file, str) else md_file.name,
                data_dir=data_dir,
                output_dir=output_dir,
            )

            zip_path = os.path.join(temp_dir, "generated_project")
            shutil.make_archive(zip_path, "zip", workflow.work_dir)
            holder["result"] = result
            holder["zip_path"] = zip_path + ".zip"
            holder["work_dir"] = workflow.work_dir

        asyncio.run(main())

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()

    progress_lines = []
    while True:
        try:
            event = event_queue.get(timeout=1)
        except queue.Empty:
            if not thread.is_alive():
                break
            continue

        if event.get("type") == "error":
            progress_lines.append(f"❌ {event['content']}")
        else:
            prefix = {"system": "🔧", "code": "💻", "code_output": "📊", "report": "📝"}.get(
                event.get("type"), "•"
            )
            progress_lines.append(f"{prefix} {event['content']}")
        yield "\n".join(progress_lines[-200:]), None, None, None

    thread.join(timeout=5)

    if "result" not in holder:
        yield "\n".join(progress_lines) + "\n\n❌ 处理失败，请查看上方日志", None, None, None
        return

    result = holder["result"]
    summary = (
        f"✅ 论文复现完成!\n\n"
        f"📝 复现任务: {sum(1 for r in result.task_results if r.success)}/"
        f"{len(result.task_results)} 成功\n"
        f"📄 报告章节: {len(result.report.sections)}\n"
        f"📦 依赖库: {len(result.requirements)}\n\n"
        f"核心产出: notebook.ipynb（可复现代码）+ report.md（复现报告）"
    )
    yield "\n".join(progress_lines[-200:]) + f"\n\n{summary}", \
        result.report.full_report, holder["zip_path"], \
        "\n".join(result.requirements) if result.requirements else "无额外依赖"


with gr.Blocks(title="LunwenToCode - 论文复现系统", theme=gr.themes.Soft()) as demo:
    gr.Markdown("""
    # 🎓 LunwenToCode - 论文复现系统

    将论文（Markdown/PDF）转换为 **可执行的 Jupyter Notebook** 与 **图文复现报告**。
    代码在真实 Jupyter 内核中执行验证，报告中所有数值均来自真实运行结果。
    （PDF 建议先用 [Mineru](https://mineru.net/) 转为 Markdown）
    """)

    with gr.Row():
        with gr.Column(scale=1):
            gr.Markdown("### 📤 输入")

            md_input = gr.File(
                label="上传论文文件",
                file_types=[".md", ".pdf", ".txt"],
                type="filepath",
            )

            data_input = gr.File(
                label="上传数据文件（可选，支持多个Excel/CSV）",
                file_types=[".xlsx", ".xls", ".csv"],
                file_count="multiple",
                type="filepath",
            )

            with gr.Accordion("⚙️ API配置", open=True):
                api_key_input = gr.Textbox(
                    label="API Key",
                    placeholder="输入你的API Key（留空则使用环境变量）",
                    type="password",
                )
                base_url_input = gr.Textbox(
                    label="API Base URL（可选）",
                    placeholder="例如: https://api.openai.com/v1",
                )
                analyzer_model_input = gr.Textbox(
                    label="分析模型（论文分析与报告写作）",
                    placeholder="默认: gpt-4o",
                    value="",
                )
                coder_model_input = gr.Textbox(
                    label="代码生成模型",
                    placeholder="默认: gpt-4o",
                    value="",
                )
                writer_model_input = gr.Textbox(
                    label="报告写作模型（留空则与分析模型一致）",
                    placeholder="默认与分析模型一致",
                    value="",
                )

            submit_btn = gr.Button("🚀 开始复现", variant="primary", size="lg")

        with gr.Column(scale=2):
            gr.Markdown("### 📥 输出")

            progress_text = gr.Textbox(
                label="执行进度（实时）",
                lines=18,
                max_lines=40,
                show_copy_button=True,
            )

            with gr.Accordion("📄 复现报告（完成后展示）", open=False):
                report_md = gr.Markdown(label="复现报告")

            with gr.Row():
                download_file = gr.File(label="📦 下载完整项目包")
                requirements_text = gr.Textbox(label="📋 依赖库", lines=5)

    submit_btn.click(
        fn=run_process,
        inputs=[md_input, data_input, api_key_input, analyzer_model_input,
                coder_model_input, writer_model_input, base_url_input],
        outputs=[progress_text, report_md, download_file, requirements_text],
    )

    gr.Markdown("""
    ### 📖 使用说明
    1. 上传论文文件（PDF 建议先用 [Mineru](https://mineru.net/) 转为 Markdown）
    2. 如有数据文件，可一并上传（Excel/CSV）
    3. 填写 API Key（或预先设置环境变量）
    4. 点击"开始复现"，实时查看执行进度（过程较慢请耐心等待）
    5. 完成后查看复现报告并下载完整项目包（notebook + 报告 + 图表）
    """)


if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=7860)
