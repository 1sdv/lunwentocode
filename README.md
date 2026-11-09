<div align="center">

# 🎓 LunwenToCode

### 研究方案 → 论文初稿 + 验证代码 · 多 Agent 学术写作系统

让 LLM 把 **研究方案 / 论文草稿** 一键转成 **论文初稿正文(paper.md)** 与 **真实执行验证的 Jupyter Notebook**。
实验数值全部来自代码真实运行结果，为论文提供可信的实验支撑。

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

> **不再"纸面生成代码"——所有代码都在真实 Jupyter 内核中执行验证，论文中的实验数值全部来自真实运行结果。**

- 📝 **论文初稿**：期刊/学位论文式结构（题目/摘要/引言/各章节/结论），以第一作者口吻撰写，模型章节基于方案素材润色，实验章节基于代码真实输出
- 🔁 **执行闭环**：代码手通过 `execute_code` 工具在持久 Jupyter 内核中编写并运行代码，出错自动反思重试（最多 5 次）
- 🧠 **多 Agent 协作**：解析 → 任务拆解 → 代码执行 → 论文写作，求解与写作交错进行
- 📓 **验证代码资产**：全过程代码实时序列化为 `notebook.ipynb`（含输出、图片、错误），可直接重跑
- 🖼️ **图片闭环**：工作目录图片 diff 追踪 → 论文强制插入 + 每图 3 行以上解读
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
python main.py --md proposal.md
python main.py --md proposal.pdf --data ./data --output ./output

# 4. 或启动 Web
python app.py
# 浏览器打开 http://localhost:7860，实时查看执行进度

# 5. 或启动公网版 Web 应用（FastAPI + 自研前端）
pip install -r requirements-web.txt && pip install ipykernel
python -m uvicorn server.main:app --host 127.0.0.1 --port 8000
# 浏览器打开 http://127.0.0.1:8000
```

> 💡 **PDF 准备小贴士**：可先用 [Mineru](https://mineru.net/) 把 PDF 转成 Markdown 再作为输入，解析质量更高。

---

## 🌐 公网部署

Web 版（`server/` + `web/`）可部署到云服务器供多人使用。**一键脚本**：

```bash
# Docker（最省事）
sudo bash deploy/deploy.sh --docker --token 你的访问令牌

# systemd + Nginx + HTTPS（推荐用于正式环境）
sudo bash deploy/deploy.sh --domain thesis.example.com --token 你的访问令牌
```

完整步骤、API 说明、自检清单与常见问题见 **[`deploy/DEPLOY.md`](deploy/DEPLOY.md)**。

关键配置（`.env`）：

| 变量 | 说明 |
|------|------|
| `SITE_TOKEN` | 访问令牌，用户需在页面填写才可提交任务。**公网部署必设** |
| `MAX_CONCURRENT_TASKS` | 同时运行的任务数（每任务 = 1 个 Jupyter 内核 + 1 线程） |
| `MAX_UPLOAD_MB` | 单文件上传上限，需与 Nginx `client_max_body_size` 匹配 |
| `RATE_LIMIT_PER_MINUTE` | 每 IP 每分钟最大提交数，防刷 |
| `TASK_TTL_HOURS` | 产出保留时长，超时自动清理 |

> ⚠️ Jupyter 内核执行的是 LLM 生成的代码，本质是任意代码执行。请用低权限用户运行、设置 `SITE_TOKEN`、限制内存，并确保 `--workers 1`（任务管理器为进程内状态）。

---

## 1. 项目概述

**LunwenToCode** 是基于大语言模型（LLM）的论文初稿生成系统：输入研究方案/论文草稿（+可选数据），输出

| 产出 | 说明 |
|------|------|
| `paper.md` | 论文初稿正文：题目/摘要/关键词、引言、各章节（模型叙述+实验数值+图表）、结论 |
| `notebook.ipynb` | 全部验证代码，按任务分节，含执行输出 / 图片 / 错误，可直接重跑 |
| `*.png` | 论文图表（300dpi 学术规范） |
| `analysis_result.json` | 方案分析与任务拆解结果 |
| `requirements.txt` / `README.md` | 依赖与说明 |

## 2. 架构

### 2.1 整体流程

```text
研究方案 (MD/PDF/TXT) + 数据 (Excel/CSV, 可选)
        │
        ▼
   ParserAgent ──► AnalyzerAgent ──► 拆解论文支撑任务（方案/对应章节/预期结论）
                                        │
                  ┌─────────────────────▼─────────────────────┐
                  │  for each task:                            │
                  │    CoderAgent ── Jupyter内核真实执行        │
                  │      └─ 出错→反思→重试（≤5次）              │
                  │    WriterAgent ── 以第一作者口吻撰写该章节  │
                  │      └─ 强制插入实验图片+解读                │
                  └───────────────────────────────────────────┘
                                        │
                                        ▼
                     包装章节（题目摘要/引言/结论）
                                        │
                                        ▼
                   paper.md + notebook.ipynb + 图表 + README
```

### 2.2 三 LLM 架构

| LLM | 用途 | 服务的 Agent |
|-----|------|--------------|
| **Analyzer LLM** | 方案解析、任务拆解 | `AnalyzerAgent`、`ParserAgent` |
| **Coder LLM** | 代码生成与执行修复 | `CoderAgent` |
| **Writer LLM** | 论文正文撰写（默认复用 Analyzer 配置） | `WriterAgent` |

均遵循 OpenAI 兼容协议。配置优先级：**CLI 参数 > 环境变量 > `.env` > 默认值**。

### 2.3 目录结构

```text
lunwentocode/
├── app/
│   ├── agents/     # Analyzer / Coder / Parser / Writer
│   ├── core/       # LLM / Workflow / 事件总线
│   ├── tools/      # Jupyter解释器 / notebook序列化 / matplotlib注入
│   ├── schemas/    # Pydantic 模型
│   ├── config/     # 配置 + 论文章节模板(toml)
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
| **论文模板** | `app/config/paper_template.toml` 定义各章节写作模板，可自由定制 |
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

- **定制论文章节**：编辑 `app/config/paper_template.toml`，占位符在 Workflow 中替换
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
