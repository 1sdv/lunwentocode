"""
工作流管理 - 协调各Agent完成论文代码生成
"""
import os
import shutil
import uuid
from datetime import datetime
from typing import List, Optional, Tuple
from pathlib import Path

from app.agents import AnalyzerAgent, CoderAgent, ValidatorAgent
from app.agents.parser_agent import ParserAgent
from app.core.llm import LLM
from app.schemas.models import (
    ParsedContent,
    AnalysisResult,
    GeneratedCode,
    ValidationResult,
    ProjectOutput,
    DataFileInfo
)
from app.utils.file_utils import scan_data_files, create_work_dir, save_code_file
from app.utils.logger import logger
from app.utils.json_utils import load_json_from_response
from app.config.settings import settings


class ThesisToCodeWorkflow:
    """毕业论文代码生成工作流"""
    
    def __init__(
        self, 
        analyzer_llm: Optional[LLM] = None,
        coder_llm: Optional[LLM] = None
    ):
        """
        初始化工作流
        
        Args:
            analyzer_llm: 分析LLM实例，用于论文分析
            coder_llm: 代码LLM实例，用于代码生成和修复
        """
        self.analyzer_llm = analyzer_llm or LLM()
        self.coder_llm = coder_llm or LLM()
        
        # 初始化各Agent，使用不同的LLM
        # AnalyzerAgent使用分析LLM
        self.analyzer_agent = AnalyzerAgent(self.analyzer_llm)
        # ParserAgent主要处理PDF转Markdown
        self.parser_agent = ParserAgent(self.analyzer_llm)
        # CoderAgent和ValidatorAgent使用代码LLM
        self.coder_agent = CoderAgent(self.coder_llm)
        self.validator_agent = ValidatorAgent(self.coder_llm)
        
        # 工作状态
        self.task_id: str = ""
        self.work_dir: str = ""
        
    async def run(
        self,
        md_path: str,
        data_dir: Optional[str] = None,
        output_dir: Optional[str] = None
    ) -> ProjectOutput:
        """
        执行完整的工作流
        
        Args:
            md_path: 论文文件路径（支持Markdown/PDF）
            data_dir: 数据文件目录（可选）
            output_dir: 输出目录（可选）
            
        Returns:
            ProjectOutput: 项目输出结果
        """
        # 生成任务ID
        self.task_id = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        logger.info(f"开始任务: {self.task_id}")
        
        # 创建工作目录
        base_output = output_dir or settings.OUTPUT_DIR
        self.work_dir = create_work_dir(self.task_id, base_output)
        
        try:
            # Phase 1: 读取Markdown文件
            logger.info("=" * 50)
            logger.info("Phase 1: 读取Markdown文件")
            logger.info("=" * 50)
            parsed_content, source_ext = await self._load_input_content(md_path)
            
            # 保存原始输入和Markdown版本
            if source_ext == ".pdf":
                shutil.copy2(md_path, os.path.join(self.work_dir, "thesis.pdf"))
                save_code_file(
                    self.work_dir,
                    "thesis.md",
                    parsed_content.raw_markdown or ""
                )
            else:
                shutil.copy2(md_path, os.path.join(self.work_dir, "thesis.md"))
            
            # Phase 2: 扫描数据文件
            logger.info("=" * 50)
            logger.info("Phase 2: 数据文件扫描")
            logger.info("=" * 50)
            data_files = []
            if data_dir and os.path.exists(data_dir):
                data_files = scan_data_files(data_dir)
                # 复制数据文件到工作目录
                for df in data_files:
                    dest = os.path.join(self.work_dir, df.file_name)
                    shutil.copy2(df.file_path, dest)
                    df.file_path = dest  # 更新路径
                logger.info(f"发现 {len(data_files)} 个数据文件")
            else:
                logger.info("无额外数据文件")
            
            # Phase 3: 内容分析
            logger.info("=" * 50)
            logger.info("Phase 3: 内容分析")
            logger.info("=" * 50)
            analysis_result = await self.analyzer_agent.run(parsed_content, data_files)
            
            # 保存分析结果
            self._save_analysis_result(analysis_result)
            
            # Phase 4: 代码生成
            logger.info("=" * 50)
            logger.info("Phase 4: 代码生成")
            logger.info("=" * 50)
            generated_codes = await self.coder_agent.run(analysis_result, data_files)
            
            # Phase 5: 代码验证
            logger.info("=" * 50)
            logger.info("Phase 5: 代码验证")
            logger.info("=" * 50)
            validation_results = await self.validator_agent.run(generated_codes)
            
            # 应用修复
            final_codes = self._apply_fixes(generated_codes, validation_results)
            
            # Phase 6: 生成项目输出
            logger.info("=" * 50)
            logger.info("Phase 6: 生成项目")
            logger.info("=" * 50)
            project_output = self._generate_project_output(
                parsed_content,
                analysis_result,
                final_codes
            )
            
            # 保存所有文件
            self._save_project_files(project_output)
            
            logger.info(f"任务完成: {self.task_id}")
            logger.info(f"输出目录: {self.work_dir}")
            
            return project_output
            
        except Exception as e:
            logger.error(f"工作流执行失败: {e}")
            raise
    
    async def _load_input_content(self, input_path: str) -> Tuple[ParsedContent, str]:
        """
        根据文件类型加载并解析内容
        
        Returns:
            (ParsedContent, 扩展名)
        """
        ext = Path(input_path).suffix.lower()
        
        if ext == ".pdf":
            logger.info("检测到PDF论文，使用ParserAgent解析")
            parsed = await self.parser_agent.run(input_path)
            if not parsed.raw_markdown:
                parsed.raw_markdown = ""
            return parsed, ext
        
        if ext in {".md", ".markdown", ".txt"} or not ext:
            parsed = await self._parse_markdown_file(input_path)
            return parsed, ".md"
        
        logger.warning(f"不支持的文件类型({ext})，按Markdown处理")
        parsed = await self._parse_markdown_file(input_path)
        return parsed, ".md"
    
    async def _parse_markdown_file(self, md_path: str) -> ParsedContent:
        """
        读取并解析Markdown文件
        
        Args:
            md_path: Markdown文件路径
            
        Returns:
            ParsedContent: 解析后的内容
        """
        logger.info(f"读取Markdown文件: {md_path}")
        
        # 读取Markdown内容
        with open(md_path, 'r', encoding='utf-8') as f:
            markdown_content = f.read()
        
        logger.info(f"Markdown文件大小: {len(markdown_content)} 字符")
        return await self._parse_markdown_content(markdown_content)
    
    async def _parse_markdown_content(self, markdown_content: str) -> ParsedContent:
        """使用LLM解析Markdown字符串"""
        prompt = f"""请分析以下Markdown文档，提取论文的结构化信息。

文档内容:
{markdown_content[:15000]}

请以JSON格式返回，包含以下字段:
{{
    "title": "论文标题",
    "abstract": "摘要内容",
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
                raw_markdown=markdown_content
            )
            
        except Exception as e:
            logger.error(f"解析Markdown失败: {e}")
            # 返回基本内容，让后续流程继续
            return ParsedContent(raw_markdown=markdown_content)
    
    def _save_analysis_result(self, result: AnalysisResult) -> None:
        """保存分析结果"""
        import json
        
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
                    "description": t.description
                }
                for t in result.code_tasks
            ],
            "summary": result.summary
        }
        
        save_code_file(
            self.work_dir, 
            "analysis_result.json", 
            json.dumps(analysis_data, ensure_ascii=False, indent=2)
        )
    
    def _apply_fixes(
        self, 
        codes: List[GeneratedCode], 
        results: List[ValidationResult]
    ) -> List[GeneratedCode]:
        """应用验证修复"""
        fixed_codes = []
        
        result_map = {r.task_id: r for r in results}
        
        for code in codes:
            result = result_map.get(code.task_id)
            if result and result.fixed_code:
                fixed_codes.append(GeneratedCode(
                    task_id=code.task_id,
                    file_name=code.file_name,
                    code=result.fixed_code,
                    description=code.description,
                    dependencies=code.dependencies
                ))
            else:
                fixed_codes.append(code)
        
        return fixed_codes
    
    def _generate_project_output(
        self,
        parsed_content: ParsedContent,
        analysis_result: AnalysisResult,
        codes: List[GeneratedCode]
    ) -> ProjectOutput:
        """生成项目输出"""
        
        # 收集所有文件
        files = {code.file_name: code.code for code in codes}
        
        # 收集所有依赖
        all_deps = set()
        for code in codes:
            all_deps.update(code.dependencies)
        
        # 添加基础依赖
        all_deps.update(analysis_result.libraries)
        
        # 生成requirements.txt
        requirements = sorted(list(all_deps))
        
        # 生成README
        readme = self._generate_readme(parsed_content, analysis_result, codes)
        
        # 生成运行说明
        run_instructions = self._generate_run_instructions(codes)
        
        return ProjectOutput(
            project_name=self.task_id,
            thesis_title=parsed_content.title,
            files=files,
            requirements=requirements,
            readme=readme,
            run_instructions=run_instructions
        )
    
    def _generate_readme(
        self,
        parsed_content: ParsedContent,
        analysis_result: AnalysisResult,
        codes: List[GeneratedCode]
    ) -> str:
        """生成README文档"""
        readme = f"""# {parsed_content.title or '毕业论文代码'}

## 项目说明

本项目是根据毕业论文自动生成的Python代码实现。

### 论文信息
- **标题**: {parsed_content.title}
- **类型**: {analysis_result.thesis_type.value}
- **研究方法**: {analysis_result.research_method}

### 技术栈
{chr(10).join(f'- {tech}' for tech in analysis_result.tech_stack)}

## 文件结构

```
{self.task_id}/
"""
        for code in codes:
            readme += f"├── {code.file_name}  # {code.description}\n"
        
        readme += f"""├── requirements.txt  # 依赖列表
├── README.md  # 项目说明
└── analysis_result.json  # 分析结果
```

## 安装依赖

```bash
pip install -r requirements.txt
```

## 运行方式

```bash
python main.py
```

## 代码模块说明

"""
        for code in codes:
            readme += f"### {code.file_name}\n{code.description}\n\n"
        
        readme += """
## 注意事项

1. 请确保已安装所有依赖
2. 如有数据文件，请放在项目目录下
3. 代码由AI自动生成，可能需要根据实际情况调整

## 生成信息

- 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
- 任务ID: {self.task_id}
"""
        return readme
    
    def _generate_run_instructions(self, codes: List[GeneratedCode]) -> str:
        """生成运行说明"""
        instructions = """# 运行说明

## 环境准备

1. 确保Python版本 >= 3.8
2. 安装依赖: pip install -r requirements.txt

## 运行步骤

"""
        for i, code in enumerate(codes, 1):
            if code.file_name != "main.py":
                instructions += f"{i}. 运行 {code.file_name}: `python {code.file_name}`\n"
        
        instructions += f"""
## 或者直接运行主程序

```bash
python main.py
```

## 常见问题

1. 如果遇到模块导入错误，请检查是否安装了所有依赖
2. 如果数据文件路径错误，请修改代码中的文件路径
3. 如有其他问题，请检查错误信息并相应修改代码
"""
        return instructions
    
    def _save_project_files(self, output: ProjectOutput) -> None:
        """保存项目文件"""
        # 保存代码文件
        for file_name, code in output.files.items():
            save_code_file(self.work_dir, file_name, code)
        
        # 保存requirements.txt
        requirements_content = "\n".join(output.requirements)
        save_code_file(self.work_dir, "requirements.txt", requirements_content)
        
        # 保存README
        save_code_file(self.work_dir, "README.md", output.readme)
        
        # 保存运行说明
        save_code_file(self.work_dir, "RUN_INSTRUCTIONS.md", output.run_instructions)
        
        logger.info(f"项目文件已保存到: {self.work_dir}")
