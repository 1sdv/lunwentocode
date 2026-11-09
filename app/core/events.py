"""
事件总线 - 进度事件发布/订阅

工作流和各 Agent 通过事件总线发布进度消息，
CLI 入口订阅后打印到控制台，Web 入口订阅后推送到 Gradio 流式输出，
后续如需接入 Redis/WebSocket 只需增加新的订阅端。
"""
import threading
from typing import Any, Callable, Dict, List

# 事件类型
EVENT_SYSTEM = "system"        # 流程进度消息
EVENT_CODE = "code"            # 代码执行（input.code 为执行的代码）
EVENT_CODE_OUTPUT = "code_output"  # 代码输出
EVENT_REPORT = "report"        # 报告写作进度
EVENT_ERROR = "error"          # 错误


class EventBus:
    """同步事件总线，线程安全的发布/订阅"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._subscribers: List[Callable[[Dict[str, Any]], None]] = []

    def subscribe(self, callback: Callable[[Dict[str, Any]], None]) -> Callable[[], None]:
        """订阅事件，返回取消订阅函数"""
        with self._lock:
            self._subscribers.append(callback)

        def unsubscribe() -> None:
            with self._lock:
                if callback in self._subscribers:
                    self._subscribers.remove(callback)

        return unsubscribe

    def publish(self, event_type: str, content: str, **extra: Any) -> None:
        """向所有订阅者发布事件"""
        event: Dict[str, Any] = {"type": event_type, "content": content}
        event.update(extra)
        for callback in list(self._subscribers):
            try:
                callback(event)
            except Exception:
                pass
