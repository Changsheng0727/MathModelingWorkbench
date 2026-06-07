from __future__ import annotations

import os
from typing import Any

from app.config import SETTINGS_ROOT
from app.services.store import load_json, save_json


SETTINGS_PATH = SETTINGS_ROOT / "capacity.json"

DEFAULT_AUTO_WORKFLOW_WORKERS = 2
DEFAULT_DELIVERY_BATCH_JOB_WORKERS = 1
DEFAULT_DELIVERY_PACKAGE_WORKERS = 4
MAX_AUTO_WORKFLOW_WORKERS = 8
MAX_DELIVERY_BATCH_JOB_WORKERS = 4
MAX_DELIVERY_PACKAGE_WORKERS = 8


def load_capacity_settings() -> dict[str, Any]:
    stored = read_settings()
    auto_workers = int_setting(
        stored.get("auto_workflow_workers"),
        env_name="MODELARK_AUTO_WORKFLOW_WORKERS",
        default=DEFAULT_AUTO_WORKFLOW_WORKERS,
        minimum=1,
        maximum=MAX_AUTO_WORKFLOW_WORKERS,
    )
    delivery_job_workers = int_setting(
        stored.get("delivery_batch_job_workers"),
        env_name="MODELARK_DELIVERY_BATCH_JOB_WORKERS",
        default=DEFAULT_DELIVERY_BATCH_JOB_WORKERS,
        minimum=1,
        maximum=MAX_DELIVERY_BATCH_JOB_WORKERS,
    )
    delivery_package_workers = int_setting(
        stored.get("delivery_package_workers"),
        env_name="MODELARK_DELIVERY_PACKAGE_WORKERS",
        default=DEFAULT_DELIVERY_PACKAGE_WORKERS,
        minimum=1,
        maximum=MAX_DELIVERY_PACKAGE_WORKERS,
    )
    return {
        "auto_workflow_workers": auto_workers,
        "delivery_batch_job_workers": delivery_job_workers,
        "delivery_package_workers": delivery_package_workers,
        "max_auto_workflow_workers": MAX_AUTO_WORKFLOW_WORKERS,
        "max_delivery_batch_job_workers": MAX_DELIVERY_BATCH_JOB_WORKERS,
        "max_delivery_package_workers": MAX_DELIVERY_PACKAGE_WORKERS,
        "source": source_label(stored),
        "settings_path": str(SETTINGS_PATH),
    }


def save_capacity_settings(payload: dict[str, Any]) -> dict[str, Any]:
    current = read_settings()
    if "auto_workflow_workers" in payload:
        current["auto_workflow_workers"] = clamp_int(payload.get("auto_workflow_workers"), 1, MAX_AUTO_WORKFLOW_WORKERS)
    if "delivery_batch_job_workers" in payload:
        current["delivery_batch_job_workers"] = clamp_int(payload.get("delivery_batch_job_workers"), 1, MAX_DELIVERY_BATCH_JOB_WORKERS)
    if "delivery_package_workers" in payload:
        current["delivery_package_workers"] = clamp_int(payload.get("delivery_package_workers"), 1, MAX_DELIVERY_PACKAGE_WORKERS)
    save_json(SETTINGS_PATH, current)
    return load_capacity_settings()


def read_settings() -> dict[str, Any]:
    if not SETTINGS_PATH.exists():
        return {}
    try:
        payload = load_json(SETTINGS_PATH)
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def int_setting(value: Any, *, env_name: str, default: int, minimum: int, maximum: int) -> int:
    if value is None or value == "":
        env_value = os.environ.get(env_name, "").strip()
        value = env_value if env_value else default
    return clamp_int(value, minimum, maximum)


def clamp_int(value: Any, minimum: int, maximum: int) -> int:
    try:
        parsed = int(float(value))
    except (TypeError, ValueError):
        parsed = minimum
    return max(minimum, min(maximum, parsed))


def source_label(stored: dict[str, Any]) -> str:
    if stored:
        return "本地设置"
    env_keys = [
        "MODELARK_AUTO_WORKFLOW_WORKERS",
        "MODELARK_DELIVERY_BATCH_JOB_WORKERS",
        "MODELARK_DELIVERY_PACKAGE_WORKERS",
    ]
    if any(os.environ.get(key) for key in env_keys):
        return "环境变量"
    return "默认值"
