"""
数据模型定义
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from enum import Enum


class DataSourceType(str, Enum):
    """数据来源类型"""
    PDF_EMBEDDED = "pdf_embedded"      # PDF内嵌数据
    EXCEL_FILE = "excel_file"          # Excel文件
    CSV_FILE = "csv_file"              # CSV文件
    NO_DATA = "no_data"                # 无数据需求


class ThesisType(str, Enum):
    """论文类型"""
    EMPIRICAL = "empirical"            # 实证研究
    SIMULATION = "simulation"          # 仿真研究
    ALGORITHM = "algorithm"            # 算法设计
    SYSTEM_DESIGN = "system_design"    # 系统设计
    DATA_ANALYSIS = "data_analysis"    # 数据分析
    MACHINE_LEARNING = "machine_learning"  # 机器学习
    OTHER = "other"                    # 其他


class CodeTaskType(str, Enum):
    """代码任务类型"""
    DATA_PREPROCESSING = "data_preprocessing"   # 数据预处理
    DATA_ANALYSIS = "data_analysis"             # 数据分析
    MODEL_TRAINING = "model_training"           # 模型训练
    VISUALIZATION = "visualization"             # 可视化
    ALGORITHM_IMPL = "algorithm_impl"           # 算法实现
    STATISTICAL_TEST = "statistical_test"       # 统计检验
    SIMULATION = "simulation"                   # 仿真模拟
    UTILITY = "utility"                         # 工具函数


class DataFileInfo(BaseModel):
    """数据文件信息"""
    file_path: str
    file_type: str  # excel, csv, etc.
    file_name: str
    columns: Optional[List[str]] = None
    row_count: Optional[int] = None
    sample_data: Optional[List[Dict[str, Any]]] = None
    description: Optional[str] = None


class ParsedContent(BaseModel):
    """PDF解析后的内容"""
    title: str = ""
    abstract: str = ""
    keywords: List[str] = Field(default_factory=list)
    chapters: Dict[str, str] = Field(default_factory=dict)  # 章节名: 内容
    tables: List[Dict[str, Any]] = Field(default_factory=list)  # 表格数据
    figures: List[str] = Field(default_factory=list)  # 图片描述
    references: List[str] = Field(default_factory=list)  # 参考文献
    raw_markdown: str = ""  # 原始markdown
    embedded_data: Optional[List[Dict[str, Any]]] = None  # PDF内嵌的数据


class CodeTask(BaseModel):
    """论文支撑任务"""
    task_id: str
    task_type: CodeTaskType
    title: str
    description: str
    plan: str = ""                       # 实现方案：方法、步骤、关键参数
    paper_section: str = ""              # 对应的论文章节标题
    paper_results: str = ""              # 预期结论或参考数值
    requirements: List[str] = Field(default_factory=list)
    dependencies: List[str] = Field(default_factory=list)  # 依赖的其他任务ID
    input_data: Optional[str] = None  # 输入数据描述
    expected_output: Optional[str] = None  # 期望输出描述
    priority: int = 0  # 优先级，数字越小优先级越高


class AnalysisResult(BaseModel):
    """内容分析结果"""
    thesis_type: ThesisType
    research_method: str  # 研究方法描述
    data_source: DataSourceType
    data_files: List[DataFileInfo] = Field(default_factory=list)
    code_tasks: List[CodeTask] = Field(default_factory=list)
    tech_stack: List[str] = Field(default_factory=list)  # 推荐技术栈
    libraries: List[str] = Field(default_factory=list)  # 需要的Python库
    summary: str = ""  # 分析总结


class CoderExecutionResult(BaseModel):
    """代码手单任务执行结果（Coder → Writer 的 A2A 消息）"""
    task_id: str
    section: str                        # notebook/report 中的分节名
    code_summary: str = ""              # LLM 对本次执行过程的总结
    code_output: str = ""               # 代码文本输出（截断后）
    created_images: List[str] = Field(default_factory=list)  # 本任务生成的图片文件名
    success: bool = True
    error_message: Optional[str] = None


class ReportOutput(BaseModel):
    """论文正文（paper.md）"""
    sections: Dict[str, str] = Field(default_factory=dict)  # section_key: 内容
    sequence: List[str] = Field(default_factory=list)       # 章节拼接顺序
    full_report: str = ""

    def assemble(self) -> str:
        """按顺序拼接全文"""
        parts = [self.sections[key] for key in self.sequence if key in self.sections]
        self.full_report = "\n\n".join(parts)
        return self.full_report


class ProjectOutput(BaseModel):
    """项目输出"""
    project_name: str
    thesis_title: str
    report: ReportOutput = Field(default_factory=ReportOutput)
    notebook_file: str = "notebook.ipynb"
    requirements: List[str] = Field(default_factory=list)
    readme: str = ""
    task_results: List[CoderExecutionResult] = Field(default_factory=list)
