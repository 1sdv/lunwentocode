<div align="center">

# 🎓 LunwenToCode

### 论文 → 可复现代码 + 复现报告 · 多 Agent 自动复现系统

让 LLM 把 **科研论文 / 毕业论文** 一键转成 **真实执行验证的 Jupyter Notebook** 与 **图文复现报告**。

<p>
  <img src="https://img.shields.io/badge/Python-3.10%2B-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python"/>
  <img src="https://img.shields.io/badge/License-MIT-22C55E?style=for-the-badge&logo=opensourceinitiative&logoColor=white" alt="License"/>
  <img src="https://img.shields.io/badge/Agent-Multi--Agent-8B5CF6?style=for-the-badge&logo=robotframework&logoColor=white" alt="Multi-Agent"/>
  <img src="https://img.shields.io/badge/Execution-Jupyter%20Kernel-22C55E?style=for-the-badge&logo=jupyter&logoColor=white" alt="Jupyter"/>
  <img src="https://img.shields.io/badge/UI-Gradio-F97316?style=for-the-badge&logo=gradio&logoColor=white" alt="Gradio"/>
</p>

</div>

---

## ✨ 项目亮点

> **不再"纸面生成代码"——所有代码都在真实 Jupyter 内核中执行验证，报告数值全部来自真实运行结果。**

- 🔁 **执行闭环**：代码手通过 `execute_code` 工具在持久 Jupyter 内核中编写并运行代码，出错自动反思重试（最多 5 次）
- 🧠 **多 Agent 协作**：解析 → 分析拆解 → 代码执行 → 报告撰写，求解与写作交错进行
- 📝 **复现报告**：方法复现对照 / 逐任务结果（图 + 解读）/ 与论文结果对比 / 差异分析
- 📓 **可复现资产**：全过程代码实时序列化为 `notebook.ipynb`（含输出、图片、错误），可直接重跑
- 🖼️ **图片闭环**：工作目录图片 diff 追踪 → 报告强制插入 + 每图 3 行以上解读
- 📊 **绘图工程化**：内核启动注入中文字体、统一配色与学术图表规范
- 🤖 **三 LLM 解耦**：分析 / 代码 / 写作可分别配置最擅长的模型（写作默认复用分析模型）
- 🌐 **双入口**：CLI 命令行 + Gradio Web（实时进度流式推送）
- 📄 **多格式输入**：`.md` / `.pdf` / `.txt`，PDF 走 Mineru API → 上传 → 本地 PyMuPDF 三层降级

---

## 🚀 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env，填写各 LLM 的 API Key / Model / Base URL

# 3. 命令行
python main.py --md thesis.md
python main.py --md thesis.pdf --data ./data --output ./output

# 4. 或启动 Web
python app.py
# 浏览器打开 http://localhost:7860，实时查看执行进度
```

> 💡 **PDF 准备小贴士**：可先用 [Mineru](https://mineru.net/) 把 PDF 转成 Markdown 再作为输入，解析质量更高。

---

## 1. 项目概述

**LunwenToCode** 是基于大语言模型（LLM）的论文复现系统：输入论文（+可选数据），输出

| 产出 | 说明 |
|------|------|
| `notebook.ipynb` | 全部复现代码，按任务分节，含执行输出 / 图片 / 错误，可直接重跑 |
| `report.md` | 图文复现报告：方法对照、逐任务结果、与论文结果对比、差异分析 |
| `*.png` | 代码生成的全部图表 |
| `analysis_result.json` | 论文分析与任务拆解结果 |
| `requirements.txt` / `README.md` | 依赖与说明 |

## 2. 架构

### 2.1 整体流程

```text
论文 (MD/PDF/TXT) + 数据 (Excel/CSV, 可选)
        │
        ▼
   ParserAgent ──► AnalyzerAgent ──► 拆解复现任务（方案/对应章节/论文结果）
                                        │
                  ┌─────────────────────▼─────────────────────┐
                  │  for each task:                            │
                  │    CoderAgent ── Jupyter内核真实执行        │
                  │      └─ 出错→反思→重试（≤5次）              │
                  │    WriterAgent ── 撰写该任务报告章节        │
                  │      └─ 强制插入新增图片+解读                │
                  └───────────────────────────────────────────┘
                                        │
                                        ▼
              包装章节（摘要/概述/方法对照/结果对比/差异分析/结论）
                                        │
                                        ▼
                   notebook.ipynb + report.md + 图表 + README
```

### 2.2 三 LLM 架构

| LLM | 用途 | 服务的 Agent |
|-----|------|--------------|
| **Analyzer LLM** | 论文解析、任务拆解 | `AnalyzerAgent`、`ParserAgent` |
| **Coder LLM** | 代码生成与执行修复 | `CoderAgent` |
| **Writer LLM** | 复现报告撰写（默认复用 Analyzer 配置） | `WriterAgent` |

均遵循 OpenAI 兼容协议。配置优先级：**CLI 参数 > 环境变量 > `.env` > 默认值**。

### 2.3 目录结构

```text
lunwentocode/
├── app/
│   ├── agents/     # Analyzer / Coder / Parser / Writer
│   ├── core/       # LLM / Workflow / 事件总线
│   ├── tools/      # Jupyter解释器 / notebook序列化 / matplotlib注入
│   ├── schemas/    # Pydantic 模型
│   ├── config/     # 配置 + 报告章节模板(toml)
│   └── utils/      # 文件 / JSON / 日志
├── main.py         # CLI 入口
├── app.py          # Web 入口 (Gradio, 实时进度)
└── requirements.txt
```

## 3. 核心机制

| 机制 | 说明 |
|------|------|
| **执行闭环** | Coder 通过 Function Calling 调用 `execute_code`，代码在持久 Jupyter 内核执行、变量跨轮保留；报错→反思提示→重试，超限如实记录失败 |
| **上下文压缩** | Coder 对话历史累积，估算 token 超过上下文窗口 75% 时自动压缩（保留系统提示与最近消息） |
| **图片闭环** | 解释器对工作目录做图片集合 diff 得到每任务新增图片；Writer 收到图片列表后强制 `![](文件名)` 插入并逐图解读 |
| **绘图预注入** | 内核启动时注册中文字体、注入 `COLORS`/`FIG_*` 常量与 rcParams（300dpi、去上右边框），代码禁止重复设置 |
| **报告模板** | `app/config/report_template.toml` 定义各章节写作模板，可自由定制 |
| **进度推送** | 事件总线（`app/core/events.py`）发布 system/code/report 事件，CLI 走日志、Gradio 流式展示，可扩展 Redis/WebSocket |

## 4. 配置

复制 `.env.example` 为 `.env` 后填写：

```env
# Mineru API（PDF 解析，可选）
MINERU_API_TOKEN=your-mineru-token

# 分析 LLM
ANALYZER_LLM_API_KEY=your-api-key
ANALYZER_LLM_MODEL=gpt-4o
ANALYZER_LLM_BASE_URL=https://api.openai.com/v1

# 代码 LLM
CODER_LLM_API_KEY=your-api-key
CODER_LLM_MODEL=gpt-4o
CODER_LLM_BASE_URL=https://api.openai.com/v1

# 写作 LLM（留空复用分析 LLM）
WRITER_LLM_API_KEY=
WRITER_LLM_MODEL=

# 执行配置
MAX_CODE_RETRIES=5       # 代码错误最大反思重试次数
MAX_CHAT_TURNS=30        # 每任务最大对话轮次
CODER_CONTEXT_WINDOW=128000
```

只设一组时也可：`LLM_API_KEY` / `LLM_MODEL` / `LLM_BASE_URL`（两边共用）。

## 5. 扩展与定制

- **定制报告章节**：编辑 `app/config/report_template.toml`，占位符在 Workflow 中替换
- **新增 Agent**：继承 `BaseAgent`，实现 `system_prompt` 与 `run`，注册到 Workflow
- **切换执行环境**：`LocalCodeInterpreter` 可替换为云端沙箱（如 E2B），实现相同接口即可
- **接入实时推送**：订阅 `EventBus`，转发到 Redis/WebSocket 即可实现多端进度展示

---

<div align="center">

### 🤝 贡献

欢迎提交 Issue 和 Pull Request！

### 📄 许可证

MIT License · © LunwenToCode Contributors

</div>
