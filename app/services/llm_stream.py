from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime
from pathlib import Path
import time
from typing import Any, Iterator

from app.services.llm_settings import redact_sensitive_text
from app.services.store import load_json, save_json


LLM_LIVE_STREAM_RELATIVE = "artifacts/llm_live_stream.json"

_ACTIVE_STREAM: ContextVar["LLMLiveStream | None"] = ContextVar("active_llm_stream", default=None)


def utc_now_text() -> str:
    return datetime.now().isoformat(timespec="seconds")


def tail_text(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[-limit:]


def safe_stream_text(value: Any) -> str:
    return redact_sensitive_text(str(value or ""))


class LLMLiveStream:
    def __init__(self, root: Path, channel: str, title: str) -> None:
        self.root = root
        self.channel = safe_stream_text(channel)
        self.title = safe_stream_text(title)
        self.path = root / LLM_LIVE_STREAM_RELATIVE
        self.seq = 0
        self.events: list[dict[str, Any]] = []
        self.current: dict[str, Any] | None = None
        self.content_tail = ""
        self.content_chars = 0
        self.status = "running"
        self.started_at = utc_now_text()
        self.updated_at = self.started_at
        self._pending_chars = 0
        self._last_write = 0.0
        self._terminal = False

    def start(self, detail: str = "") -> None:
        self.emit("session_start", "直播开始", detail or self.title, status="running")

    def begin_request(self, label: str, attempt: int, attempts: int, max_tokens: int | None) -> None:
        self.flush()
        label = safe_stream_text(label)
        self.current = {
            "label": label,
            "status": "running",
            "attempt": attempt,
            "attempts": attempts,
            "max_tokens": max_tokens,
            "started_at": utc_now_text(),
            "updated_at": utc_now_text(),
            "content_tail": "",
            "content_chars": 0,
            "detail": f"正在接收第 {attempt}/{attempts} 次 LLM 流式响应。",
        }
        self.emit("llm_request", label, self.current["detail"], status="running")

    def append_delta(self, delta: str) -> None:
        if not delta:
            return
        delta = str(delta)
        if self.current is None:
            self.current = {
                "label": "大模型生成内容",
                "status": "running",
                "started_at": utc_now_text(),
                "updated_at": utc_now_text(),
                "content_tail": "",
                "content_chars": 0,
                "detail": "正在接收 LLM 流式响应。",
            }
        self.content_chars += len(delta)
        self.content_tail = safe_stream_text(tail_text(self.content_tail + delta, 8000))
        self.current["content_chars"] = int(self.current.get("content_chars") or 0) + len(delta)
        self.current["content_tail"] = safe_stream_text(tail_text(str(self.current.get("content_tail") or "") + delta, 5000))
        self.current["updated_at"] = utc_now_text()
        self.current["detail"] = f"已接收 {self.current['content_chars']} 个字符，界面显示最近片段。"
        self.updated_at = self.current["updated_at"]
        self._pending_chars += len(delta)
        now = time.time()
        if self._pending_chars >= 120 or now - self._last_write >= 0.45:
            self.flush()

    def finish_request(self, status: str, detail: str = "") -> None:
        self.flush()
        label = self.current.get("label") if self.current else "大模型生成内容"
        status = safe_stream_text(status)
        detail = safe_stream_text(detail)
        if self.current:
            self.current["status"] = status
            self.current["finished_at"] = utc_now_text()
            if detail:
                self.current["detail"] = detail
        self.emit("llm_done" if status == "success" else "llm_error", str(label), detail, status=status)
        if status == "success":
            self.current = None

    def emit(self, kind: str, label: str, detail: str = "", status: str = "info") -> None:
        self.seq += 1
        event = {
            "seq": self.seq,
            "time": utc_now_text(),
            "kind": safe_stream_text(kind),
            "label": safe_stream_text(label),
            "detail": safe_stream_text(detail),
            "status": safe_stream_text(status),
        }
        self.events.append(event)
        self.events = self.events[-80:]
        self.updated_at = event["time"]
        self._write()

    def flush(self) -> None:
        if self._pending_chars <= 0 and self._last_write > 0:
            return
        self.seq += 1
        self._pending_chars = 0
        self.updated_at = utc_now_text()
        self._write()

    def finish(self, status: str, detail: str = "") -> None:
        if self._terminal:
            return
        self.flush()
        status = safe_stream_text(status)
        self.status = status
        self._terminal = True
        self.emit("session_finish", "直播结束", detail, status=status)

    def is_terminal(self) -> bool:
        return self._terminal

    def snapshot(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "channel": self.channel,
            "title": self.title,
            "started_at": self.started_at,
            "updated_at": self.updated_at,
            "seq": self.seq,
            "current": self.current,
            "events": self.events,
            "content_tail": self.content_tail,
            "content_chars": self.content_chars,
        }

    def _write(self) -> None:
        self._last_write = time.time()
        save_json(self.path, self.snapshot())


def active_llm_stream() -> LLMLiveStream | None:
    return _ACTIVE_STREAM.get()


@contextmanager
def bind_llm_stream(root: Path, channel: str, title: str, detail: str = "") -> Iterator[LLMLiveStream]:
    stream = LLMLiveStream(root, channel, title)
    stream.start(detail)
    token = _ACTIVE_STREAM.set(stream)
    try:
        yield stream
        if not stream.is_terminal():
            stream.finish("success", "大模型直播已结束。")
    except Exception as exc:
        if not stream.is_terminal():
            stream.finish("failed", f"{type(exc).__name__}: {exc}")
        raise
    finally:
        _ACTIVE_STREAM.reset(token)


def load_llm_live_stream(root: Path) -> dict[str, Any]:
    path = root / LLM_LIVE_STREAM_RELATIVE
    if not path.exists():
        return {}
    try:
        payload = load_json(path)
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}
