"""
LLM 调用封装 - 使用OpenAI SDK
"""
import asyncio
import httpx
from typing import List, Dict, Any, Optional
from openai import AsyncOpenAI
from app.config.settings import settings
from app.utils.logger import logger


class LLM:
    """LLM 调用类"""
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: float = 300.0,  # 默认5分钟超时
    ):
        self.api_key = api_key or settings.LLM_API_KEY
        self.model = model or settings.LLM_MODEL
        self.base_url = base_url or settings.LLM_BASE_URL
        
        # 初始化OpenAI客户端，设置超时
        self.client = AsyncOpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=httpx.Timeout(timeout, connect=60.0),  # 连接超时60秒，总超时5分钟
        )
        
        logger.info(f"LLM初始化: model={self.model}, timeout={timeout}s")
        
    async def chat(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict]] = None,
        tool_choice: Optional[str] = None,
        temperature: float = 1,
        max_tokens: Optional[int] = None,
        max_retries: int = 3,
    ) -> Any:
        """
        调用LLM进行对话
        
        Args:
            messages: 对话历史
            tools: 工具定义
            tool_choice: 工具选择策略
            temperature: 温度参数
            max_tokens: 最大token数
            max_retries: 最大重试次数
            
        Returns:
            LLM响应
        """
        kwargs = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }
            
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = tool_choice or "auto"
            
        if max_tokens:
            kwargs["max_tokens"] = max_tokens
        
        for attempt in range(max_retries):
            try:
                logger.debug(f"LLM调用 (尝试 {attempt + 1}/{max_retries})")
                response = await self.client.chat.completions.create(**kwargs)
                return response
            except Exception as e:
                logger.error(f"LLM调用失败 (尝试 {attempt + 1}): {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)  # 指数退避
                else:
                    raise
    
    async def simple_chat(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """
        简单对话，返回文本内容
        
        Args:
            prompt: 用户提示
            system_prompt: 系统提示
            
        Returns:
            响应文本
        """
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        response = await self.chat(messages)
        return response.choices[0].message.content
