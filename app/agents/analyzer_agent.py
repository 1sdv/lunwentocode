"""
内容分析Agent - 分析论文内容，提取代码需求
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
    """内容分析Agent"""
    
    def __init__(self, llm: LLM):
        super().__init__(llm)
        
    @property
    def system_prompt(self) -> str:
        return """你是一个专业的论文分析专家，擅长分析毕业论文并提取代码实现需求。
你需要:
1. 识别论文类型（实证研究、仿真、算法设计等）
2. 分析研究方法和技术路线
3. 识别数据处理需求
4. 提取需要实现的代码任务
5. 推荐合适的Python技术栈

请确保分析全面、准确，生成的代码任务要具体可执行。"""
    
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
        logger.info("开始分析论文内容...")
        
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
        
        prompt = f"""根据以下论文信息，生成需要实现的Python代码任务列表。

论文标题: {parsed_content.title}
论文类型: {thesis_analysis.get('type', '')}
研究方法: {thesis_analysis.get('method', '')}
关键技术: {thesis_analysis.get('key_techniques', [])}
数据需求: {thesis_analysis.get('data_requirements', '')}

可用数据文件: {data_info if data_info else '无额外数据文件，需要从论文中提取或模拟数据'}

章节内容:
{json.dumps(parsed_content.chapters, ensure_ascii=False, indent=2)[:3000]}

请生成代码任务列表，每个任务应该具体、可执行。任务类型包括:
- data_preprocessing: 数据预处理
- data_analysis: 数据分析
- model_training: 模型训练
- visualization: 可视化
- algorithm_impl: 算法实现
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
            "requirements": ["具体要求1", "具体要求2"],
            "input_data": "输入数据描述",
            "expected_output": "期望输出",
            "priority": 0
        }}
    ]
}}

按执行顺序排列任务，priority数字越小优先级越高。只返回JSON。"""

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
