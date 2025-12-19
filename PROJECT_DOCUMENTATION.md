# LunwenToCode 项目详细说明文档

> 科研论文/毕业论文代码生成系统 - 将论文Markdown自动转换为可运行的Python代码

---

## 目录

1. [项目概述](#1-项目概述)
2. [系统架构](#2-系统架构)
3. [核心组件详解](#3-核心组件详解)
4. [处理流程](#4-处理流程)
5. [数据模型](#5-数据模型)
6. [配置说明](#6-配置说明)
7. [使用方式](#7-使用方式)
8. [技术栈](#8-技术栈)
9. [扩展与定制](#9-扩展与定制)

---

## 1. 项目概述

### 1.1 项目定位

**LunwenToCode** 是一个基于大语言模型（LLM）的智能代码生成系统，专门用于将科研论文或毕业论文自动转换为可运行的Python代码。系统采用多Agent协作架构，通过分析论文内容、识别研究方法、提取代码需求，最终生成完整的Python项目。

### 1.2 核心功能

| 功能 | 描述 |
|------|------|
| 📄 **文稿解析** | 支持Markdown和PDF格式论文的读取与解析 |
| 🔍 **智能分析** | 自动识别论文类型、研究方法和代码需求 |
| 💻 **代码生成** | 根据论文内容生成完整的Python代码 |
| ✅ **自动验证** | 语法检查、导入验证和自动修复 |
| 📊 **数据支持** | 支持额外Excel/CSV数据文件 |

### 1.3 支持的论文类型

- **实证研究 (Empirical)** - 基于数据的实证分析
- **仿真研究 (Simulation)** - 模拟仿真类研究
- **算法设计 (Algorithm)** - 算法实现与优化
- **系统设计 (System Design)** - 系统架构设计
- **数据分析 (Data Analysis)** - 数据处理与分析
- **机器学习 (Machine Learning)** - 机器学习模型

---

## 2. 系统架构

### 2.1 整体架构图

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         LunwenToCode 系统架构                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────┐                                                            │
│  │   输入层    │  Markdown/PDF论文 + Excel/CSV数据文件                        │
│  └──────┬──────┘                                                            │
│         │                                                                   │
│         ▼                                                                   │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                        工作流引擎 (Workflow)                         │    │
│  │  ┌───────────┐   ┌───────────┐   ┌───────────┐   ┌───────────┐      │    │
│  │  │  Parser   │ → │ Analyzer  │ → │  Coder    │ → │ Validator │      │    │
│  │  │  Agent    │   │  Agent    │   │  Agent    │   │  Agent    │      │    │
│  │  └───────────┘   └───────────┘   └───────────┘   └───────────┘      │    │
│  │       ↓               ↓               ↓               ↓             │    │
│  │   PDF转MD        提取需求         生成代码         验证修复           │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│         │                                                                   │
│         ▼                                                                   │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                          LLM 服务层                                  │    │
│  │  ┌─────────────────────┐    ┌─────────────────────┐                 │    │
│  │  │   Analyzer LLM      │    │    Coder LLM        │                 │    │
│  │  │   (论文分析专用)     │    │   (代码生成专用)     │                 │    │
│  │  └─────────────────────┘    └─────────────────────┘                 │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│         │                                                                   │
│         ▼                                                                   │
│  ┌─────────────┐                                                            │
│  │   输出层    │  Python项目 (代码文件 + requirements.txt + README)           │
│  └─────────────┘                                                            │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 双LLM架构设计

系统采用**双LLM架构**，将论文分析和代码生成任务分离：

| LLM类型 | 用途 | 使用的Agent |
|---------|------|-------------|
| **Analyzer LLM** | 论文内容分析、结构提取 | AnalyzerAgent, ParserAgent |
| **Coder LLM** | 代码生成、代码修复 | CoderAgent, ValidatorAgent |

**设计优势**：
- 可以为不同任务选择最适合的模型
- 分析任务可使用擅长理解的模型
- 代码任务可使用擅长编程的模型
- 降低单一模型的负载压力

### 2.3 项目目录结构

```
lunwentocode/
├── app/                          # 核心应用模块
│   ├── __init__.py
│   ├── agents/                   # Agent实现
│   │   ├── __init__.py
│   │   ├── analyzer_agent.py     # 内容分析Agent
│   │   ├── coder_agent.py        # 代码生成Agent
│   │   ├── parser_agent.py       # PDF解析Agent
│   │   └── validator_agent.py    # 代码验证Agent
│   ├── core/                     # 核心模块
│   │   ├── __init__.py
│   │   ├── base_agent.py         # Agent基类
│   │   ├── llm.py                # LLM封装
│   │   └── workflow.py           # 工作流引擎
│   ├── schemas/                  # 数据模型
│   │   ├── __init__.py
│   │   └── models.py             # Pydantic模型定义
│   ├── config/                   # 配置模块
│   │   ├── __init__.py
│   │   └── settings.py           # 系统配置
│   └── utils/                    # 工具函数
│       ├── __init__.py
│       ├── file_utils.py         # 文件处理工具
│       ├── json_utils.py         # JSON解析工具
│       └── logger.py             # 日志工具
├── output/                       # 输出目录
├── main.py                       # 命令行入口
├── app.py                        # Web界面入口(Gradio)
├── requirements.txt              # 依赖列表
├── .env                          # 环境变量配置
└── README.md                     # 项目说明
```

---

## 3. 核心组件详解

### 3.1 工作流引擎 (ThesisToCodeWorkflow)

**文件位置**: `app/core/workflow.py`

工作流引擎是整个系统的**核心调度器**，负责协调各个Agent完成论文代码生成任务。

#### 主要职责

1. **任务管理** - 生成任务ID，创建工作目录
2. **流程编排** - 按顺序调用各Agent
3. **数据传递** - 在Agent之间传递处理结果
4. **结果整合** - 生成最终的项目输出

#### 核心方法

```python
class ThesisToCodeWorkflow:
    async def run(
        self,
        md_path: str,           # 论文文件路径
        data_dir: Optional[str], # 数据文件目录
        output_dir: Optional[str] # 输出目录
    ) -> ProjectOutput:
        """执行完整的工作流"""
```

#### 工作流六阶段

| 阶段 | 名称 | 描述 |
|------|------|------|
| Phase 1 | 读取Markdown文件 | 加载论文内容，支持PDF自动转换 |
| Phase 2 | 数据文件扫描 | 扫描并提取Excel/CSV数据文件信息 |
| Phase 3 | 内容分析 | 调用AnalyzerAgent分析论文 |
| Phase 4 | 代码生成 | 调用CoderAgent生成代码 |
| Phase 5 | 代码验证 | 调用ValidatorAgent验证并修复 |
| Phase 6 | 生成项目 | 整合输出，生成完整项目 |

---

### 3.2 Agent基类 (BaseAgent)

**文件位置**: `app/core/base_agent.py`

所有Agent的抽象基类，采用**无状态设计**，每次调用独立无历史依赖。

#### 设计特点

- **无状态**: 每次LLM调用独立，不保留对话历史
- **统一接口**: 所有Agent继承相同的基类
- **灵活调用**: 支持普通调用和工具调用两种模式

#### 核心方法

```python
class BaseAgent(ABC):
    @property
    @abstractmethod
    def system_prompt(self) -> str:
        """系统提示词 - 每个Agent必须实现"""
        pass
    
    @abstractmethod
    async def run(self, *args, **kwargs) -> Any:
        """执行Agent任务 - 每个Agent必须实现"""
        pass
    
    async def call_llm(self, prompt: str, context: Optional[str] = None) -> str:
        """独立调用LLM（无历史依赖）"""
        
    async def call_llm_with_tools(self, prompt: str, tools: List[Dict], ...) -> Any:
        """使用工具调用LLM"""
```

---

### 3.3 PDF解析Agent (ParserAgent)

**文件位置**: `app/agents/parser_agent.py`

负责将PDF论文转换为Markdown格式。

#### 解析策略

```
PDF输入
    │
    ├─── URL方式 ──→ 直接提交Mineru API
    │
    └─── 本地文件
            │
            ├─── 尝试上传到Mineru API
            │
            └─── 失败则使用PyMuPDF本地解析（备用方案）
```

#### 核心流程

1. **判断输入类型** - URL或本地文件
2. **调用Mineru API** - 云端PDF转Markdown服务
3. **轮询任务结果** - 等待转换完成
4. **本地备用解析** - 使用PyMuPDF提取文本
5. **结构化解析** - 使用LLM提取论文结构

#### 输出结构

```python
ParsedContent(
    title="论文标题",
    abstract="摘要内容",
    keywords=["关键词1", "关键词2"],
    chapters={"章节名": "章节内容"},
    tables=[{"name": "表格名", "description": "描述"}],
    raw_markdown="原始Markdown内容"
)
```

---

### 3.4 内容分析Agent (AnalyzerAgent)

**文件位置**: `app/agents/analyzer_agent.py`

分析论文内容，提取代码实现需求。

#### 分析流程

```
ParsedContent输入
        │
        ▼
┌───────────────────┐
│ 1. 确定数据来源    │  → DataSourceType
└───────────────────┘
        │
        ▼
┌───────────────────┐
│ 2. 分析论文类型    │  → ThesisType + 研究方法
└───────────────────┘
        │
        ▼
┌───────────────────┐
│ 3. 生成代码任务    │  → List[CodeTask]
└───────────────────┘
        │
        ▼
┌───────────────────┐
│ 4. 确定技术栈      │  → tech_stack + libraries
└───────────────────┘
        │
        ▼
    AnalysisResult
```

#### 代码任务类型

| 任务类型 | 描述 |
|----------|------|
| `data_preprocessing` | 数据预处理 |
| `data_analysis` | 数据分析 |
| `model_training` | 模型训练 |
| `visualization` | 可视化 |
| `algorithm_impl` | 算法实现 |
| `statistical_test` | 统计检验 |
| `simulation` | 仿真模拟 |
| `utility` | 工具函数 |

---

### 3.5 代码生成Agent (CoderAgent)

**文件位置**: `app/agents/coder_agent.py`

根据分析结果生成Python代码。

#### 设计特点

- **无状态设计**: 每个任务独立调用LLM，不依赖历史
- **工具调用**: 使用OpenAI Function Calling生成结构化代码
- **上下文共享**: 所有任务共享项目上下文信息

#### 代码生成工具定义

```python
CODER_TOOLS = [{
    "type": "function",
    "function": {
        "name": "generate_code",
        "parameters": {
            "properties": {
                "code": "完整的Python代码",
                "file_name": "代码文件名",
                "description": "代码功能描述",
                "dependencies": "依赖的Python库列表"
            }
        }
    }
}]
```

#### 生成流程

1. **构建上下文** - 整合项目背景、数据信息、任务列表
2. **按优先级排序** - 按任务优先级顺序生成
3. **独立生成代码** - 每个任务独立调用LLM
4. **生成主程序** - 最后生成main.py协调所有模块

#### 代码规范

- 代码必须完整、可直接运行
- 包含必要的import语句
- 添加清晰的中文注释
- 包含main函数作为入口
- 包含错误处理

---

### 3.6 代码验证Agent (ValidatorAgent)

**文件位置**: `app/agents/validator_agent.py`

验证生成的代码并自动修复错误。

#### 验证流程

```
GeneratedCode输入
        │
        ▼
┌───────────────────┐
│ 1. 语法检查        │  → ast.parse()
│    (失败则修复)    │
└───────────────────┘
        │
        ▼
┌───────────────────┐
│ 2. 导入检查        │  → 检查import语句
│    (失败则修复)    │
└───────────────────┘
        │
        ▼
┌───────────────────┐
│ 3. 静态分析        │  → 代码质量检查
└───────────────────┘
        │
        ▼
    ValidationResult
```

#### 验证项目

| 检查项 | 方法 | 说明 |
|--------|------|------|
| 语法检查 | `ast.parse()` | 检查Python语法正确性 |
| 导入检查 | AST分析 | 检查import语句 |
| 静态分析 | AST遍历 | 检查main函数、异常处理、文档字符串 |

#### 自动修复机制

- 最大重试次数: 5次（可配置）
- 使用LLM修复代码错误
- 修复后重新验证
- 超过重试次数返回失败

---

### 3.7 LLM封装 (LLM)

**文件位置**: `app/core/llm.py`

统一的LLM调用封装，基于OpenAI SDK。

#### 特性

- **异步调用**: 使用AsyncOpenAI客户端
- **超时控制**: 默认5分钟超时
- **自动重试**: 最多3次重试，指数退避
- **工具调用**: 支持Function Calling

#### 核心方法

```python
class LLM:
    async def chat(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict]] = None,
        temperature: float = 1,
        max_tokens: Optional[int] = None,
        max_retries: int = 3
    ) -> Any:
        """调用LLM进行对话"""
    
    async def simple_chat(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """简单对话，返回文本内容"""
```

---

## 4. 处理流程

### 4.1 完整处理流程图

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            完整处理流程                                      │
└─────────────────────────────────────────────────────────────────────────────┘

用户输入
    │
    ├── 论文文件 (Markdown/PDF)
    └── 数据文件 (Excel/CSV) [可选]
    │
    ▼
╔═══════════════════════════════════════════════════════════════════════════╗
║  Phase 1: 读取Markdown文件                                                 ║
╠═══════════════════════════════════════════════════════════════════════════╣
║  • 检测文件类型 (.md/.pdf/.txt)                                            ║
║  • PDF文件 → ParserAgent → Mineru API / PyMuPDF                           ║
║  • Markdown文件 → 直接读取                                                 ║
║  • 使用LLM解析文档结构 → ParsedContent                                     ║
╚═══════════════════════════════════════════════════════════════════════════╝
    │
    ▼
╔═══════════════════════════════════════════════════════════════════════════╗
║  Phase 2: 数据文件扫描                                                     ║
╠═══════════════════════════════════════════════════════════════════════════╣
║  • 扫描数据目录                                                            ║
║  • 提取Excel文件信息 (列名、行数、样本数据)                                  ║
║  • 提取CSV文件信息                                                         ║
║  • 复制数据文件到工作目录                                                   ║
╚═══════════════════════════════════════════════════════════════════════════╝
    │
    ▼
╔═══════════════════════════════════════════════════════════════════════════╗
║  Phase 3: 内容分析 (AnalyzerAgent)                                         ║
╠═══════════════════════════════════════════════════════════════════════════╣
║  • 确定数据来源类型                                                        ║
║  • 分析论文类型和研究方法                                                   ║
║  • 生成代码任务列表                                                        ║
║  • 确定技术栈和依赖库                                                       ║
║  → 输出: AnalysisResult                                                    ║
╚═══════════════════════════════════════════════════════════════════════════╝
    │
    ▼
╔═══════════════════════════════════════════════════════════════════════════╗
║  Phase 4: 代码生成 (CoderAgent)                                            ║
╠═══════════════════════════════════════════════════════════════════════════╣
║  • 构建项目上下文                                                          ║
║  • 按优先级排序任务                                                        ║
║  • 逐个生成代码文件 (独立LLM调用)                                           ║
║  • 生成主程序 main.py                                                      ║
║  → 输出: List[GeneratedCode]                                               ║
╚═══════════════════════════════════════════════════════════════════════════╝
    │
    ▼
╔═══════════════════════════════════════════════════════════════════════════╗
║  Phase 5: 代码验证 (ValidatorAgent)                                        ║
╠═══════════════════════════════════════════════════════════════════════════╣
║  • 语法检查 (ast.parse)                                                    ║
║  • 导入检查                                                                ║
║  • 静态代码分析                                                            ║
║  • 自动修复错误 (最多5次重试)                                               ║
║  → 输出: List[ValidationResult]                                            ║
╚═══════════════════════════════════════════════════════════════════════════╝
    │
    ▼
╔═══════════════════════════════════════════════════════════════════════════╗
║  Phase 6: 生成项目                                                         ║
╠═══════════════════════════════════════════════════════════════════════════╣
║  • 应用修复后的代码                                                        ║
║  • 收集所有依赖                                                            ║
║  • 生成 requirements.txt                                                   ║
║  • 生成 README.md                                                          ║
║  • 生成运行说明                                                            ║
║  • 保存所有文件到工作目录                                                   ║
╚═══════════════════════════════════════════════════════════════════════════╝
    │
    ▼
输出项目
    │
    ├── main.py                 # 主程序入口
    ├── data_preprocessing.py   # 数据预处理
    ├── data_analysis.py        # 数据分析
    ├── visualization.py        # 可视化
    ├── model_training.py       # 模型训练(如有)
    ├── requirements.txt        # 依赖列表
    ├── README.md               # 项目说明
    ├── analysis_result.json    # 分析结果
    └── thesis.md               # 论文Markdown
```

### 4.2 数据流转图

```
                    ┌─────────────┐
                    │  论文文件   │
                    └──────┬──────┘
                           │
                           ▼
                    ┌─────────────┐
                    │ParsedContent│ ─── 标题、摘要、章节、表格
                    └──────┬──────┘
                           │
            ┌──────────────┼──────────────┐
            │              │              │
            ▼              ▼              ▼
     ┌───────────┐  ┌───────────┐  ┌───────────┐
     │ ThesisType│  │ CodeTask  │  │ tech_stack│
     └───────────┘  └───────────┘  └───────────┘
            │              │              │
            └──────────────┼──────────────┘
                           │
                           ▼
                   ┌──────────────┐
                   │AnalysisResult│
                   └──────┬───────┘
                          │
                          ▼
                  ┌───────────────┐
                  │ GeneratedCode │ ─── 代码文件、依赖
                  └───────┬───────┘
                          │
                          ▼
                 ┌────────────────┐
                 │ValidationResult│ ─── 验证结果、修复代码
                 └────────┬───────┘
                          │
                          ▼
                  ┌──────────────┐
                  │ ProjectOutput│ ─── 完整项目
                  └──────────────┘
```

---

## 5. 数据模型

### 5.1 模型定义文件

**文件位置**: `app/schemas/models.py`

所有数据模型使用Pydantic定义，确保类型安全和数据验证。

### 5.2 枚举类型

#### DataSourceType - 数据来源类型

```python
class DataSourceType(str, Enum):
    PDF_EMBEDDED = "pdf_embedded"   # PDF内嵌数据
    EXCEL_FILE = "excel_file"       # Excel文件
    CSV_FILE = "csv_file"           # CSV文件
    NO_DATA = "no_data"             # 无数据需求
```

#### ThesisType - 论文类型

```python
class ThesisType(str, Enum):
    EMPIRICAL = "empirical"              # 实证研究
    SIMULATION = "simulation"            # 仿真研究
    ALGORITHM = "algorithm"              # 算法设计
    SYSTEM_DESIGN = "system_design"      # 系统设计
    DATA_ANALYSIS = "data_analysis"      # 数据分析
    MACHINE_LEARNING = "machine_learning" # 机器学习
    OTHER = "other"                      # 其他
```

#### CodeTaskType - 代码任务类型

```python
class CodeTaskType(str, Enum):
    DATA_PREPROCESSING = "data_preprocessing"  # 数据预处理
    DATA_ANALYSIS = "data_analysis"            # 数据分析
    MODEL_TRAINING = "model_training"          # 模型训练
    VISUALIZATION = "visualization"            # 可视化
    ALGORITHM_IMPL = "algorithm_impl"          # 算法实现
    STATISTICAL_TEST = "statistical_test"      # 统计检验
    SIMULATION = "simulation"                  # 仿真模拟
    UTILITY = "utility"                        # 工具函数
```

### 5.3 核心数据模型

#### ParsedContent - 解析后的论文内容

```python
class ParsedContent(BaseModel):
    title: str = ""                              # 论文标题
    abstract: str = ""                           # 摘要
    keywords: List[str] = []                     # 关键词
    chapters: Dict[str, str] = {}                # 章节名: 内容
    tables: List[Dict[str, Any]] = []            # 表格数据
    figures: List[str] = []                      # 图片描述
    references: List[str] = []                   # 参考文献
    raw_markdown: str = ""                       # 原始markdown
    embedded_data: Optional[List[Dict]] = None   # PDF内嵌数据
```

#### CodeTask - 代码任务

```python
class CodeTask(BaseModel):
    task_id: str                           # 任务ID
    task_type: CodeTaskType                # 任务类型
    title: str                             # 任务标题
    description: str                       # 任务描述
    requirements: List[str] = []           # 具体要求
    dependencies: List[str] = []           # 依赖的其他任务ID
    input_data: Optional[str] = None       # 输入数据描述
    expected_output: Optional[str] = None  # 期望输出描述
    priority: int = 0                      # 优先级(越小越高)
```

#### AnalysisResult - 分析结果

```python
class AnalysisResult(BaseModel):
    thesis_type: ThesisType                # 论文类型
    research_method: str                   # 研究方法描述
    data_source: DataSourceType            # 数据来源
    data_files: List[DataFileInfo] = []    # 数据文件信息
    code_tasks: List[CodeTask] = []        # 代码任务列表
    tech_stack: List[str] = []             # 推荐技术栈
    libraries: List[str] = []              # 需要的Python库
    summary: str = ""                      # 分析总结
```

#### GeneratedCode - 生成的代码

```python
class GeneratedCode(BaseModel):
    task_id: str                    # 任务ID
    file_name: str                  # 文件名
    code: str                       # 代码内容
    description: str                # 功能描述
    dependencies: List[str] = []    # 依赖库
```

#### ValidationResult - 验证结果

```python
class ValidationResult(BaseModel):
    task_id: str                         # 任务ID
    is_valid: bool                       # 是否有效
    syntax_check: bool = True            # 语法检查结果
    import_check: bool = True            # 导入检查结果
    execution_check: bool = False        # 执行测试结果
    error_message: Optional[str] = None  # 错误信息
    suggestions: List[str] = []          # 改进建议
    fixed_code: Optional[str] = None     # 修复后的代码
```

#### ProjectOutput - 项目输出

```python
class ProjectOutput(BaseModel):
    project_name: str                    # 项目名称
    thesis_title: str                    # 论文标题
    files: Dict[str, str] = {}           # 文件名: 代码内容
    requirements: List[str] = []         # 依赖列表
    readme: str = ""                     # README内容
    run_instructions: str = ""           # 运行说明
```

---

## 6. 配置说明

### 6.1 配置文件

**文件位置**: `app/config/settings.py`

使用Pydantic Settings管理配置，支持环境变量和.env文件。

### 6.2 配置项详解

#### Mineru API配置

```env
MINERU_API_TOKEN=your-mineru-token
MINERU_API_URL=https://mineru.net/api/v4/extract/task
```

#### 分析LLM配置

```env
ANALYZER_LLM_API_KEY=your-api-key
ANALYZER_LLM_MODEL=gpt-4o
ANALYZER_LLM_BASE_URL=https://api.openai.com/v1
```

#### 代码LLM配置

```env
CODER_LLM_API_KEY=your-api-key
CODER_LLM_MODEL=gpt-4o
CODER_LLM_BASE_URL=https://api.openai.com/v1
```

#### 兼容配置（单一LLM）

```env
LLM_API_KEY=your-api-key
LLM_MODEL=gpt-4o
LLM_BASE_URL=https://api.openai.com/v1
```

#### 执行配置

```env
MAX_CODE_RETRIES=5      # 代码最大重试次数
MAX_CHAT_TURNS=30       # 最大对话轮次
CODE_TIMEOUT=300        # 代码执行超时(秒)
```

#### 路径配置

```env
UPLOAD_DIR=uploads      # 上传目录
OUTPUT_DIR=output       # 输出目录
LOG_LEVEL=INFO          # 日志级别
```

### 6.3 配置优先级

1. 命令行参数
2. 环境变量
3. .env文件
4. 默认值

---

## 7. 使用方式

### 7.1 命令行使用

#### 基本用法

```bash
# 使用Markdown文件
python main.py --md thesis.md

# 使用Markdown和数据文件
python main.py --md thesis.md --data ./data

# 指定输出目录
python main.py --md thesis.md --output ./my_output
```

#### 完整参数

```bash
python main.py \
    --md thesis.md \           # 论文文件路径（必需）
    --data ./data \            # 数据文件目录（可选）
    --output ./output \        # 输出目录（默认: output）
    --api-key your-key \       # API Key（可选）
    --model gpt-4o \           # 模型名称（可选）
    --base-url https://...     # API Base URL（可选）
```

### 7.2 Web界面使用

#### 启动服务

```bash
python app.py
```

服务启动后访问: `http://localhost:7860`

#### 界面功能

1. **上传论文文件** - 支持.md/.pdf/.txt格式
2. **上传数据文件** - 支持多个Excel/CSV文件
3. **配置API** - 填写API Key和模型设置
4. **开始生成** - 点击按钮启动处理
5. **下载结果** - 下载生成的代码包

### 7.3 作为Python模块使用

```python
import asyncio
from app.core.workflow import ThesisToCodeWorkflow
from app.core.llm import LLM

async def main():
    # 创建LLM实例
    analyzer_llm = LLM(
        api_key="your-api-key",
        model="gpt-4o"
    )
    coder_llm = LLM(
        api_key="your-api-key",
        model="gpt-4o"
    )
    
    # 创建工作流
    workflow = ThesisToCodeWorkflow(
        analyzer_llm=analyzer_llm,
        coder_llm=coder_llm
    )
    
    # 执行
    result = await workflow.run(
        md_path="thesis.md",
        data_dir="./data",
        output_dir="./output"
    )
    
    print(f"生成文件: {list(result.files.keys())}")

asyncio.run(main())
```

---

## 8. 技术栈

### 8.1 核心依赖

| 库 | 版本 | 用途 |
|----|------|------|
| pydantic | >=2.0.0 | 数据模型验证 |
| pydantic-settings | >=2.0.0 | 配置管理 |
| openai | >=1.0.0 | LLM API调用 |
| aiohttp | >=3.8.0 | 异步HTTP请求 |
| gradio | >=4.0.0 | Web界面 |

### 8.2 数据处理

| 库 | 版本 | 用途 |
|----|------|------|
| pandas | >=2.0.0 | 数据处理 |
| openpyxl | >=3.0.0 | Excel读取 |
| xlrd | >=2.0.0 | 旧版Excel支持 |

### 8.3 PDF解析

| 库 | 版本 | 用途 |
|----|------|------|
| PyMuPDF | >=1.23.0 | 本地PDF解析（备用） |

### 8.4 日志

| 库 | 版本 | 用途 |
|----|------|------|
| icecream | >=2.1.0 | 调试输出 |

---

## 9. 扩展与定制

### 9.1 添加新的Agent

1. 继承`BaseAgent`基类
2. 实现`system_prompt`属性
3. 实现`run`方法
4. 在工作流中集成

```python
from app.core.base_agent import BaseAgent

class CustomAgent(BaseAgent):
    @property
    def system_prompt(self) -> str:
        return "你是一个自定义Agent..."
    
    async def run(self, input_data) -> OutputType:
        # 实现逻辑
        response = await self.call_llm(prompt)
        return result
```

### 9.2 添加新的论文类型

1. 在`ThesisType`枚举中添加新类型
2. 在`AnalyzerAgent._analyze_thesis_type`中添加映射
3. 根据需要调整代码生成逻辑

### 9.3 添加新的代码任务类型

1. 在`CodeTaskType`枚举中添加新类型
2. 在`AnalyzerAgent._parse_task_type`中添加映射
3. 在`CoderAgent`中添加对应的生成逻辑

### 9.4 自定义验证规则

在`ValidatorAgent`中添加新的验证方法：

```python
def _custom_check(self, code: str) -> Tuple[bool, Optional[str]]:
    # 自定义检查逻辑
    return True, None
```

### 9.5 集成其他LLM

修改`LLM`类或创建新的LLM封装类，只需实现相同的接口：

```python
class CustomLLM:
    async def chat(self, messages, tools=None, ...) -> Any:
        # 调用自定义LLM API
        pass
    
    async def simple_chat(self, prompt, system_prompt=None) -> str:
        # 简单对话
        pass
```

---

## 附录

### A. 输出示例

生成的项目结构示例：

```
output/20241217_143052_abc123/
├── main.py                    # 主程序入口
├── data_preprocessing.py      # 数据预处理模块
├── data_analysis.py           # 数据分析模块
├── visualization.py           # 可视化模块
├── model_training.py          # 模型训练模块
├── requirements.txt           # 依赖列表
├── README.md                  # 项目说明
├── RUN_INSTRUCTIONS.md        # 运行说明
├── analysis_result.json       # 分析结果
└── thesis.md                  # 原始论文
```

### B. 常见问题

**Q: 支持哪些LLM？**
A: 支持所有OpenAI兼容的API，包括OpenAI、Azure OpenAI、本地部署的模型等。

**Q: PDF解析失败怎么办？**
A: 系统会自动尝试使用PyMuPDF本地解析作为备用方案。也可以先使用Mineru网站手动转换PDF为Markdown。

**Q: 生成的代码需要修改吗？**
A: AI生成的代码可能需要根据实际情况进行调整，特别是数据文件路径和特定业务逻辑。

**Q: 如何提高代码质量？**
A: 使用更强大的代码LLM模型（如GPT-4o），并确保论文描述清晰详细。

### C. 版本历史

- **v1.0.0** - 初始版本，支持基本的论文代码生成功能

---

*文档生成时间: 2024年12月*
*项目地址: lunwentocode*
