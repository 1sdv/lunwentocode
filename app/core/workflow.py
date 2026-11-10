"""
工作流引擎 - 论文初稿生成：解析研究方案 → 拆解支撑任务 → 逐任务执行代码 → 交错撰写论文正文 → 组装输出

参考 MathModelAgent 的 MathModelWorkFlow：
- 定位：研究生撰写自己的论文初稿，代码用于实验验证
- 求解与写作交错：每个任务由代码手在 Jupyter 内核中真实执行后，
  写作手立即以第一作者口吻撰写该任务对应的论文章节（携带代码输出与新增图片）
- 全部任务完成后撰写包装章节（题目摘要/引言/结论）
- 最终产出：paper.md（论文正文）+ notebook.ipynb（验证代码）+ requirements.txt + README.md
"""
import json
import os
import shutil
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

try:
    import tomllib
except ModuleNotFoundError:  # Python < 3.11
    import tomli as tomllib

from app.agents import AnalyzerAgent, CoderAgent, ParserAgent, WriterAgent
from app.core.events import EVENT_SYSTEM, EventBus
from app.core.llm import LLM
from app.schemas.models import (
    AnalysisResult,
    CodeTask,
    CoderExecutionResult,
    DataFileInfo,
    ParsedContent,
    ProjectOutput,
    ReportOutput,
)
from app.tools.local_interpreter import LocalCodeInterpreter
from app.tools.notebook_serializer import NotebookSerializer
from app.utils.file_utils import create_work_dir, save_code_file, scan_data_files
from app.utils.logger import logger
from app.utils.json_utils import load_json_from_response
from app.config.settings import settings

PAPER_TEMPLATE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "app", "config", "paper_template.toml",
)

# 论文章节拼接顺序（任务章节动态插入中间）
WRAPPER_SECTIONS = ["firstPage", "introduction"]
TAIL_SECTIONS = ["conclusion"]

DEFAULT_LIBRARIES = ["pandas", "numpy", "matplotlib"]


class ThesisToCodeWorkflow:
    """论文初稿工作流：研究方案 → 论文正文(paper.md) + 验证代码(notebook.ipynb)"""

    def __init__(
        self,
        analyzer_llm: Optional[LLM] = None,
        coder_llm: Optional[LLM] = None,
        writer_llm: Optional[LLM] = None,
        event_bus: Optional[EventBus] = None,
    ):
        self.analyzer_llm = analyzer_llm or LLM()
        self.coder_llm = coder_llm or LLM()
        # 写作手默认复用分析 LLM（分析模型通常擅长写作）
        self.writer_llm = writer_llm or self.analyzer_llm
        self.event_bus = event_bus or EventBus()

        self.analyzer_agent = AnalyzerAgent(self.analyzer_llm)
        self.parser_agent = ParserAgent(self.analyzer_llm)

        # 工作状态
        self.task_id: str = ""
        self.work_dir: str = ""
        # 研究方案原文（供写作手撰写各章节时引用素材）
        self._source_markdown: str = ""
        # 记录最近一次 LLM 错误，任务失败时优先抛出它，
        # 避免被「未生成支撑任务」这类二次错误掩盖真正原因
        self._last_llm_error: str = ""
        self._last_llm_error_at: float = 0.0

    def _on_llm_error(self, message: str) -> None:
        """LLM 调用失败：记录并推送到事件总线（前端终端可见）"""
        self._last_llm_error = message
        self._last_llm_error_at = time.time()
        self._publish(EVENT_ERROR, message)

    # ------------------------------------------------------------------ 主流程

    async def run(
        self,
        md_path: str,
        data_dir: Optional[str] = None,
        output_dir: Optional[str] = None,
    ) -> ProjectOutput:
        self.task_id = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        self._publish(EVENT_SYSTEM, f"开始任务: {self.task_id}")
        self.bind_llm_error_hooks()

        base_output = output_dir or settings.OUTPUT_DIR
        self.work_dir = create_work_dir(self.task_id, base_output)

        code_interpreter: Optional[LocalCodeInterpreter] = None
        try:
            # Phase 1: 读取输入
            self._publish(EVENT_SYSTEM, "Phase 1/6: 读取研究方案")
            parsed_content, source_ext = await self._load_input_content(md_path)
            self._source_markdown = parsed_content.raw_markdown or ""
            if source_ext == ".pdf":
                shutil.copy2(md_path, os.path.join(self.work_dir, "thesis.pdf"))
                save_code_file(self.work_dir, "thesis.md", parsed_content.raw_markdown or "")
            else:
                shutil.copy2(md_path, os.path.join(self.work_dir, "thesis.md"))

            # Phase 2: 扫描数据文件
            self._publish(EVENT_SYSTEM, "Phase 2/6: 扫描数据文件")
            data_files: List[DataFileInfo] = []
            if data_dir and os.path.exists(data_dir):
                data_files = scan_data_files(data_dir)
                for df in data_files:
                    dest = os.path.join(self.work_dir, df.file_name)
                    shutil.copy2(df.file_path, dest)
                    df.file_path = dest
                self._publish(EVENT_SYSTEM, f"发现 {len(data_files)} 个数据文件")

            # Phase 3: 内容分析
            self._publish(EVENT_SYSTEM, "Phase 3/6: 分析研究方案，拆解论文支撑任务")
            analysis_result = await self.analyzer_agent.run(parsed_content, data_files)
            self._save_analysis_result(analysis_result)
            if not analysis_result.code_tasks:
                raise ValueError("分析阶段未生成任何支撑任务，请检查方案内容或更换分析模型")
            self._publish(
                EVENT_SYSTEM,
                f"分析完成: 研究类型={analysis_result.thesis_type.value}, "
                f"共 {len(analysis_result.code_tasks)} 个支撑任务",
            )

            # Phase 4: 初始化执行环境
            self._publish(EVENT_SYSTEM, "Phase 4/6: 启动 Jupyter 内核执行环境")
            notebook_serializer = NotebookSerializer(work_dir=self.work_dir)
            code_interpreter = LocalCodeInterpreter(
                work_dir=self.work_dir,
                notebook_serializer=notebook_serializer,
                event_bus=self.event_bus,
            )
            await code_interpreter.initialize()

            coder_agent = CoderAgent(
                llm=self.coder_llm,
                work_dir=self.work_dir,
                code_interpreter=code_interpreter,
                event_bus=self.event_bus,
                max_chat_turns=settings.MAX_CHAT_TURNS,
                max_retries=settings.MAX_CODE_RETRIES,
            )
            writer_agent = WriterAgent(self.writer_llm, event_bus=self.event_bus)
            templates = self._load_paper_templates()
            context = self._build_coder_context(analysis_result, data_files)

            # Phase 5: 逐任务交错执行：代码 → 论文章节
            sorted_tasks = sorted(analysis_result.code_tasks, key=lambda t: t.priority)
            task_results: List[CoderExecutionResult] = []
            report = ReportOutput()
            task_section_keys: List[str] = []

            for i, task in enumerate(sorted_tasks, 1):
                self._publish(
                    EVENT_SYSTEM,
                    f"Phase 5/6: 支撑任务 {i}/{len(sorted_tasks)}: {task.title}",
                )
                result = await coder_agent.run(task, context, data_files)
                task_results.append(result)

                section_key = f"task_{i}"
                task_section_keys.append(section_key)
                section_content = await writer_agent.run(
                    self._build_task_section_prompt(
                        templates, task, result, i, len(sorted_tasks)
                    ),
                    available_images=result.created_images,
                )
                report.sections[section_key] = section_content
                self._save_intermediate_state(report, task_results, task_section_keys)

            # Phase 6: 撰写包装章节并组装输出
            self._publish(EVENT_SYSTEM, "Phase 6/6: 撰写论文摘要、引言与结论")
            thesis_info = self._build_thesis_info(parsed_content, analysis_result)
            tasks_overview = self._build_tasks_overview(sorted_tasks)
            comparison_info = self._build_comparison_info(sorted_tasks, task_results)

            for key in WRAPPER_SECTIONS:
                prompt = self._render_template(
                    templates.get(key, ""),
                    thesis_info=thesis_info,
                    tasks_overview=tasks_overview,
                    comparison_info=comparison_info,
                    thesis_title=parsed_content.title or "论文初稿",
                )
                report.sections[key] = await writer_agent.run(prompt)

            for key in TAIL_SECTIONS:
                prompt = self._render_template(
                    templates.get(key, ""),
                    thesis_info=thesis_info,
                    tasks_overview=tasks_overview,
                    comparison_info=comparison_info,
                    section_number=str(len(sorted_tasks) + 2),
                )
                report.sections[key] = await writer_agent.run(prompt)

            report.sequence = WRAPPER_SECTIONS + task_section_keys + TAIL_SECTIONS
            report.assemble()

            # 组装项目输出
            requirements = sorted(
                set(analysis_result.libraries) | set(DEFAULT_LIBRARIES)
            )
            project_output = ProjectOutput(
                project_name=self.task_id,
                thesis_title=parsed_content.title,
                report=report,
                notebook_file="notebook.ipynb",
                requirements=requirements,
                readme=self._generate_readme(parsed_content, analysis_result, sorted_tasks, task_results),
                task_results=task_results,
            )
            self._save_project_files(project_output)

            self._publish(EVENT_SYSTEM, f"任务完成: {self.task_id}")
            self._publish(EVENT_SYSTEM, f"输出目录: {self.work_dir}")
            return project_output

        except Exception as e:
            logger.error(f"工作流执行失败: {e}")
            # LLM 调用失败是最常见的原因，优先抛出它，
            # 避免被「未生成支撑任务」等二次错误掩盖。
            # 只在近期发生过 LLM 错误时才采用，避免误报陈旧错误。
            recent = (time.time() - self._last_llm_error_at) < 120
            if self._last_llm_error and recent:
                raise RuntimeError(self._last_llm_error) from e
            raise
        finally:
            if code_interpreter:
                await code_interpreter.cleanup()

    # ------------------------------------------------------------------ 输入解析

    async def _load_input_content(self, input_path: str) -> Tuple[ParsedContent, str]:
        ext = Path(input_path).suffix.lower()

        if ext == ".pdf":
            logger.info("检测到PDF论文，使用ParserAgent解析")
            parsed = await self.parser_agent.run(input_path)
            if not parsed.raw_markdown:
                parsed.raw_markdown = ""
            return parsed, ext

        if ext in {".md", ".markdown", ".txt"} or not ext:
            return await self._parse_markdown_file(input_path), ".md"

        logger.warning(f"不支持的文件类型({ext})，按Markdown处理")
        return await self._parse_markdown_file(input_path), ".md"

    async def _parse_markdown_file(self, md_path: str) -> ParsedContent:
        logger.info(f"读取Markdown文件: {md_path}")
        with open(md_path, "r", encoding="utf-8") as f:
            markdown_content = f.read()
        logger.info(f"Markdown文件大小: {len(markdown_content)} 字符")
        return await self._parse_markdown_content(markdown_content)

    async def _parse_markdown_content(self, markdown_content: str) -> ParsedContent:
        prompt = f"""请分析以下研究方案/论文初稿内容，提取结构化信息。

文档内容:
{markdown_content[:15000]}

请以JSON格式返回，包含以下字段:
{{
    "title": "论文标题（若原文未提供，请根据内容拟定一个规范的学术论文标题，禁止输出'未提供'或解释性文字）",
    "abstract": "摘要内容（若无则概括核心研究内容）",
    "keywords": ["关键词1", "关键词2"],
    "chapters": {{
        "章节名1": "章节内容摘要",
        "章节名2": "章节内容摘要"
    }},
    "tables": [
        {{"name": "表格名", "description": "表格描述", "data_hint": "数据特征"}}
    ],
    "research_method": "研究方法描述",
    "data_description": "数据描述（如果有）"
}}

只返回JSON，不要其他内容。"""

        try:
            response = await self.analyzer_llm.simple_chat(prompt)
            data = load_json_from_response(response)
            logger.info(f"解析成功: 标题={data.get('title', '未知')}")
            return ParsedContent(
                title=data.get("title", ""),
                abstract=data.get("abstract", ""),
                keywords=data.get("keywords", []),
                chapters=data.get("chapters", {}),
                tables=data.get("tables", []),
                raw_markdown=markdown_content,
            )
        except Exception as e:
            logger.error(f"解析Markdown失败: {e}")
            return ParsedContent(raw_markdown=markdown_content)

    # ------------------------------------------------------------------ 提示词组装

    @staticmethod
    def _load_paper_templates() -> dict:
        try:
            with open(PAPER_TEMPLATE_PATH, "rb") as f:
                raw = tomllib.load(f)
            # 模板格式为 [section] + 同名 key，展平为 {section: 模板文本}
            return {
                key: (value.get(key, "") if isinstance(value, dict) else value)
                for key, value in raw.items()
            }
        except Exception as e:
            logger.error(f"加载论文模板失败: {e}")
            return {}

    @staticmethod
    def _render_template(template: str, **placeholders: str) -> str:
        """用 str.replace 渲染模板占位符（避免 format 与 JSON 花括号冲突）"""
        result = template.strip().strip('"').strip()
        for key, value in placeholders.items():
            result = result.replace("{" + key + "}", value)
        return result

    def _build_coder_context(
        self,
        analysis_result: AnalysisResult,
        data_files: List[DataFileInfo],
    ) -> str:
        context = f"""## 项目背景
论文标题: {analysis_result.summary[:200] if analysis_result.summary else ''}
论文类型: {analysis_result.thesis_type.value}
研究方法: {analysis_result.research_method}
技术栈: {', '.join(analysis_result.tech_stack)}

## 数据信息
"""
        if data_files:
            for df in data_files:
                context += f"\n### {df.file_name}\n"
                context += f"- 类型: {df.file_type}\n"
                if df.columns:
                    context += f"- 列名: {df.columns}\n"
                if df.row_count:
                    context += f"- 行数: {df.row_count}\n"
        else:
            context += "无额外数据文件，需要根据论文描述模拟或生成示例数据。\n"

        context += "\n## 论文支撑任务列表\n"
        for t in analysis_result.code_tasks:
            context += f"\n### {t.title} (优先级{t.priority})\n"
            context += f"- 类型: {t.task_type.value}\n"
            context += f"- 对应章节: {t.paper_section or '未指定'}\n"
            context += f"- 描述: {t.description}\n"
        return context

    def _build_task_section_prompt(
        self,
        templates: dict,
        task: CodeTask,
        result: CoderExecutionResult,
        index: int,
        total: int,
    ) -> str:
        template = templates.get("task_section", "")
        code_output = result.code_output[:4000] if result.code_output else "（无代码输出）"
        coder_summary = result.code_summary[:3000] if result.code_summary else "（无总结）"
        if not result.success:
            coder_summary = f"⚠️ 实验执行失败：{result.error_message}\n\n{coder_summary}"

        section_title = f"{index + 1} {task.paper_section or task.title}"
        return self._render_template(
            template,
            section_title=section_title,
            paper_section=task.paper_section or task.title,
            source_excerpt=self._source_markdown[:6000] or "（无原文素材）",
            coder_summary=coder_summary,
            code_output=code_output,
            images_prompt="（图片列表见提示词末尾）",
        )

    @staticmethod
    def _build_thesis_info(parsed_content: ParsedContent, analysis: AnalysisResult) -> str:
        return (
            f"论文标题: {parsed_content.title or '未知'}\n"
            f"研究类型: {analysis.thesis_type.value}\n"
            f"研究方法: {analysis.research_method}\n"
            f"摘要: {parsed_content.abstract[:1000]}\n"
            f"关键词: {', '.join(parsed_content.keywords)}\n"
            f"章节: {', '.join(list(parsed_content.chapters.keys())[:20])}\n"
            f"技术栈: {', '.join(analysis.tech_stack)}"
        )

    @staticmethod
    def _build_tasks_overview(tasks: List[CodeTask]) -> str:
        lines = []
        for i, t in enumerate(tasks, 1):
            lines.append(
                f"任务{i}: {t.title} | 类型: {t.task_type.value} | "
                f"对应章节: {t.paper_section or '未指定'} | 描述: {t.description[:200]} | "
                f"实现方案: {t.plan[:300] if t.plan else '无'}"
            )
        return "\n".join(lines)

    @staticmethod
    def _build_comparison_info(
        tasks: List[CodeTask], results: List[CoderExecutionResult]
    ) -> str:
        lines = []
        for i, (t, r) in enumerate(zip(tasks, results), 1):
            status = "成功" if r.success else f"失败({r.error_message[:100] if r.error_message else '未知'})"
            lines.append(
                f"任务{i}: {t.title}（章节: {t.paper_section or '未指定'}） | 执行状态: {status} | "
                f"实验结果摘要: {r.code_summary[:800] if r.code_summary else '无'} | "
                f"生成图片: {', '.join(r.created_images) if r.created_images else '无'}"
            )
        return "\n".join(lines)

    # ------------------------------------------------------------------ 输出保存

    def _save_intermediate_state(
        self,
        report: ReportOutput,
        task_results: List[CoderExecutionResult],
        task_section_keys: List[str],
    ) -> None:
        """每个任务完成后落盘中间状态，便于崩溃后恢复写作阶段"""
        state = {
            "task_section_keys": task_section_keys,
            "sections": report.sections,
            "task_results": [r.model_dump() for r in task_results],
        }
        save_code_file(
            self.work_dir,
            "_state.json",
            json.dumps(state, ensure_ascii=False, indent=2),
        )

    def _save_analysis_result(self, result: AnalysisResult) -> None:
        analysis_data = {
            "thesis_type": result.thesis_type.value,
            "research_method": result.research_method,
            "data_source": result.data_source.value,
            "tech_stack": result.tech_stack,
            "libraries": result.libraries,
            "code_tasks": [
                {
                    "task_id": t.task_id,
                    "type": t.task_type.value,
                    "title": t.title,
                    "description": t.description,
                    "plan": t.plan,
                    "paper_section": t.paper_section,
                    "paper_results": t.paper_results,
                }
                for t in result.code_tasks
            ],
            "summary": result.summary,
        }
        save_code_file(
            self.work_dir,
            "analysis_result.json",
            json.dumps(analysis_data, ensure_ascii=False, indent=2),
        )

    def _generate_readme(
        self,
        parsed_content: ParsedContent,
        analysis: AnalysisResult,
        tasks: List[CodeTask],
        results: List[CoderExecutionResult],
    ) -> str:
        readme = f"""# {parsed_content.title or '论文初稿'} - 论文初稿项目

## 项目说明

本项目基于研究方案自动生成：**paper.md** 是论文初稿正文（题目/摘要/引言/各章节/结论，
实验数值均来自代码真实执行），**notebook.ipynb** 包含全部验证代码（含执行输出与图表）。

### 论文信息
- **标题**: {parsed_content.title}
- **研究类型**: {analysis.thesis_type.value}
- **研究方法**: {analysis.research_method}

## 文件结构

```
{self.task_id}/
├── paper.md             # 论文初稿正文（期刊/学位论文式）
├── notebook.ipynb       # 全部验证代码（Jupyter，可直接重跑）
├── requirements.txt     # 依赖列表
├── thesis.md            # 研究方案原文（Markdown）
├── analysis_result.json # 方案分析与任务拆解结果
├── *.png                # 论文图表
└── README.md            # 本文件
```

## 使用方式

```bash
pip install -r requirements.txt
jupyter notebook notebook.ipynb
```

## 支撑任务清单（与论文章节对应）

"""
        for i, (t, r) in enumerate(zip(tasks, results), 1):
            status = "✅ 成功" if r.success else "❌ 失败"
            readme += f"{i}. {t.paper_section or t.title}（{t.title}）{status}"
            if r.created_images:
                readme += f"（图表: {', '.join(r.created_images)}）"
            readme += "\n"

        readme += f"""
## 注意事项

1. 代码由 AI 自动生成并真实执行验证，如数据文件不同请调整读取路径
2. paper.md 中的所有实验数值均来自代码真实输出
3. 论文初稿不含参考文献，请根据实际引用情况自行补充

---
生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} · 任务ID: {self.task_id}
"""
        return readme

    def _save_project_files(self, output: ProjectOutput) -> None:
        self._relocate_report_images(output.report.full_report)
        save_code_file(self.work_dir, "paper.md", output.report.full_report)
        requirements_content = "\n".join(output.requirements)
        save_code_file(self.work_dir, "requirements.txt", requirements_content)
        save_code_file(self.work_dir, "README.md", output.readme)
        logger.info(f"项目文件已保存到: {self.work_dir}")

    def _relocate_report_images(self, report_content: str) -> None:
        """论文以裸文件名引用图片；若图片被代码移入子目录，复制回工作目录根以保证链接有效"""
        import re as _re

        referenced = set(_re.findall(r"!\[[^\]]*\]\(([^)]+)\)", report_content))
        for name in referenced:
            if "/" in name or "\\" in name:
                continue
            if os.path.exists(os.path.join(self.work_dir, name)):
                continue
            for root, _dirs, files in os.walk(self.work_dir):
                if name in files:
                    shutil.copy(
                        os.path.join(root, name),
                        os.path.join(self.work_dir, name),
                    )
                    logger.info(f"图片归位: {name} <- {root}")
                    break
            else:
                logger.warning(f"报告引用的图片不存在: {name}")

    # ------------------------------------------------------------------ 事件

    def _publish(self, event_type: str, content: str) -> None:
        logger.info(content)
        self.event_bus.publish(event_type, content)

    def bind_llm_error_hooks(self) -> None:
        """让三个 LLM 实例的失败回调指向本工作流，统一记录与推送"""
        for llm in (self.analyzer_llm, self.coder_llm, self.writer_llm):
            llm.on_error = self._on_llm_error
