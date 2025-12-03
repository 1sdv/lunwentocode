"""
lunwenToCode - 科研论文/毕业论文代码生成系统 (Web版)

将毕业论文Markdown转换为可运行的Python代码
"""
import asyncio
import os
import sys
import tempfile
import shutil
import gradio as gr

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.core.workflow import ThesisToCodeWorkflow
from app.core.llm import LLM
from app.config.settings import settings
from app.utils.logger import logger


async def process_thesis(
    md_file,
    data_files,
    api_key,
    analyzer_model,
    coder_model,
    base_url
):
    """处理论文并生成代码"""
    
    if md_file is None:
        return "❌ 请上传论文文件（Markdown或PDF）", None, ""
    
    # 使用传入的API Key或环境变量
    final_api_key = api_key.strip() if api_key and api_key.strip() else settings.LLM_API_KEY
    if not final_api_key:
        return "❌ 请输入API Key或设置环境变量 LLM_API_KEY", None, ""
    
    # 模型配置
    analyzer_model = analyzer_model.strip() if analyzer_model and analyzer_model.strip() else settings.ANALYZER_LLM_MODEL or "gpt-4o"
    coder_model = coder_model.strip() if coder_model and coder_model.strip() else settings.CODER_LLM_MODEL or "gpt-4o"
    final_base_url = base_url.strip() if base_url and base_url.strip() else settings.LLM_BASE_URL
    
    # 创建临时目录
    temp_dir = tempfile.mkdtemp()
    output_dir = os.path.join(temp_dir, "output")
    data_dir = None
    
    try:
        # 处理数据文件
        if data_files and len(data_files) > 0:
            data_dir = os.path.join(temp_dir, "data")
            os.makedirs(data_dir, exist_ok=True)
            for data_file in data_files:
                if data_file is not None:
                    shutil.copy(data_file.name, os.path.join(data_dir, os.path.basename(data_file.name)))
        
        # 创建分析LLM实例
        analyzer_llm = LLM(
            api_key=final_api_key,
            model=analyzer_model,
            base_url=final_base_url
        )
        
        # 创建代码LLM实例
        coder_llm = LLM(
            api_key=final_api_key,
            model=coder_model,
            base_url=final_base_url
        )
        
        # 创建工作流
        workflow = ThesisToCodeWorkflow(analyzer_llm=analyzer_llm, coder_llm=coder_llm)
        
        # 执行工作流
        result = await workflow.run(
            md_path=md_file.name,
            data_dir=data_dir,
            output_dir=output_dir
        )
        
        # 收集生成的文件内容
        output_text = "✅ 代码生成完成!\n\n"
        output_text += f"📄 生成文件数: {len(result.files)}\n"
        output_text += f"📦 依赖库数: {len(result.requirements)}\n\n"
        output_text += "=" * 50 + "\n\n"
        
        # 显示每个文件的内容
        for file_name, content in result.files.items():
            output_text += f"📄 {file_name}\n"
            output_text += "-" * 40 + "\n"
            output_text += content + "\n\n"
        
        # 打包输出目录为zip
        zip_path = os.path.join(temp_dir, "generated_code")
        shutil.make_archive(zip_path, 'zip', workflow.work_dir)
        
        # requirements
        req_text = "\n".join(result.requirements) if result.requirements else "无额外依赖"
        
        return output_text, zip_path + ".zip", req_text
        
    except Exception as e:
        import traceback
        error_msg = f"❌ 处理失败: {str(e)}\n\n{traceback.format_exc()}"
        return error_msg, None, ""


def run_process(md_file, data_files, api_key, analyzer_model, coder_model, base_url):
    """同步包装器"""
    return asyncio.run(process_thesis(md_file, data_files, api_key, analyzer_model, coder_model, base_url))


# 创建Gradio界面
with gr.Blocks(title="BiyeToCode - 毕业论文代码生成系统", theme=gr.themes.Soft()) as demo:
    gr.Markdown("""
    # 🎓 LunwenToCode - 科研论文/毕业论文代码生成系统
    
    将论文（Markdown格式）转换为可运行的Python代码([Mineru](https://mineru.net/)一键转化pdf为Markdown文件)
    """)
    
    with gr.Row():
        with gr.Column(scale=1):
            gr.Markdown("### 📤 输入")
            
            md_input = gr.File(
                label="上传论文文件",
                file_types=[".md", ".pdf", ".txt"],
                type="filepath"
            )
            
            data_input = gr.File(
                label="上传数据文件（可选，支持多个Excel/CSV）",
                file_types=[".xlsx", ".xls", ".csv"],
                file_count="multiple",
                type="filepath"
            )
            
            with gr.Accordion("⚙️ API配置", open=True):
                api_key_input = gr.Textbox(
                    label="API Key",
                    placeholder="输入你的API Key（留空则使用环境变量）",
                    type="password"
                )
                
                base_url_input = gr.Textbox(
                    label="API Base URL（可选）",
                    placeholder="例如: https://api.openai.com/v1"
                )
                
                analyzer_model_input = gr.Textbox(
                    label="分析模型",
                    placeholder="默认: gpt-4o",
                    value=""
                )
                
                coder_model_input = gr.Textbox(
                    label="代码生成模型",
                    placeholder="默认: gpt-4o",
                    value=""
                )
            
            submit_btn = gr.Button("🚀 开始生成", variant="primary", size="lg")
        
        with gr.Column(scale=2):
            gr.Markdown("### 📥 输出")
            
            output_text = gr.Textbox(
                label="生成结果",
                lines=25,
                max_lines=50,
                show_copy_button=True
            )
            
            with gr.Row():
                download_file = gr.File(label="📦 下载完整代码包")
                requirements_text = gr.Textbox(label="📋 依赖库", lines=5)
    
    # 绑定事件
    submit_btn.click(
        fn=run_process,
        inputs=[md_input, data_input, api_key_input, analyzer_model_input, coder_model_input, base_url_input],
        outputs=[output_text, download_file, requirements_text]
    ) 
    
    gr.Markdown("""
    
    ### 📖 使用说明
    1. 上传论文文件（pdf转为Maekdown文档使用[Mineru](https://mineru.net/)一键转化下载即可）
    2. 如有数据文件，可一并上传（Excel/CSV）
    3. 填写 API Key（或预先设置环境变量）
    4. 点击"开始生成"按钮
    5. 等待处理完成后下载生成的代码包
    """)


if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=7860)
