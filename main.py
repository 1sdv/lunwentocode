"""
BiyeToCode - 论文初稿生成系统

将研究方案/论文草稿（Markdown或PDF）转化为：论文初稿正文 + 可运行的验证代码
"""
import asyncio
import argparse
import os
import sys

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.core.workflow import ThesisToCodeWorkflow
from app.core.llm import LLM
from app.config.settings import settings
from app.utils.logger import logger


def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description="BiyeToCode - 论文初稿生成系统",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 使用Markdown或PDF研究方案
  python main.py --md proposal.pdf

  # 使用Markdown方案和数据文件
  python main.py --md proposal.md --data ./data

  # 指定输出目录
  python main.py --md proposal.md --output ./my_output
        """
    )

    parser.add_argument(
        "--md", "-m",
        required=True,
        help="研究方案/论文草稿文件路径（支持Markdown或PDF）"
    )
    
    parser.add_argument(
        "--data", "-d",
        default=None,
        help="数据文件目录（可选，包含Excel/CSV文件）"
    )
    
    parser.add_argument(
        "--output", "-o",
        default="output",
        help="输出目录（默认: output）"
    )
    
    parser.add_argument(
        "--api-key",
        default=None,
        help="LLM API Key（也可通过环境变量LLM_API_KEY设置）"
    )
    
    parser.add_argument(
        "--model",
        default=None,
        help="LLM模型名称（默认: gpt-4o）"
    )
    
    parser.add_argument(
        "--base-url",
        default=None,
        help="LLM API Base URL（可选）"
    )
    
    return parser.parse_args()


async def main():
    """主函数"""
    args = parse_args()
    
    # 打印欢迎信息
    print("""
╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║     🎓 BiyeToCode - 论文初稿生成系统 🎓                       ║
║                                                              ║
║     研究方案 → 论文正文(paper.md) + 验证代码(notebook)        ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
    """)
    
    # 配置检查 - 分析LLM
    analyzer_api_key = settings.ANALYZER_LLM_API_KEY or settings.LLM_API_KEY or args.api_key
    if not analyzer_api_key:
        logger.error("请设置分析LLM API Key（环境变量 ANALYZER_LLM_API_KEY 或 LLM_API_KEY）")
        sys.exit(1)
    
    # 配置检查 - 代码LLM
    coder_api_key = settings.CODER_LLM_API_KEY or settings.LLM_API_KEY or args.api_key
    if not coder_api_key:
        logger.error("请设置代码LLM API Key（环境变量 CODER_LLM_API_KEY 或 LLM_API_KEY）")
        sys.exit(1)

    # 检查输入文件
    if not os.path.exists(args.md):
        logger.error(f"论文文件不存在: {args.md}")
        sys.exit(1)

    # 检查数据目录
    if args.data and not os.path.exists(args.data):
        logger.warning(f"数据目录不存在: {args.data}")
        args.data = None

    # 创建分析LLM实例（用于论文分析）
    analyzer_llm = LLM(
        api_key=analyzer_api_key,
        model=settings.ANALYZER_LLM_MODEL or settings.LLM_MODEL,
        base_url=settings.ANALYZER_LLM_BASE_URL or settings.LLM_BASE_URL
    )
    logger.info(f"分析LLM: {analyzer_llm.model}")

    # 创建代码LLM实例（用于代码生成和修复）
    coder_llm = LLM(
        api_key=coder_api_key,
        model=settings.CODER_LLM_MODEL or settings.LLM_MODEL,
        base_url=settings.CODER_LLM_BASE_URL or settings.LLM_BASE_URL
    )
    logger.info(f"代码LLM: {coder_llm.model}")

    # 创建写作LLM实例（用于复现报告，默认复用分析LLM配置）
    writer_api_key = settings.WRITER_LLM_API_KEY or analyzer_api_key
    writer_llm = LLM(
        api_key=writer_api_key,
        model=settings.WRITER_LLM_MODEL or settings.ANALYZER_LLM_MODEL or settings.LLM_MODEL,
        base_url=settings.WRITER_LLM_BASE_URL or settings.ANALYZER_LLM_BASE_URL or settings.LLM_BASE_URL
    )
    logger.info(f"写作LLM: {writer_llm.model}")

    # 创建工作流（传入LLM，事件直接走日志）
    workflow = ThesisToCodeWorkflow(
        analyzer_llm=analyzer_llm,
        coder_llm=coder_llm,
        writer_llm=writer_llm,
    )

    try:
        logger.info("开始处理...")
        logger.info(f"研究方案: {args.md}")
        if args.data:
            logger.info(f"数据目录: {args.data}")
        logger.info(f"输出目录: {args.output}")

        # 执行工作流
        result = await workflow.run(
            md_path=args.md,
            data_dir=args.data,
            output_dir=args.output
        )

        # 打印结果
        print("\n" + "=" * 60)
        print("✅ 论文初稿生成完成!")
        print("=" * 60)
        print(f"\n📁 项目目录: {workflow.work_dir}")
        print(f"📝 支撑任务数: {len(result.task_results)}")
        print(f"📦 依赖库数: {len(result.requirements)}")
        print(f"📄 论文章节数: {len(result.report.sections)}")

        success_count = sum(1 for r in result.task_results if r.success)
        print(f"✅ 任务成功: {success_count}/{len(result.task_results)}")

        print("\n核心产出:")
        print("  - paper.md        # 论文初稿正文（题目/摘要/引言/各章/结论）")
        print("  - notebook.ipynb  # 全部验证代码（可重跑）")

        print(f"\n请查看 {workflow.work_dir}/README.md 了解详细信息")
        print("=" * 60)
        
    except Exception as e:
        logger.error(f"处理失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
