from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from app.config import SETTINGS_ROOT
from app.services.workflow_strategy import (
    DEFAULT_WORKFLOW_STRATEGY,
    get_workflow_strategy,
    normalize_workflow_strategy,
    workflow_strategy_options,
)


SETTINGS_PATH = SETTINGS_ROOT / "llm.json"
DEFAULT_BASE_URL = "https://api.chshapi.org/v1"
DEFAULT_MODEL = "gpt-5.5"
BASE_URL_ENDPOINT_SUFFIXES = (
    "/chat/completions",
    "/completions",
    "/responses",
    "/models",
)


def get_llm_settings() -> dict[str, Any]:
    stored = load_settings()
    env_key = os.getenv("OPENAI_API_KEY", "")
    api_key = stored.get("api_key") or env_key
    source = "local" if stored.get("api_key") else "env" if env_key else ""
    strategy = get_workflow_strategy(stored.get("workflow_strategy"))
    base_url = effective_base_url(stored.get("base_url"))
    last_test = stored.get("last_test") if isinstance(stored.get("last_test"), dict) else {}
    return {
        "provider": "openai",
        "configured": bool(api_key),
        "source": source,
        "masked_api_key": mask_api_key(api_key),
        "base_url": base_url,
        "model": stored.get("model") or DEFAULT_MODEL,
        "workflow_strategy": strategy["id"],
        "workflow_strategy_label": strategy["label"],
        "workflow_strategy_summary": strategy["summary"],
        "workflow_strategy_options": workflow_strategy_options(),
        "last_test": last_test,
    }


def get_private_llm_config() -> dict[str, str]:
    stored = load_settings()
    env_key = os.getenv("OPENAI_API_KEY", "")
    return {
        "api_key": stored.get("api_key") or env_key,
        "base_url": effective_base_url(stored.get("base_url")),
        "model": stored.get("model") or DEFAULT_MODEL,
        "workflow_strategy": normalize_workflow_strategy(stored.get("workflow_strategy")),
    }


def save_llm_settings(
    api_key: str | None,
    base_url: str | None,
    model: str | None,
    workflow_strategy: str | None = None,
) -> dict[str, Any]:
    current = load_settings()
    normalized_key = normalize_api_key(api_key)
    normalized_base_url = normalize_base_url(base_url)
    normalized_model = normalize_model(model)
    normalized_strategy = normalize_workflow_strategy(
        workflow_strategy if workflow_strategy is not None else current.get("workflow_strategy", DEFAULT_WORKFLOW_STRATEGY)
    )
    previous = {
        "api_key": current.get("api_key", ""),
        "base_url": current.get("base_url") or DEFAULT_BASE_URL,
        "model": current.get("model") or DEFAULT_MODEL,
        "workflow_strategy": normalize_workflow_strategy(current.get("workflow_strategy", DEFAULT_WORKFLOW_STRATEGY)),
    }
    incoming = {
        "api_key": normalized_key or previous["api_key"],
        "base_url": normalized_base_url or previous["base_url"],
        "model": normalized_model or previous["model"],
        "workflow_strategy": normalized_strategy,
    }

    if normalized_key:
        current["api_key"] = normalized_key

    if normalized_base_url:
        current["base_url"] = normalized_base_url
    if normalized_model:
        current["model"] = normalized_model
    current["workflow_strategy"] = normalized_strategy
    if incoming != previous:
        current.pop("last_test", None)

    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_PATH.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
    return get_llm_settings()


def record_llm_test_result(ok: bool, status: str, message: str, diagnosis: dict[str, Any] | None = None) -> dict[str, Any]:
    current = load_settings()
    row = {
        "ok": bool(ok),
        "status": str(status or ""),
        "message": str(message or "")[:300],
        "tested_at": datetime.now().isoformat(timespec="seconds"),
    }
    if isinstance(diagnosis, dict) and diagnosis:
        row["diagnosis"] = {
            key: str(diagnosis.get(key) or "")[:220]
            for key in ["category", "label", "suggested_action"]
            if diagnosis.get(key)
        }
    current["last_test"] = row
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_PATH.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
    return get_llm_settings()


def clear_llm_settings() -> dict[str, Any]:
    if SETTINGS_PATH.exists():
        SETTINGS_PATH.unlink()
    return get_llm_settings()


def load_settings() -> dict[str, Any]:
    if not SETTINGS_PATH.exists():
        return {}
    try:
        payload = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    if not isinstance(payload, dict):
        return {}
    return payload


def normalize_api_key(value: str | None) -> str:
    if value is None:
        return ""
    value = value.strip()
    if not value:
        return ""
    if any(ch.isspace() for ch in value):
        raise ValueError("API Key 不能包含空白字符")
    if len(value) < 20:
        raise ValueError("API Key 长度过短")
    return value


def normalize_base_url(value: str | None) -> str:
    if value is None:
        return ""
    value = value.strip().rstrip("/")
    if not value:
        return DEFAULT_BASE_URL
    if not (value.startswith("https://") or value.startswith("http://")):
        raise ValueError("Base URL 必须以 http:// 或 https:// 开头")
    value = strip_completion_endpoint(value)
    parsed = urlsplit(value)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError("Base URL must be a complete http(s) URL")
    path = parsed.path.rstrip("/")
    if parsed.netloc.lower() == "api.openai.com" and not path:
        path = "/v1"
    return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


def strip_completion_endpoint(value: str) -> str:
    value = value.strip().rstrip("/")
    lowered = value.lower()
    for suffix in BASE_URL_ENDPOINT_SUFFIXES:
        if lowered.endswith(suffix):
            value = value[: -len(suffix)].rstrip("/")
            break
    return value


def effective_base_url(value: str | None) -> str:
    try:
        return normalize_base_url(value or DEFAULT_BASE_URL)
    except ValueError:
        return str(value or DEFAULT_BASE_URL).strip().rstrip("/")


def normalize_model(value: str | None) -> str:
    if value is None:
        return ""
    value = value.strip()
    if not value:
        return DEFAULT_MODEL
    if any(ch.isspace() for ch in value):
        raise ValueError("模型名称不能包含空白字符")
    return value


def mask_api_key(api_key: str) -> str:
    if not api_key:
        return ""
    if len(api_key) <= 12:
        return "*" * len(api_key)
    return f"{api_key[:7]}...{api_key[-4:]}"
