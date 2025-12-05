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
    """代码任务"""
    task_id: str
    task_type: CodeTaskType
    title: str
    description: str
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


class GeneratedCode(BaseModel):
    """生成的代码"""
    task_id: str
    file_name: str
    code: str
    description: str
    dependencies: List[str] = Field(default_factory=list)


class ValidationResult(BaseModel):
    """代码验证结果"""
    task_id: str
    is_valid: bool
    syntax_check: bool = True
    import_check: bool = True
    execution_check: bool = False  # 是否通过执行测试
    error_message: Optional[str] = None
    suggestions: List[str] = Field(default_factory=list)
    fixed_code: Optional[str] = None


class ProjectOutput(BaseModel):
    """项目输出"""
    project_name: str
    thesis_title: str
    files: Dict[str, str] = Field(default_factory=dict)  # 文件名: 代码内容
    requirements: List[str] = Field(default_factory=list)
    readme: str = ""
    run_instructions: str = ""
