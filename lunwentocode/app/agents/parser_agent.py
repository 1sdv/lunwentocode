"""
PDF解析Agent - 使用Mineru API将PDF转换为Markdown
"""
import asyncio
import aiohttp
import time
import os
from typing import Optional, Dict, Any
from app.core.base_agent import BaseAgent
from app.core.llm import LLM
from app.schemas.models import ParsedContent
from app.config.settings import settings
from app.utils.logger import logger
from app.utils.json_utils import load_json_from_response


class ParserAgent(BaseAgent):
    """PDF解析Agent"""
    
    def __init__(self, llm: LLM):
        super().__init__(llm)
        self.mineru_token = settings.MINERU_API_TOKEN
        self.mineru_url = settings.MINERU_API_URL
        
    @property
    def system_prompt(self) -> str:
        return """你是一个专业的文档解析助手，负责从Markdown文档中提取结构化信息。
你需要识别论文的各个部分：标题、摘要、关键词、各章节内容、表格数据等。
请以JSON格式返回解析结果。"""
    
    async def run(self, pdf_path: str) -> ParsedContent:
        """
        解析PDF文件
        
        Args:
            pdf_path: PDF文件路径或URL
            
        Returns:
            ParsedContent: 解析后的内容
        """
        logger.info(f"开始解析PDF: {pdf_path}")
        
        # 1. 调用Mineru API转换PDF
        markdown_content = await self._convert_pdf_to_markdown(pdf_path)
        
        if not markdown_content:
            logger.error("PDF转换失败")
            return ParsedContent(raw_markdown="")
        
        # 2. 使用LLM解析Markdown结构
        parsed_content = await self._parse_markdown_structure(markdown_content)
        
        logger.info("PDF解析完成")
        return parsed_content
    
    async def _convert_pdf_to_markdown(self, pdf_path: str) -> Optional[str]:
        """调用Mineru API转换PDF"""
        logger.info("调用Mineru API...")
        
        # 判断是URL还是本地文件
        if pdf_path.startswith("http"):
            # URL方式直接提交
            return await self._submit_url_task(pdf_path)
        else:
            # 本地文件：先尝试上传，失败则使用本地解析
            if not os.path.exists(pdf_path):
                logger.error(f"PDF文件不存在: {pdf_path}")
                return None
            
            # 尝试使用Mineru文件上传API
            markdown = await self._upload_and_parse(pdf_path)
            if markdown:
                return markdown
            
            # 备用方案：本地解析
            logger.info("Mineru上传失败，尝试本地解析...")
            return await self._local_pdf_parse(pdf_path)
    
    async def _submit_url_task(self, url: str) -> Optional[str]:
        """提交URL任务到Mineru"""
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.mineru_token}"
        }
        data = {"url": url, "model_version": "vlm"}
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.mineru_url, 
                    headers=headers, 
                    json=data
                ) as response:
                    if response.status != 200:
                        logger.error(f"Mineru API错误: {response.status}")
                        return None
                    
                    result = await response.json()
                    logger.info(f"任务提交成功: {result}")
                    
                    task_id = result.get("data", {}).get("task_id")
                    if not task_id:
                        logger.error("未获取到任务ID")
                        return None
                
                return await self._poll_task_result(session, headers, task_id)
                
        except Exception as e:
            logger.error(f"Mineru API调用失败: {e}")
            return None
    
    async def _upload_and_parse(self, pdf_path: str) -> Optional[str]:
        """上传本地文件到Mineru并解析"""
        upload_url = "https://mineru.net/api/v4/file/upload"
        
        headers = {
            "Authorization": f"Bearer {self.mineru_token}"
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                # 读取文件并上传
                with open(pdf_path, 'rb') as f:
                    file_data = aiohttp.FormData()
                    file_data.add_field('file',
                                        f,
                                        filename=os.path.basename(pdf_path),
                                        content_type='application/pdf')
                    
                    logger.info(f"上传文件: {pdf_path}")
                    async with session.post(upload_url, headers=headers, data=file_data) as response:
                        if response.status != 200:
                            logger.warning(f"文件上传失败: {response.status}")
                            return None
                        
                        result = await response.json()
                        logger.info(f"上传结果: {result}")
                        
                        # 检查上传结果
                        if result.get("code") != 0:
                            logger.warning(f"上传失败: {result.get('msg')}")
                            return None
                        
                        # 获取文件URL或直接获取task_id
                        file_url = result.get("data", {}).get("url")
                        task_id = result.get("data", {}).get("task_id")
                        
                        if task_id:
                            # 直接有task_id，轮询结果
                            return await self._poll_task_result(session, headers, task_id)
                        elif file_url:
                            # 有URL，提交解析任务
                            return await self._submit_url_task(file_url)
                        else:
                            logger.warning("上传成功但未获取到URL或task_id")
                            return None
                            
        except Exception as e:
            logger.warning(f"文件上传失败: {e}")
            return None
    
    async def _local_pdf_parse(self, pdf_path: str) -> Optional[str]:
        """本地PDF解析（备用方案）"""
        try:
            import fitz  # PyMuPDF
            
            logger.info(f"使用PyMuPDF本地解析: {pdf_path}")
            doc = fitz.open(pdf_path)
            
            markdown_parts = []
            page_count = len(doc)
            for page_num, page in enumerate(doc, 1):
                text = page.get_text("text")
                if text.strip():
                    markdown_parts.append(f"## 第 {page_num} 页\n\n{text}")
            
            doc.close()
            
            markdown = "\n\n".join(markdown_parts)
            logger.info(f"本地解析完成，共 {page_count} 页")
            return markdown
            
        except ImportError:
            logger.error("PyMuPDF未安装，请运行: pip install PyMuPDF")
            return None
        except Exception as e:
            logger.error(f"本地PDF解析失败: {e}")
            return None
    
    async def _poll_task_result(
        self, 
        session: aiohttp.ClientSession, 
        headers: Dict, 
        task_id: str,
        max_wait: int = 300,
        interval: int = 5
    ) -> Optional[str]:
        """轮询获取任务结果"""
        status_url = f"https://mineru.net/api/v4/extract/task/{task_id}"
        
        start_time = time.time()
        while time.time() - start_time < max_wait:
            try:
                async with session.get(status_url, headers=headers) as response:
                    if response.status != 200:
                        logger.warning(f"查询状态失败: {response.status}")
                        await asyncio.sleep(interval)
                        continue
                    
                    result = await response.json()
                    status = result.get("data", {}).get("status")
                    
                    if status == "completed":
                        # 获取Markdown内容
                        md_url = result.get("data", {}).get("markdown_url")
                        if md_url:
                            async with session.get(md_url) as md_response:
                                return await md_response.text()
                        return result.get("data", {}).get("markdown", "")
                    
                    elif status == "failed":
                        logger.error("任务处理失败")
                        return None
                    
                    logger.info(f"任务状态: {status}, 等待中...")
                    await asyncio.sleep(interval)
                    
            except Exception as e:
                logger.error(f"轮询失败: {e}")
                await asyncio.sleep(interval)
        
        logger.error("任务超时")
        return None
    
    async def _parse_markdown_structure(self, markdown: str) -> ParsedContent:
        """使用LLM解析Markdown结构"""
        logger.info("解析Markdown结构...")
        
        prompt = f"""请分析以下Markdown文档，提取论文的结构化信息。

文档内容:
{markdown[:8000]}  # 限制长度避免超出token限制

请以JSON格式返回，包含以下字段:
{{
    "title": "论文标题",
    "abstract": "摘要内容",
    "keywords": ["关键词1", "关键词2"],
    "chapters": {{
        "章节名1": "章节内容摘要",
        "章节名2": "章节内容摘要"
    }},
    "tables": [
        {{"name": "表格名", "description": "表格描述", "data_hint": "数据特征"}}
    ],
    "research_method": "研究方法描述",
    "data_description": "数据描述（如果有）"
}}

只返回JSON，不要其他内容。"""

        try:
            response = await self.llm.simple_chat(prompt)
            data = load_json_from_response(response)

            return ParsedContent(
                title=data.get("title", ""),
                abstract=data.get("abstract", ""),
                keywords=data.get("keywords", []),
                chapters=data.get("chapters", {}),
                tables=data.get("tables", []),
                raw_markdown=markdown
            )
            
        except Exception as e:
            logger.error(f"解析Markdown失败: {e}")
            return ParsedContent(raw_markdown=markdown)
