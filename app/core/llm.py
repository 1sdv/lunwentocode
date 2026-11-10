"""
LLM 调用封装 - 使用OpenAI SDK
"""
import asyncio
import os

# httpx 无法解析 NO_PROXY 中的 IPv6 字面量 [::1]，在任何 httpx 客户端创建前先清理
for _key in ("NO_PROXY", "no_proxy"):
    _val = os.environ.get(_key, "")
    if "[::1]" in _val:
        _cleaned = _val.replace("[::1],", "").replace("[::1]", "").strip(",")
        if _cleaned:
            os.environ[_key] = _cleaned
        else:
            os.environ.pop(_key, None)

import httpx
from typing import Callable, List, Dict, Any, Optional
from openai import AsyncOpenAI
from app.config.settings import settings
from app.utils.logger import logger


def normalize_base_url(base_url: Optional[str]) -> Optional[str]:
    """规范化接口地址，自动补齐缺失的 /v1 后缀。

    很多人填写 base_url 时会漏掉 /v1，导致 404 Not Found。
    这里做一次容错：地址非空且末段不是版本号时补上 /v1。
    已带 /v1 或以其他版本号结尾的保持原样。
    """
    if not base_url:
        return base_url
    url = base_url.strip().rstrip("/")
    if not url:
        return url

    # 末段若是版本号（v1/v2/...）或已是完整接口路径，则不再追加
    last = url.rsplit("/", 1)[-1].lower()
    if last.startswith("v") and last[1:].isdigit():
        return url
    # 有些服务用 /chat/completions 这样的完整路径，也不追加
    if last in ("chat", "completions", "chat/completions"):
        return url
    return f"{url}/v1"


class LLM:
    """LLM 调用类"""
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: float = 300.0,  # 默认5分钟超时
        on_error: Optional[Callable[[str], None]] = None,
    ):
        self.api_key = api_key or settings.LLM_API_KEY
        self.model = model or settings.LLM_MODEL
        self.base_url = normalize_base_url(base_url or settings.LLM_BASE_URL)
        # 调用失败时的回调（用于把错误推送到前端终端）
        self.on_error = on_error
        
        # 初始化OpenAI客户端，设置超时
        # max_retries=0：SDK 内层不再重试，由 chat() 统一控制重试次数，
        # 否则两层重试叠加会让失败反馈非常迟缓。
        self.client = AsyncOpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=httpx.Timeout(timeout, connect=60.0),  # 连接超时60秒，总超时5分钟
            max_retries=0,
        )
        
        logger.info(
            f"LLM初始化: model={self.model}, base_url={self.base_url}, timeout={timeout}s"
        )

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
                detail = self._describe_error(e)
                is_last = attempt >= max_retries - 1
                logger.error(f"LLM调用失败 (尝试 {attempt + 1}): {detail}")
                # 中间次重试只在日志里记录，不打扰前端终端；
                # 最后一次失败才提示，避免终端被重复刷屏
                if is_last:
                    self._notify_error(f"{detail}（已重试 {max_retries} 次仍失败）")
                if not is_last:
                    await asyncio.sleep(2 ** attempt)  # 指数退避
                else:
                    raise

    def _describe_error(self, exc: Exception) -> str:
        """把异常转成对用户友好的说明"""
        name = type(exc).__name__
        msg = str(exc).strip()
        low = msg.lower()

        # 404 常见于 base_url 漏了 /v1
        if "404" in low or "not found" in low:
            hint = "（请检查接口地址 base_url 是否需要 /v1 后缀）"
        elif "401" in low or "unauthorized" in low:
            hint = "（API Key 无效或已过期）"
        elif "429" in low:
            hint = "（请求过于频繁或额度已用尽）"
        elif "connection" in low or "connect" in low:
            hint = "（无法连接服务器，请检查地址与网络）"
        else:
            hint = ""

        first_line = msg.splitlines()[0] if msg else name
        return f"LLM 调用失败：{first_line}{hint}"

    def _notify_error(self, detail: str) -> None:
        """把错误推给订阅者（前端终端）"""
        if not self.on_error:
            return
        try:
            self.on_error(detail)
        except Exception:  # noqa: BLE001
            pass

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
