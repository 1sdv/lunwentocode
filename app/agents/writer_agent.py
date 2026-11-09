"""
写作手 Agent - 基于代码真实执行结果撰写论文正文章节

- 每个章节一次独立调用，章节提示词由 Workflow 用模板组装
- 以论文第一作者口吻写作（"本文提出…"），产出学术论文初稿
- 收到图片列表时强制插入 Markdown 图片标签，且每图至少 3 行解读
- 所有数值必须来自代码输出，禁止编造
"""
from typing import List, Optional

from app.core.base_agent import BaseAgent
from app.core.events import EVENT_REPORT, EventBus
from app.core.llm import LLM


class WriterAgent(BaseAgent):
    """写作手 Agent - 无状态设计，每章节独立撰写"""

    def __init__(self, llm: LLM, event_bus: Optional[EventBus] = None):
        super().__init__(llm)
        self.event_bus = event_bus

    @property
    def system_prompt(self) -> str:
        return """你是学术论文写作专家，为研究生撰写论文初稿正文。
你基于研究方案素材与代码真实执行结果写作，产出期刊/学位论文级别的章节正文。

# 写作定位
1. 以论文第一作者口吻写作："本文提出/本文设计/实验结果表明…"，禁止出现"复现""本任务""代码手"等字样
2. 模型与方法部分基于方案原文素材润色扩写，保持符号与公式一致；不得凭空增加原文没有的技术内容
3. 实验部分所有数值必须来自提供的代码输出或实验总结，禁止编造任何数值
4. 不编造参考文献、不虚构相关工作的作者与年份，相关工作只用一般性表述

# 写作风格规范
1. 段落式写作：正文禁止出现分点列表（bullet points），必须转换为流畅的论文级段落
2. 每句不超过 30 词左右，避免口语化表达
3. 章节之间自然衔接，符合论文行文逻辑（模型→方法→实验→结论）

# 图片插入规范（强制）
1. 提供的可用图片列表中的每张图片都必须在正文中插入
2. 插入格式：![图片描述](文件名.png)，标签独占一行，放在相关段落之后
3. 使用图片的原始文件名，不要修改文件名
4. 每张图片后必须配至少 3 行文字解读：趋势、原因、与结论的关系
5. 图表解读必须基于代码输出的数据特征，禁止猜测图片内容

# 公式与格式
- 行内公式 $...$，块级公式 $$...$$，符号与方案原文一致
- 表格使用 Markdown 语法
- 直接输出 Markdown 内容，不要用代码块包裹整个输出

# 执行约束
1. 自主完成写作，不询问过程性问题
2. 严格按提供的章节模板结构撰写
3. 保持中文写作"""

    async def run(
        self,
        prompt: str,
        available_images: Optional[List[str]] = None,
    ) -> str:
        """撰写单个论文章节

        Args:
            prompt: Workflow 组装好的章节提示词（含模板与上下文）
            available_images: 本章节代码生成的图片文件名列表

        Returns:
            章节的 Markdown 内容
        """
        if available_images:
            image_lines = "\n".join(f"- ![{img}]({img})" for img in available_images)
            prompt += (
                f"\n\n【必须插入的图片列表】\n"
                f"以下图片是本章节实验生成的，你必须在论文正文相关段落后"
                f"用 Markdown 格式逐一插入：\n{image_lines}\n"
                f"插入格式为独占一行的 ![描述](文件名)，每张图片后需配 3 行以上的分析解读。\n"
            )

        if self.event_bus:
            self.event_bus.publish(EVENT_REPORT, f"写作手开始撰写章节（图片 {len(available_images or [])} 张）")

        response = await self.call_llm(prompt)
        content = response or ""

        if self.event_bus:
            self.event_bus.publish(EVENT_REPORT, f"写作手完成章节（{len(content)} 字）")

        return content
