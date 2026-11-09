"""
本地代码解释器 - 基于 Jupyter 内核执行代码，保留变量状态

参考 MathModelAgent 的 LocalCodeInterpreter：
- execute_code 返回 (喂给LLM的文本, 是否出错, 错误信息)
- 分节(section)记录每个任务的代码输出，供写作手引用
- 通过工作目录图片集合 diff 追踪每个任务新生成的图片
"""
import os
import re
from typing import Optional, Tuple

import jupyter_client

from app.core.events import EVENT_CODE_OUTPUT, EventBus
from app.tools.matplotlib_setup import build_matplotlib_init_code
from app.tools.notebook_serializer import NotebookSerializer
from app.utils.logger import logger


class LocalCodeInterpreter:
    """基于本地 Jupyter 内核的代码解释器"""

    def __init__(
        self,
        work_dir: str,
        notebook_serializer: NotebookSerializer,
        event_bus: Optional[EventBus] = None,
    ):
        self.work_dir = work_dir
        self.notebook_serializer = notebook_serializer
        self.event_bus = event_bus
        self.km = None
        self.kc = None
        # 分节输出: {section: [文本输出...]}
        self.section_output: dict[str, list[str]] = {}
        # 当前正在执行的 section
        self.current_section: Optional[str] = None
        # 图片 diff 基线
        self.last_created_images: set = set()

    # ------------------------------------------------------------------ 生命周期

    async def initialize(self) -> None:
        """启动 Jupyter 内核并注入 matplotlib 环境"""
        logger.info("初始化本地 Jupyter 内核")
        # UTF-8 编码环境，避免 Windows 中文环境下 GBK 编码导致的乱码
        kernel_env = os.environ.copy()
        kernel_env["PYTHONIOENCODING"] = "utf-8"
        kernel_env["PYTHONUTF8"] = "1"
        self.km, self.kc = jupyter_client.manager.start_new_kernel(
            kernel_name="python3", env=kernel_env
        )
        init_code = build_matplotlib_init_code(self.work_dir)
        outputs = self.execute_code_(init_code)
        for mark, text in outputs:
            if mark == "stdout":
                logger.info(text.strip())

    async def cleanup(self) -> None:
        """关闭内核"""
        if self.kc is not None:
            try:
                self.kc.shutdown()
            except Exception as e:
                logger.warning(f"关闭 kernel client 失败: {e}")
        if self.km is not None:
            try:
                self.km.shutdown_kernel()
            except Exception as e:
                logger.warning(f"关闭 kernel 失败: {e}")
        logger.info("Jupyter 内核已关闭")

    # ------------------------------------------------------------------ 分节管理

    def add_section(self, section_name: str) -> None:
        """开始新的任务分节：notebook 写入标题、重置输出记录和图片基线"""
        self.current_section = section_name
        if section_name not in self.section_output:
            self.section_output[section_name] = []
        # 以当前图片集合为基线，后续 diff 出本节新增图片
        self.last_created_images = self._scan_images()
        self.notebook_serializer.add_markdown_cell(f"## {section_name}")

    def get_code_output(self, section: str) -> str:
        """获取指定 section 的代码文本输出（供写作手引用）"""
        return "\n".join(self.section_output.get(section, []))

    def _scan_images(self) -> set:
        """扫描工作目录中的图片文件"""
        if not os.path.exists(self.work_dir):
            return set()
        return {
            f for f in os.listdir(self.work_dir)
            if f.lower().endswith((".png", ".jpg", ".jpeg"))
        }

    async def get_created_images(self, section: str) -> list[str]:
        """获取自上次调用以来新增的图片（即本 section 生成的图片）"""
        current_images = self._scan_images()
        new_images = current_images - self.last_created_images
        self.last_created_images = current_images
        new_list = sorted(new_images)
        if new_list:
            logger.info(f"本节新增图片: {new_list}")
        return new_list

    # ------------------------------------------------------------------ 代码执行

    async def execute_code(self, code: str) -> Tuple[str, bool, str]:
        """执行一段代码

        Returns:
            (喂给 LLM 的文本输出, 是否出错, 错误信息)
        """
        self.notebook_serializer.add_code_cell(code)

        if self.event_bus:
            self.event_bus.publish(EVENT_CODE_OUTPUT, f"执行代码:\n{code}")

        execution = self.execute_code_(code)

        text_to_gpt: list[str] = []
        error_occurred = False
        error_message = ""

        for mark, out_str in execution:
            if mark in ("stdout", "execute_result_text", "display_text"):
                truncated = self._truncate_text(f"[{mark}]\n{out_str}")
                text_to_gpt.append(truncated)
                self.notebook_serializer.add_output_to_last_cell(out_str)
                if self.current_section:
                    self.section_output[self.current_section].append(
                        self._truncate_text(out_str, max_length=2000)
                    )

            elif mark in ("execute_result_png", "execute_result_jpeg",
                          "display_png", "display_jpeg"):
                text_to_gpt.append(f"[{mark} 图片已生成，内容为 base64，未展示]")
                mime = "image/png" if "png" in mark else "image/jpeg"
                self.notebook_serializer.add_image_to_last_cell(out_str, mime)

            elif mark == "error":
                error_occurred = True
                error_message = self._delete_color_control_char(out_str)
                error_message = self._truncate_text(error_message)
                text_to_gpt.append(error_message)
                self.notebook_serializer.add_error_to_last_cell(out_str)

        combined_text = "\n".join(text_to_gpt)

        if self.event_bus:
            if error_occurred:
                self.event_bus.publish(EVENT_CODE_OUTPUT, f"执行出错:\n{error_message}")
            else:
                summary = combined_text if len(combined_text) < 500 else combined_text[:500] + "..."
                self.event_bus.publish(EVENT_CODE_OUTPUT, f"执行成功:\n{summary}")

        return combined_text, error_occurred, error_message

    def execute_code_(self, code: str) -> list[tuple[str, str]]:
        """在 Jupyter 内核中同步执行代码并收集输出"""
        assert self.kc is not None, "Jupyter 内核未初始化"
        self.kc.execute(code)

        msg_list = []
        while True:
            try:
                iopub_msg = self.kc.get_iopub_msg(timeout=1)
                msg_list.append(iopub_msg)
                if (
                    iopub_msg["msg_type"] == "status"
                    and iopub_msg["content"].get("execution_state") == "idle"
                ):
                    break
            except Exception:
                continue

        all_output: list[tuple[str, str]] = []
        for iopub_msg in msg_list:
            msg_type = iopub_msg["msg_type"]
            content = iopub_msg["content"]

            if msg_type == "stream":
                if content.get("name") == "stdout":
                    all_output.append(("stdout", content["text"]))

            elif msg_type in ("execute_result", "display_data"):
                if "data" in content:
                    data = content["data"]
                    if "text/plain" in data:
                        all_output.append((f"{msg_type}_text", data["text/plain"]))
                    if "image/png" in data:
                        all_output.append((f"{msg_type}_png", data["image/png"]))
                    if "image/jpeg" in data:
                        all_output.append((f"{msg_type}_jpeg", data["image/jpeg"]))

            elif msg_type == "error":
                if "traceback" in content:
                    output = "\n".join(content["traceback"])
                    all_output.append(("error", self._delete_color_control_char(output)))

        return all_output

    # ------------------------------------------------------------------ 工具方法

    @staticmethod
    def _delete_color_control_char(string: str) -> str:
        ansi_escape = re.compile(r"(\x9B|\x1B\[)[0-?]*[ -\/]*[@-~]")
        return ansi_escape.sub("", string)

    @staticmethod
    def _truncate_text(text: str, max_length: int = 1000) -> str:
        """截断文本，保留开头和结尾的重要信息"""
        if len(text) <= max_length:
            return text
        half_length = max_length // 2
        return text[:half_length] + "\n... (内容已截断) ...\n" + text[-half_length:]
