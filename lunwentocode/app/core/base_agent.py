"""
Agent 基类 - 无状态设计，每次调用独立
"""
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from app.core.llm import LLM
from app.utils.logger import logger


class BaseAgent(ABC):
    """Agent 基类 - 无状态设计"""
    
    def __init__(self, llm: LLM):
        """
        初始化Agent
        
        Args:
            llm: LLM实例
        """
        self.llm = llm
        
    @property
    @abstractmethod
    def system_prompt(self) -> str:
        """系统提示词"""
        pass
    
    @abstractmethod
    async def run(self, *args, **kwargs) -> Any:
        """执行Agent任务"""
        pass
    
    async def call_llm(self, prompt: str, context: Optional[str] = None) -> str:
        """
        独立调用LLM（无历史依赖）
        
        Args:
            prompt: 用户提示
            context: 可选的上下文信息（直接包含在prompt中）
            
        Returns:
            LLM响应文本
        """
        messages = [
            {"role": "system", "content": self.system_prompt}
        ]
        
        # 如果有上下文，组合到prompt中
        if context:
            full_prompt = f"{context}\n\n{prompt}"
        else:
            full_prompt = prompt
            
        messages.append({"role": "user", "content": full_prompt})
        
        logger.debug(f"{self.__class__.__name__} 调用LLM，prompt长度={len(full_prompt)}")
        
        response = await self.llm.chat(messages)
        return response.choices[0].message.content
    
    async def call_llm_with_tools(
        self, 
        prompt: str, 
        tools: List[Dict],
        context: Optional[str] = None
    ) -> Any:
        """
        使用工具调用LLM
        
        Args:
            prompt: 用户提示
            tools: 工具定义列表
            context: 可选的上下文信息
            
        Returns:
            LLM响应
        """
        messages = [
            {"role": "system", "content": self.system_prompt}
        ]
        
        if context:
            full_prompt = f"{context}\n\n{prompt}"
        else:
            full_prompt = prompt
            
        messages.append({"role": "user", "content": full_prompt})
        
        logger.debug(f"{self.__class__.__name__} 调用LLM(with tools)，prompt长度={len(full_prompt)}")
        
        response = await self.llm.chat(messages, tools=tools)
        return response
