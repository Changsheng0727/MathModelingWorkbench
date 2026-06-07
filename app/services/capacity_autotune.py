from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from app.config import SETTINGS_ROOT
from app.services.store import load_json, save_json


LEDGER_PATH = SETTINGS_ROOT / "capacity_autotune_events.json"
MAX_EVENTS = 200


def record_capacity_autotune_event(plan: dict[str, Any], settings_after: dict[str, Any], *, source: str = "manual") -> dict[str, Any]:
    now = datetime.now().isoformat(timespec="seconds")
    updates = plan.get("updates", {}) if isinstance(plan.get("updates"), dict) else {}
    event = {
        "id": f"cap-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid4().hex[:8]}",
        "recorded_at": now,
        "source": source,
        "status": str(plan.get("status") or "unknown"),
        "summary": str(plan.get("summary") or ""),
        "applied": bool(updates),
        "updates": updates,
        "reasons": plan.get("reasons", []) if isinstance(plan.get("reasons"), list) else [],
        "signals": plan.get("signals", {}) if isinstance(plan.get("signals"), dict) else {},
        "before": plan.get("before", {}) if isinstance(plan.get("before"), dict) else {},
        "after": plan.get("after", {}) if isinstance(plan.get("after"), dict) else {},
        "settings_after": public_settings(settings_after),
    }
    ledger = read_ledger()
    items = [event, *ledger.get("items", [])]
    save_json(LEDGER_PATH, {"updated_at": now, "items": items[:MAX_EVENTS]})
    return event


def list_capacity_autotune_events(limit: int = 30) -> dict[str, Any]:
    ledger = read_ledger()
    items = ledger.get("items", [])
    if not isinstance(items, list):
        items = []
    limit = max(1, min(100, int(limit or 30)))
    public_items = [item for item in items if isinstance(item, dict)]
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "ledger_path": str(LEDGER_PATH),
        "latest": public_items[0] if public_items else None,
        "items": public_items[:limit],
        "total_tracked": len(public_items),
    }


def read_ledger() -> dict[str, Any]:
    if not LEDGER_PATH.exists():
        return {"items": []}
    try:
        payload = load_json(LEDGER_PATH)
    except Exception:
        return {"items": []}
    if not isinstance(payload, dict):
        return {"items": []}
    items = payload.get("items", [])
    payload["items"] = items if isinstance(items, list) else []
    return payload


def public_settings(settings: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "auto_workflow_workers",
        "delivery_batch_job_workers",
        "delivery_package_workers",
        "max_auto_workflow_workers",
        "max_delivery_batch_job_workers",
        "max_delivery_package_workers",
        "source",
    ]
    return {key: settings.get(key) for key in keys if key in settings}
