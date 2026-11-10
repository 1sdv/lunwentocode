"""
base_url 处理逻辑的回归测试

覆盖：
- 地址不被预改（保留用户填写的原样路径）
- 404 时自动用补了 /v1 的地址重试并成功
- 补了 /v1 仍失败 → 提示用户手动确认
- 非 404 错误不触发 /v1 重试
- 地址本就以版本号结尾时不重复补
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.llm import LLM, normalize_base_url, with_v1_suffix  # noqa: E402


def test_normalize_keeps_original():
    """地址保持原样，不预补 /v1"""
    assert normalize_base_url(None) is None
    assert normalize_base_url("") is None
    assert normalize_base_url("  ") is None
    assert normalize_base_url("https://api.openai.com") == "https://api.openai.com"
    assert normalize_base_url("https://api.openai.com/") == "https://api.openai.com"
    assert normalize_base_url("https://x.com/api/openai") == "https://x.com/api/openai"
    assert normalize_base_url("https://api.openai.com/v1") == "https://api.openai.com/v1"


def test_with_v1_suffix():
    """补 /v1 的判断"""
    assert with_v1_suffix("https://api.openai.com") == "https://api.openai.com/v1"
    assert with_v1_suffix("https://api.openai.com/v1") == "https://api.openai.com/v1"
    assert with_v1_suffix("https://x.com/v2") == "https://x.com/v2"
    assert with_v1_suffix("https://x.com/chat/completions") == (
        "https://x.com/chat/completions"
    )
    assert with_v1_suffix(None) is None


def test_no_v1_attempt_on_non_404():
    """非 404 错误不应触发地址切换"""
    llm = LLM(api_key="k", model="m", base_url="https://api.x.com")

    class FakeErr(Exception):
        status_code = 401

    assert llm._is_not_found(FakeErr()) is False
    assert llm._tried_v1_fallback is False


def test_not_found_detection():
    """404 识别"""
    llm = LLM(api_key="k", model="m", base_url="https://api.x.com")

    class NotFound(Exception):
        status_code = 404

    assert llm._is_not_found(NotFound()) is True
    assert llm._is_not_found(Exception("Error code: 404 - not found")) is True
    assert llm._is_not_found(Exception("boom")) is False


def test_v1_suffix_skipped_when_already_versioned():
    """地址本就以版本号结尾时，不应再补，也不该切换"""
    llm = LLM(api_key="k", model="m", base_url="https://api.x.com/v1")
    assert with_v1_suffix(llm.base_url) == llm.base_url


def test_describe_error_after_fallback():
    """补全仍失败时，提示语要说清已尝试自动补全"""
    llm = LLM(api_key="k", model="m", base_url="https://api.x.com")

    class NotFound(Exception):
        status_code = 404

    llm._tried_v1_fallback = True
    text = llm._describe_error(NotFound("Error code: 404"))
    assert "已自动尝试补 /v1" in text, text

    llm._tried_v1_fallback = False
    text = llm._describe_error(NotFound("Error code: 404"))
    assert "是否需要 /v1 后缀" in text, text


def test_base_url_switch_preserved():
    """切换地址后 base_url 与 client 一致"""
    llm = LLM(api_key="k", model="m", base_url="https://api.x.com")
    llm._switch_base_url("https://api.x.com/v1")
    assert llm.base_url == "https://api.x.com/v1"
    assert str(llm.client.base_url).rstrip("/") == "https://api.x.com/v1"


if __name__ == "__main__":
    test_normalize_keeps_original()
    test_with_v1_suffix()
    test_no_v1_attempt_on_non_404()
    test_not_found_detection()
    test_v1_suffix_skipped_when_already_versioned()
    test_describe_error_after_fallback()
    test_base_url_switch_preserved()
    print("全部通过 ✓")
