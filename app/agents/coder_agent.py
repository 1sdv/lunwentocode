"""
代码手 Agent - 在 Jupyter 内核中生成并真实执行代码，完成论文复现任务

参考 MathModelAgent 的 CoderAgent：
- execute_code 工具循环：LLM 调用工具 → 内核执行 → 结果回填 → 继续或结束
- 出错 → 反思提示词 → 重试（max_retries）
- 对话历史跨任务累积，超过上下文窗口阈值时自动压缩
- 每个任务独立分节：notebook 写入标题、追踪新增图片
"""
import json
from typing import List, Optional

from app.core.events import EVENT_CODE, EventBus
from app.core.llm import LLM
from app.schemas.models import CodeTask, CoderExecutionResult, DataFileInfo
from app.tools.local_interpreter import LocalCodeInterpreter
from app.utils.logger import logger

# 每个字符估算的 token 数（中英混合文本的保守估计）
_CHARS_PER_TOKEN = 3
# 触发压缩的 token 占比阈值（相对 context_window）
_TOKEN_THRESHOLD_RATIO = 0.75

EXECUTE_CODE_TOOL = {
    "type": "function",
    "function": {
        "name": "execute_code",
        "description": "执行 Python 代码并返回终端输出。代码在持久 Jupyter 内核中执行，"
                       "变量在多次执行之间保留。图片输出不会直接返回，"
                       "请将图片用 plt.savefig('文件名.png', dpi=300) 保存到当前目录。",
        "parameters": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "要执行的 Python 代码"}
            },
            "required": ["code"],
        },
    },
}


class CoderAgent:
    """代码手 Agent - 有状态设计，管理对话历史与记忆压缩"""

    def __init__(
        self,
        llm: LLM,
        work_dir: str,
        code_interpreter: LocalCodeInterpreter,
        event_bus: Optional[EventBus] = None,
        max_chat_turns: int = 30,
        max_retries: int = 5,
        context_window: int = 128000,
    ):
        self.llm = llm
        self.work_dir = work_dir
        self.code_interpreter = code_interpreter
        self.event_bus = event_bus
        self.max_chat_turns = max_chat_turns
        self.max_retries = max_retries
        self.context_window = context_window

        self.chat_history: List[dict] = []
        self.current_token_count = 0
        self.is_first_run = True

    @property
    def system_prompt(self) -> str:
        return """你是论文复现代码专家，在 Jupyter 内核中编写并执行 Python 代码来复现论文中的方法与实验。

# 环境说明
- 内核启动时已注入：CJK_FONT、COLORS、DEFAULT_COLORS、FIG_SINGLE、FIG_DOUBLE、FIG_WIDE、FIG_SQUARE 以及 matplotlib 字体与样式配置
- 严格禁止调用 sns.set_theme() 或修改 font.sans-serif / axes.unicode_minus（会覆盖中文字体导致方框）
- 绑图时直接使用预置变量，例如 fig, ax = plt.subplots(figsize=FIG_SINGLE)
- 所有用户数据文件已在当前工作目录，直接用相对路径访问（如 pd.read_excel("data.xlsx")）
- Excel 用 pd.read_excel()，CSV 先尝试 utf-8 再 gbk

# 代码规范
1. 分步执行：每次 execute_code 只做一个步骤（读取数据/建模/绘图），便于定位错误
2. 向量化优先，避免低效循环
3. 关键参数必须有来源说明（数据统计/论文给定/网格搜索三选一），在注释或 print 中说明
4. 所有图片保存为 PNG（dpi=300），文件名含序号与含义（如 fig1_data_distribution.png）
5. 每张图保存后必须用 print() 输出该图的关键数据特征（趋势、最值、相关系数、指标值等），
   因为你无法看到图片，后续报告写作完全依赖这些文本输出
6. 每个任务完成后输出一段【本任务结果汇总】：核心方法、关键指标数值、生成的图片文件、核心结论

# 可视化规范（学术标准）
- 图表内不加标题（标题由报告 caption 提供）
- 使用统一 COLORS 配色；折线图必要时用 fill_between 添加置信带
- 标注关键统计量（r, p, R², MAE 等）；图例 frameon=False
- 禁止 3D 图、饼图；分布比较用箱线图/小提琴图；分类对比用水平条形图

# 执行原则
1. 自主完成任务，不询问用户
2. 出错时：分析原因 → 修复或换更简单的方案 → 重试，绝不陷入死循环；
   反复失败时果断简化模型或跳过该步骤并在汇总中说明
3. 代码执行成功且任务完成时，不再调用工具，直接输出本任务结果汇总"""

    # ------------------------------------------------------------------ 主流程

    async def run(
        self,
        task: CodeTask,
        context: str,
        data_files: Optional[List[DataFileInfo]] = None,
    ) -> CoderExecutionResult:
        """执行单个复现任务，返回执行结果供写作手使用"""
        section = f"任务{task.priority + 1}：{task.title}" if task.title else task.task_id
        self.code_interpreter.add_section(section)
        self._publish(EVENT_CODE, f"代码手开始执行: {section}")

        if self.is_first_run:
            self.is_first_run = False
            self._append_history({"role": "system", "content": self.system_prompt})
            data_info = self._format_data_files(data_files)
            self._append_history({
                "role": "user",
                "content": f"当前工作目录下的数据文件：\n{data_info}" if data_info
                else "当前没有用户提供的数据文件，需要根据论文描述模拟或构造示例数据。",
            })

        task_prompt = self._build_task_prompt(task, context)
        self._append_history({"role": "user", "content": task_prompt})

        retry_count = 0
        last_error_message = ""
        turn_count = 0  # 本任务的对话轮次（历史跨任务累积，轮次独立计算）

        while True:
            if retry_count >= self.max_retries:
                logger.error(f"超过最大重试次数: {self.max_retries}")
                self._publish(EVENT_CODE, f"任务失败（超过最大重试次数）: {section}")
                return CoderExecutionResult(
                    task_id=task.task_id,
                    section=section,
                    code_summary=f"任务执行失败，超过最大重试次数({self.max_retries})。最后错误：{last_error_message}",
                    code_output=self.code_interpreter.get_code_output(section),
                    created_images=await self.code_interpreter.get_created_images(section),
                    success=False,
                    error_message=last_error_message,
                )

            if turn_count >= self.max_chat_turns:
                logger.error(f"超过最大对话轮次: {self.max_chat_turns}")
                self._publish(EVENT_CODE, f"任务因轮次超限中止: {section}")
                return CoderExecutionResult(
                    task_id=task.task_id,
                    section=section,
                    code_summary=f"任务因超过最大对话轮次({self.max_chat_turns})而中止。",
                    code_output=self.code_interpreter.get_code_output(section),
                    created_images=await self.code_interpreter.get_created_images(section),
                    success=False,
                    error_message="超过最大对话轮次",
                )

            turn_count += 1

            try:
                response = await self.llm.chat(
                    messages=self.chat_history,
                    tools=[EXECUTE_CODE_TOOL],
                    tool_choice="auto",
                )
                message = response.choices[0].message

                tool_calls = getattr(message, "tool_calls", None)
                if tool_calls:
                    tool_call = tool_calls[0]
                    code = json.loads(tool_call.function.arguments)["code"]

                    self._publish(EVENT_CODE, f"执行代码:\n```\n{code[:500]}\n```")

                    # 回填 assistant 消息（含 tool_calls）
                    self._append_history({
                        "role": "assistant",
                        "content": message.content or "",
                        "tool_calls": [
                            {
                                "id": tc.id,
                                "type": "function",
                                "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                            }
                            for tc in tool_calls
                        ],
                    })

                    text_to_gpt, error_occurred, error_message = \
                        await self.code_interpreter.execute_code(code)

                    self._append_history({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": "execute_code",
                        "content": text_to_gpt,
                    })

                    if error_occurred:
                        retry_count += 1
                        last_error_message = error_message
                        logger.warning(f"代码执行错误 (重试 {retry_count}/{self.max_retries}): {error_message[:200]}")
                        self._publish(EVENT_CODE, f"代码执行出错，反思重试 ({retry_count}/{self.max_retries})")
                        self._append_history({
                            "role": "user",
                            "content": self._reflection_prompt(error_message, code),
                        })
                        continue
                    # 执行成功，继续循环等待 LLM 下一步动作
                    continue
                else:
                    # 没有工具调用，任务完成
                    summary = message.content or ""
                    images = await self.code_interpreter.get_created_images(section)
                    self._publish(EVENT_CODE, f"代码手完成: {section}（生成 {len(images)} 张图片）")
                    return CoderExecutionResult(
                        task_id=task.task_id,
                        section=section,
                        code_summary=summary,
                        code_output=self.code_interpreter.get_code_output(section),
                        created_images=images,
                        success=True,
                    )

            except Exception as e:
                retry_count += 1
                last_error_message = str(e)
                logger.error(f"CoderAgent 执行异常 (重试 {retry_count}/{self.max_retries}): {e}")
                self._publish(EVENT_CODE, f"执行异常: {e}")
                continue

    # ------------------------------------------------------------------ 提示词

    def _build_task_prompt(self, task: CodeTask, context: str) -> str:
        prompt = f"""请完成以下论文复现任务。

{context}

## 当前任务
- 标题: {task.title}
- 类型: {task.task_type.value}
- 任务描述: {task.description}
- 复现方案: {task.plan or '无，请根据任务描述自行设计'}
- 对应论文章节: {task.paper_section or '未指定'}
- 论文报告的结果（复现时用于对比）: {task.paper_results or '论文未给出具体数值'}
- 具体要求: {task.requirements}
- 输入数据: {task.input_data or '见数据文件'}
- 期望输出: {task.expected_output or '代码执行结果与图表'}

执行要求:
1. 严格按复现方案逐步实现，使用 execute_code 工具执行代码
2. 每张图保存后 print 关键数据特征
3. 任务完成后输出【本任务结果汇总】（不再调用工具）"""
        return prompt

    @staticmethod
    def _reflection_prompt(error_message: str, code: str) -> str:
        return f"""代码执行出错:
{error_message}

请分析错误原因并修复。考虑:
1. 语法错误、缺少 import、变量名/类型错误、文件路径问题
2. 若反复失败：拆小步骤、换更简单的实现、或直接跳过该步骤并在汇总中说明
3. 不要询问用户，自主完成

出错代码:
```
{code[:2000]}
```

修复后请继续调用 execute_code 工具。"""

    # ------------------------------------------------------------------ 历史管理

    def _append_history(self, msg: dict) -> None:
        self.chat_history.append(msg)
        self.current_token_count += self._estimate_message_tokens(msg)
        # 只在非 tool 消息时检查压缩，避免破坏工具调用序列
        if msg.get("role") != "tool":
            self._compress_if_needed()

    def _compress_if_needed(self) -> None:
        """token 超过上下文窗口阈值时，压缩历史（保留系统消息与最近消息）"""
        threshold = int(self.context_window * _TOKEN_THRESHOLD_RATIO)
        if self.current_token_count <= threshold:
            return

        logger.info(f"触发记忆压缩: 当前 ~{self.current_token_count} tokens, 阈值 {threshold}")
        # 保守策略：保留系统消息 + 最近 6 条消息，其余丢弃
        system_msgs = [m for m in self.chat_history if m.get("role") == "system"]
        recent = self.chat_history[-6:]
        self.chat_history = system_msgs + recent
        self.current_token_count = sum(
            self._estimate_message_tokens(m) for m in self.chat_history
        )
        logger.info(f"记忆压缩完成，保留 {len(self.chat_history)} 条消息")

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        return max(1, len(text) // _CHARS_PER_TOKEN)

    def _estimate_message_tokens(self, msg: dict) -> int:
        content = msg.get("content") or ""
        tokens = self._estimate_tokens(content) + 4
        for tc in msg.get("tool_calls") or []:
            tokens += self._estimate_tokens(tc.get("function", {}).get("arguments", ""))
        return tokens

    # ------------------------------------------------------------------ 工具方法

    @staticmethod
    def _format_data_files(data_files: Optional[List[DataFileInfo]]) -> str:
        if not data_files:
            return ""
        lines = []
        for df in data_files:
            line = f"- {df.file_name} ({df.file_type})"
            if df.columns:
                line += f", 列: {df.columns[:10]}"
            if df.row_count:
                line += f", 行数: {df.row_count}"
            lines.append(line)
        return "\n".join(lines)

    def _publish(self, event_type: str, content: str) -> None:
        if self.event_bus:
            self.event_bus.publish(event_type, content)
