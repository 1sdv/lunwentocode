<div align="center">

# 🎓 LunwenToCode

### 论文 → 可运行 Python 代码 · 多 Agent 自动生成系统

让 LLM 替你把 **科研论文 / 毕业论文** 一键转成完整的 Python 工程。

<p>
  <img src="https://img.shields.io/badge/Python-3.8%2B-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python"/>
  <img src="https://img.shields.io/badge/License-MIT-22C55E?style=for-the-badge&logo=opensourceinitiative&logoColor=white" alt="License"/>
  <img src="https://img.shields.io/badge/Agent-Multi--Agent-8B5CF6?style=for-the-badge&logo=robotframework&logoColor=white" alt="Multi-Agent"/>
  <img src="https://img.shields.io/badge/LLM-Dual%20Model-F59E0B?style=for-the-badge&logo=openai&logoColor=white" alt="Dual LLM"/>
  <img src="https://img.shields.io/badge/UI-Gradio-F97316?style=for-the-badge&logo=gradio&logoColor=white" alt="Gradio"/>
</p>

</div>

---

## ✨ 项目亮点

> **把论文里的算法、模型、实验步骤翻译成一份能 `python main.py` 直接跑起来的项目。**

- 🧠 **多 Agent 协作**：解析 → 分析 → 生成 → 验证，四个 Agent 流水线分工
- 🤖 **双 LLM 架构**：分析模型与代码模型解耦，可分别选用最擅长模型
- 📄 **多格式输入**：支持 `.md` / `.pdf` / `.txt`，PDF 三层降级解析
- 💻 **结构化生成**：基于 OpenAI Function Calling 生成可直接运行的代码
- ✅ **自检自愈**：语法 + 导入 + 静态分析三段验证 + LLM 自动修复（最多 5 次）
- 📊 **数据友好**：自动识别 Excel / CSV，把 schema 注入生成上下文
- 🌐 **双入口**：CLI 命令行 + Gradio Web 界面
<img width="960" height="483" alt="幻灯片3" src="https://github.com/user-attachments/assets/75f15998-36a4-4309-bad2-2afd8c876b77" />

---

## 🚀 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env，填写两个 LLM 的 API Key / Model / Base URL

# 3. 命令行
python main.py --md thesis.md
python main.py --md thesis.pdf --data ./data --output ./output

# 4. 或启动 Web
python app.py
# 浏览器打开 http://localhost:7860
```

> 💡 **PDF 准备小贴士**：你可以先用 [Mineru](https://mineru.net/) 一键把 PDF 转成 Markdown 再作为输入。


## 1. 项目概述

**LunwenToCode** 是一个基于大语言模型（LLM）的智能代码生成系统，专门用于将科研论文或毕业论文自动转换为可运行的 Python 代码。

系统采用 **多 Agent 协作架构**：先分析论文内容、识别研究方法、提取代码需求，再生成完整的 Python 项目。

### 支持的论文类型

`empirical` 实证研究 · `simulation` 仿真研究 · `algorithm` 算法设计 · `system_design` 系统设计 · `data_analysis` 数据分析 · `machine_learning` 机器学习 · `other` 其他

### 核心功能

| 功能 | 描述 |
|------|------|
| 📄 文稿解析 | 支持 Markdown / PDF / TXT |
| 🔍 智能分析 | 自动识别论文类型、研究方法、代码需求 |
| 💻 代码生成 | 根据论文生成完整可运行代码 |
| ✅ 自动验证 | 语法 + 导入 + 静态分析 + LLM 自动修复 |
| 📊 数据支持 | 自动注入 Excel / CSV 数据 schema |
| 🌐 双入口 | CLI + Gradio Web |

---

## 2. 架构

### 2.1 整体流程

```text
论文 (MD / PDF / TXT) + 数据 (Excel / CSV, 可选)
        │
        ▼
┌──────────────────────────────────────────────────────┐
│  Parser ─► Analyzer ─► Coder ─► Validator            │
│  PDF转MD   提取需求    生成代码   验证修复            │
└──────────────────────────────────────────────────────┘
        │
        ▼
   Python 项目 (代码 + requirements + README)
```

### 2.2 双 LLM 架构

| LLM | 用途 | 服务的 Agent |
|-----|------|--------------|
| **Analyzer LLM** | 论文内容分析、结构提取 | `AnalyzerAgent`、`ParserAgent` |
| **Coder LLM** | 代码生成、代码修复 | `CoderAgent`、`ValidatorAgent` |

> 两套 LLM 都遵循 OpenAI 兼容协议，可接 OpenAI / Azure / 书生 / Qwen / Ollama 等。配置优先级：**CLI 参数 > 环境变量 > `.env` > 默认值**。

### 2.3 目录结构

```text
lunwentocode/
├── app/
│   ├── agents/      # Analyzer / Coder / Parser / Validator
│   ├── core/        # BaseAgent / LLM / Workflow
│   ├── schemas/     # Pydantic 模型
│   ├── config/      # 配置
│   └── utils/       # 文件 / JSON / 日志
├── main.py          # CLI 入口
├── app.py           # Web 入口 (Gradio)
└── requirements.txt
```

---

## 3. 核心组件

### 3.1 `ThesisToCodeWorkflow`（工作流引擎）

> `app/core/workflow.py`

整个系统的核心调度器，**六阶段流水线**：

| Phase | 名称 | 描述 |
|:-----:|------|------|
| 1 | 读取输入 | 加载论文，PDF 自动转 MD |
| 2 | 数据扫描 | 扫描 Excel / CSV 并注入上下文 |
| 3 | 内容分析 | `AnalyzerAgent` 分析论文 |
| 4 | 代码生成 | `CoderAgent` 逐任务生成代码 |
| 5 | 代码验证 | `ValidatorAgent` 验证并自动修复 |
| 6 | 生成项目 | 整合输出，生成 README / requirements |

### 3.2 `BaseAgent`（Agent 基类）

> `app/core/base_agent.py`

所有 Agent 的抽象基类，**无状态设计**——每次调用独立、不保留历史，避免长论文撑爆上下文。提供两种调用方式：

- `call_llm(prompt, context)`：纯文本
- `call_llm_with_tools(prompt, tools, context)`：Function Calling

### 3.3 四个 Agent 速览

| Agent | 职责 | 关键能力 |
|-------|------|----------|
| **ParserAgent** | PDF → Markdown | Mineru API → 上传 → 本地 PyMuPDF 三层降级 |
| **AnalyzerAgent** | 论文分析 | 数据来源、论文类型、代码任务、技术栈四步流水线 |
| **CoderAgent** | 代码生成 | OpenAI Function Calling `generate_code` 工具，按 `priority` 排序逐任务独立生成，最后生成 `main.py` |
| **ValidatorAgent** | 验证修复 | `ast.parse` 语法 → import 检查 → 静态分析（main/try/docstring），失败时调用 LLM 修复，最多 5 次 |

### 3.4 `LLM`（LLM 封装）

> `app/core/llm.py`

基于 OpenAI SDK，**兼容所有 OpenAI 兼容 API**：

- ⚡ 异步调用（`AsyncOpenAI`）
- ⏱️ 默认 5 分钟超时
- 🔁 最多 3 次重试，指数退避
- 🛠️ 支持 Function Calling

---

## 4. 处理流程

```text
Phase 1  读取输入      ─►  解析为 ParsedContent (title/abstract/chapters/tables)
Phase 2  数据扫描      ─►  DataFileInfo 列表 (列名/行数/样本)
Phase 3  AnalyzerAgent ─►  AnalysisResult (thesis_type/code_tasks/libraries)
Phase 4  CoderAgent    ─►  GeneratedCode[] (按 priority 生成 + main.py)
Phase 5  Validator     ─►  ValidationResult[] (含 fixed_code)
Phase 6  打包输出      ─►  main.py + 模块 + requirements.txt + README.md
```

**数据流转**：`ParsedContent` → `AnalysisResult` → `GeneratedCode[]` → `ValidationResult[]` → `ProjectOutput`

---

## 5. 使用方式

### 5.1 命令行（推荐）

```bash
python main.py --md thesis.md                              # 仅论文
python main.py --md thesis.pdf --data ./data --output ./output  # 论文+数据
python main.py --md thesis.md --api-key xxx --model gpt-4o   # 指定 LLM
```

完整参数：`--md` 论文路径 · `--data` 数据目录 · `--output` 输出目录 · `--api-key` / `--model` / `--base-url`

### 5.2 Web 界面

```bash
python app.py
```

访问 **<http://localhost:7860>**：上传论文 + 数据 → 配置 API → 点击生成 → 下载 zip。

### 5.3 Python 模块

```python
import asyncio
from app.core.workflow import ThesisToCodeWorkflow
from app.core.llm import LLM

async def main():
    analyzer = LLM(api_key="...", model="gpt-4o")
    coder    = LLM(api_key="...", model="gpt-4o")
    wf = ThesisToCodeWorkflow(analyzer_llm=analyzer, coder_llm=coder)
    result = await wf.run(md_path="thesis.md", data_dir="./data")
    print(list(result.files.keys()))

asyncio.run(main())
```

---

## 6. 配置

复制 `.env.example` 为 `.env` 后填写：

```env
# Mineru API（PDF 解析）
MINERU_API_TOKEN=your-mineru-token

# 分析 LLM（论文解析/分析）
ANALYZER_LLM_API_KEY=your-api-key
ANALYZER_LLM_MODEL=gpt-4o
ANALYZER_LLM_BASE_URL=https://api.openai.com/v1

# 代码 LLM（代码生成/修复）
CODER_LLM_API_KEY=your-api-key
CODER_LLM_MODEL=gpt-4o
CODER_LLM_BASE_URL=https://api.openai.com/v1

# 执行配置
MAX_CODE_RETRIES=5
CODE_TIMEOUT=300
```

只设一组时也可：`LLM_API_KEY` / `LLM_MODEL` / `LLM_BASE_URL`（两边共用）。

**配置优先级**：CLI 参数 > 环境变量 > `.env` > 默认值

---

## 7. 扩展与定制

- **新增 Agent**：继承 `BaseAgent`，实现 `system_prompt` 和 `run`，注册到 Workflow
- **新增论文类型**：在 `ThesisType` 枚举添加，并在 `AnalyzerAgent._analyze_thesis_type` 的 `type_mapping` 补映射
- **新增代码任务**：在 `CodeTaskType` 枚举添加，并在 `AnalyzerAgent._parse_task_type` 的 `type_mapping` 补映射
- **接入其他 LLM**：让新 LLM 类实现 `chat()` 和 `simple_chat()` 接口即可（详见 `app/core/llm.py`）

---

## 📦 输出示例
<img width="1536" height="749" alt="data" src="https://github.com/user-attachments/assets/f6c4d626-0229-4e24-a743-74c05c202d58" />
<img width="795" height="630" alt="image" src="https://github.com/user-attachments/assets/0d2431de-c033-4933-be73-f377c5a32153" />

---


<div align="center">

### 🤝 贡献

欢迎提交 Issue 和 Pull Request！

### 📄 许可证

MIT License · © LunwenToCode Contributors

</div>
