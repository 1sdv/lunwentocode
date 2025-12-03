"""
LLM JSON 响应处理工具
"""
from __future__ import annotations

import json
from typing import Any

from app.utils.logger import logger


def strip_code_fences(text: str) -> str:
    """移除Markdown代码块标记和多余空白"""
    cleaned = text.strip()

    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if len(lines) > 1:
            cleaned = "\n".join(lines[1:])
        else:
            cleaned = ""

    if cleaned.endswith("```"):
        cleaned = cleaned.rsplit("```", 1)[0]

    return cleaned.strip()


def extract_json_blob(text: str) -> str:
    """
    从响应中提取JSON主体，忽略前后的解释性文本。
    该方法不会尝试修复真正的语法错误，仅做裁剪。
    """
    cleaned = strip_code_fences(text)

    # 从第一个 { 或 [ 开始截取
    start_candidates = [idx for idx in (cleaned.find("{"), cleaned.find("[")) if idx != -1]
    start = min(start_candidates) if start_candidates else 0
    trimmed = cleaned[start:]

    # 以最后一个 } 或 ] 结尾
    end_candidates = [idx for idx in (trimmed.rfind("}"), trimmed.rfind("]")) if idx != -1]
    end = max(end_candidates) + 1 if end_candidates else len(trimmed)

    return trimmed[:end].strip()


def load_json_from_response(response: str) -> Any:
    """清理并解析LLM响应中的JSON"""
    cleaned = extract_json_blob(response)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as exc:
        logger.error("解析JSON失败: %s | 原始响应片段: %s", exc, cleaned[:2000])
        raise
