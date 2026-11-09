"""
Jupyter Notebook 序列化器 - 将执行过程中的代码/输出/图片实时写入 notebook.ipynb
"""
import os

import nbformat
from nbformat import v4 as nbf

from app.utils.logger import logger


class NotebookSerializer:
    """Jupyter Notebook 序列化器，负责创建和维护 .ipynb 文件"""

    def __init__(self, work_dir: str | None = None, notebook_name: str = "notebook.ipynb"):
        self.nb = nbf.new_notebook()
        self.notebook_path: str | None = None
        self.init_notebook(work_dir, notebook_name)

    def init_notebook(self, work_dir: str | None = None, notebook_name: str = "notebook.ipynb") -> None:
        if not work_dir:
            return
        base, ext = os.path.splitext(notebook_name)
        if ext.lower() != ".ipynb":
            notebook_name = base + ".ipynb"
        self.notebook_path = os.path.join(work_dir, notebook_name)

    def write_to_notebook(self) -> None:
        if self.notebook_path:
            with open(self.notebook_path, "w", encoding="utf-8") as f:
                f.write(nbformat.writes(self.nb))

    def add_markdown_cell(self, content: str) -> None:
        """添加 markdown 单元格（任务分节标题等）"""
        self.nb["cells"].append(nbf.new_markdown_cell(content))
        self.write_to_notebook()
        logger.debug(f"notebook 添加 markdown 单元格: {content[:50]}")

    def add_code_cell(self, code: str) -> None:
        """添加代码单元格"""
        self.nb["cells"].append(nbf.new_code_cell(source=code))
        self.write_to_notebook()

    def add_output_to_last_cell(self, output: str) -> None:
        """向最后一个代码单元格添加文本输出"""
        if not self.nb["cells"]:
            return
        cell = self.nb["cells"][-1]
        if cell["cell_type"] != "code":
            return
        cell["outputs"].append(
            nbf.new_output(output_type="stream", name="stdout", text=output)
        )
        self.write_to_notebook()

    def add_error_to_last_cell(self, error: str) -> None:
        """向最后一个代码单元格添加错误输出"""
        if not self.nb["cells"]:
            return
        cell = self.nb["cells"][-1]
        if cell["cell_type"] != "code":
            return
        cell["outputs"].append(
            nbf.new_output(
                output_type="error",
                ename="Error",
                evalue="Error message",
                traceback=[error],
            )
        )
        self.write_to_notebook()

    def add_image_to_last_cell(self, image_base64: str, mime_type: str = "image/png") -> None:
        """向最后一个代码单元格添加图片输出"""
        if not self.nb["cells"]:
            return
        cell = self.nb["cells"][-1]
        if cell["cell_type"] != "code":
            return
        cell["outputs"].append(
            nbf.new_output(output_type="display_data", data={mime_type: image_base64})
        )
        self.write_to_notebook()
