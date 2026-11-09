"""
内容分析Agent - 分析研究方案内容，拆解论文支撑任务
"""
import json
import uuid
from typing import List, Optional
from app.core.base_agent import BaseAgent
from app.core.llm import LLM
from app.schemas.models import (
    ParsedContent,
    AnalysisResult,
    CodeTask,
    CodeTaskType,
    ThesisType,
    DataSourceType,
    DataFileInfo
)
from app.utils.logger import logger
from app.utils.json_utils import load_json_from_response


class AnalyzerAgent(BaseAgent):
    """内容分析Agent：研究方案 → 论文支撑任务拆解"""

    def __init__(self, llm: LLM):
        super().__init__(llm)

    @property
    def system_prompt(self) -> str:
        return """你是一个论文研究方案分析专家。输入是研究生撰写的论文初稿素材（系统模型、方法设计、
方案章节等），你的职责是把方案转化为支撑论文的代码任务，使论文的每个关键部分都有代码验证与实验结果。
你需要：
1. 判断研究类型（仿真研究、算法设计、系统设计、数据分析、机器学习等）
2. 分析研究方法和技术路线
3. 按论文章节组织代码任务（模型实现、算法/求解设计、仿真实验、图表生成等）
4. 推荐合适的Python技术栈

任务要具体可执行，数量控制在5-9个，每个任务对应论文的一个主要章节（如"系统模型"、"方法设计"、
"仿真实验"），实验图表任务可适当细化。"""
    
    async def run(
        self, 
        parsed_content: ParsedContent,
        data_files: Optional[List[DataFileInfo]] = None
    ) -> AnalysisResult:
        """
        分析论文内容，生成代码任务
        
        Args:
            parsed_content: 解析后的论文内容
            data_files: 额外的数据文件信息（可选）
            
        Returns:
            AnalysisResult: 分析结果
        """
        logger.info("开始分析研究方案内容...")
        
        # 1. 确定数据来源
        data_source = self._determine_data_source(parsed_content, data_files)
        
        # 2. 分析论文类型和研究方法
        thesis_analysis = await self._analyze_thesis_type(parsed_content)
        
        # 3. 生成代码任务
        code_tasks = await self._generate_code_tasks(
            parsed_content, 
            thesis_analysis,
            data_files
        )
        
        # 4. 确定技术栈
        tech_stack, libraries = await self._determine_tech_stack(
            thesis_analysis, 
            code_tasks
        )
        
        result = AnalysisResult(
            thesis_type=thesis_analysis.get("type", ThesisType.OTHER),
            research_method=thesis_analysis.get("method", ""),
            data_source=data_source,
            data_files=data_files or [],
            code_tasks=code_tasks,
            tech_stack=tech_stack,
            libraries=libraries,
            summary=thesis_analysis.get("summary", "")
        )
        
        logger.info(f"分析完成: {len(code_tasks)} 个代码任务")
        return result
    
    def _determine_data_source(
        self, 
        parsed_content: ParsedContent,
        data_files: Optional[List[DataFileInfo]]
    ) -> DataSourceType:
        """确定数据来源"""
        if data_files and len(data_files) > 0:
            # 有额外数据文件
            if any(f.file_type == "excel" for f in data_files):
                return DataSourceType.EXCEL_FILE
            elif any(f.file_type == "csv" for f in data_files):
                return DataSourceType.CSV_FILE
        
        # 检查PDF中是否有数据
        if parsed_content.tables and len(parsed_content.tables) > 0:
            return DataSourceType.PDF_EMBEDDED
        
        return DataSourceType.NO_DATA
    
    async def _analyze_thesis_type(self, parsed_content: ParsedContent) -> dict:
        """分析论文类型"""
        prompt = f"""分析以下论文信息，确定论文类型和研究方法。

标题: {parsed_content.title}
摘要: {parsed_content.abstract}
关键词: {', '.join(parsed_content.keywords)}
章节: {list(parsed_content.chapters.keys())}

请以JSON格式返回:
{{
    "type": "论文类型(empirical/simulation/algorithm/system_design/data_analysis/machine_learning/other)",
    "method": "研究方法详细描述",
    "summary": "论文主要内容总结",
    "key_techniques": ["关键技术1", "关键技术2"],
    "data_requirements": "数据需求描述"
}}

只返回JSON。"""

        try:
            response = await self.llm.simple_chat(prompt)
            data = load_json_from_response(response)
            
            # 转换类型
            type_mapping = {
                "empirical": ThesisType.EMPIRICAL,
                "simulation": ThesisType.SIMULATION,
                "algorithm": ThesisType.ALGORITHM,
                "system_design": ThesisType.SYSTEM_DESIGN,
                "data_analysis": ThesisType.DATA_ANALYSIS,
                "machine_learning": ThesisType.MACHINE_LEARNING,
            }
            data["type"] = type_mapping.get(data.get("type", ""), ThesisType.OTHER)
            
            return data
        except Exception as e:
            logger.error(f"分析论文类型失败: {e}")
            return {"type": ThesisType.OTHER, "method": "", "summary": ""}
    
    async def _generate_code_tasks(
        self,
        parsed_content: ParsedContent,
        thesis_analysis: dict,
        data_files: Optional[List[DataFileInfo]]
    ) -> List[CodeTask]:
        """生成代码任务列表"""
        
        # 构建数据文件信息
        data_info = ""
        if data_files:
            for df in data_files:
                data_info += f"\n- 文件: {df.file_name}, 类型: {df.file_type}"
                if df.columns:
                    data_info += f", 列: {df.columns[:10]}"
                if df.row_count:
                    data_info += f", 行数: {df.row_count}"
        
        prompt = f"""根据以下论文研究方案，生成支撑论文的 Python 代码任务列表。

研究方案标题: {parsed_content.title}
研究类型: {thesis_analysis.get('type', '')}
研究方法: {thesis_analysis.get('method', '')}
关键技术: {thesis_analysis.get('key_techniques', [])}
数据需求: {thesis_analysis.get('data_requirements', '')}

可用数据文件: {data_info if data_info else '无外部数据文件，需根据方案描述模拟或构造数据'}

方案章节内容:
{json.dumps(parsed_content.chapters, ensure_ascii=False, indent=2)[:3000]}

背景说明：这是研究生自己的论文初稿素材，需要用代码实现模型/算法并产出实验结果，
作为论文各章节的正文素材。任务按论文章节组织（模型实现在前，求解与实验在后，图表收尾），
数量控制在5-9个，每个任务产出论文一个章节的验证内容。任务类型包括:
- data_preprocessing: 数据预处理
- data_analysis: 数据分析
- model_training: 模型训练
- visualization: 可视化
- algorithm_impl: 算法/模型实现
- statistical_test: 统计检验
- simulation: 仿真模拟
- utility: 工具函数

以JSON格式返回:
{{
    "tasks": [
        {{
            "task_type": "任务类型",
            "title": "任务标题",
            "description": "详细描述",
            "plan": "实现方案：使用的方法、实现步骤、关键参数及其来源（方案给定/自行设定并注明）",
            "paper_section": "该任务成果对应的论文章节标题（不含编号，如'系统模型与信道设计'、'仿真实验与结果分析'）",
            "paper_results": "方案中预期的结论或参考数值（若方案未给出则写无）",
            "requirements": ["具体要求1", "具体要求2"],
            "input_data": "输入数据描述",
            "expected_output": "期望输出（结果表格/指标/图表）",
            "priority": 0
        }}
    ]
}}

priority数字越小优先级越高，按论文行文顺序排列任务。只返回JSON。"""

        try:
            response = await self.llm.simple_chat(prompt)
            data = load_json_from_response(response)

            tasks = []
            for i, task_data in enumerate(data.get("tasks", [])):
                task_type = self._parse_task_type(task_data.get("task_type", ""))

                task = CodeTask(
                    task_id=f"task_{uuid.uuid4().hex[:8]}",
                    task_type=task_type,
                    title=task_data.get("title", f"任务{i+1}"),
                    description=task_data.get("description", ""),
                    plan=task_data.get("plan", ""),
                    paper_section=task_data.get("paper_section", ""),
                    paper_results=task_data.get("paper_results", ""),
                    requirements=task_data.get("requirements", []),
                    input_data=task_data.get("input_data"),
                    expected_output=task_data.get("expected_output"),
                    priority=task_data.get("priority", i)
                )
                tasks.append(task)

            return tasks

        except Exception as e:
            logger.error(f"生成代码任务失败: {e}")
            return []
    
    async def _determine_tech_stack(
        self, 
        thesis_analysis: dict,
        code_tasks: List[CodeTask]
    ) -> tuple:
        """确定技术栈和依赖库"""
        
        task_types = [t.task_type.value for t in code_tasks]
        
        prompt = f"""根据以下信息，推荐Python技术栈和需要的库。

论文类型: {thesis_analysis.get('type', '')}
关键技术: {thesis_analysis.get('key_techniques', [])}
代码任务类型: {task_types}

请以JSON格式返回:
{{
    "tech_stack": ["技术栈1", "技术栈2"],
    "libraries": ["库名1", "库名2"]
}}

libraries应该是可以pip install的包名。只返回JSON。"""

        try:
            response = await self.llm.simple_chat(prompt)
            data = load_json_from_response(response)
            
            return data.get("tech_stack", []), data.get("libraries", [])
            
        except Exception as e:
            logger.error(f"确定技术栈失败: {e}")
            # 返回默认库
            return (
                ["Python", "Pandas", "NumPy"],
                ["pandas", "numpy", "matplotlib", "scikit-learn"]
            )
    
    def _parse_task_type(self, type_str: str) -> CodeTaskType:
        """解析任务类型"""
        type_mapping = {
            "data_preprocessing": CodeTaskType.DATA_PREPROCESSING,
            "data_analysis": CodeTaskType.DATA_ANALYSIS,
            "model_training": CodeTaskType.MODEL_TRAINING,
            "visualization": CodeTaskType.VISUALIZATION,
            "algorithm_impl": CodeTaskType.ALGORITHM_IMPL,
            "statistical_test": CodeTaskType.STATISTICAL_TEST,
            "simulation": CodeTaskType.SIMULATION,
            "utility": CodeTaskType.UTILITY,
        }
        return type_mapping.get(type_str.lower(), CodeTaskType.UTILITY)
