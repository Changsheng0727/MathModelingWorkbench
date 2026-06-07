from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from app.services.attachment_profile import build_attachment_profile
from app.services.parallel_task_plan import build_parallel_task_plan
from app.services.performance_health import PERFORMANCE_HEALTH_JSON_RELATIVE, write_performance_health_report
from app.services.repair_center import build_repair_briefing, write_repair_briefing
from app.services.store import load_json
from app.services.workflow_strategy import get_workflow_strategy, public_workflow_strategy


def refresh_diagnostic_assets(
    root: Path,
    meta: dict[str, Any],
    analysis: dict[str, Any],
    *,
    workflow_strategy: dict[str, Any] | str | None = None,
    force_attachment: bool = True,
) -> dict[str, Any]:
    if not isinstance(analysis, dict) or not analysis:
        raise ValueError("项目尚未完成赛题分析，无法刷新诊断资产。")

    strategy = get_workflow_strategy(workflow_strategy if workflow_strategy is not None else meta.get("workflow_strategy"))
    artifacts: dict[str, str] = {}
    artifacts.update(build_attachment_profile(root, analysis, force=force_attachment))
    artifacts.update(build_parallel_task_plan(root, analysis, workflow_strategy=strategy))
    artifacts.update(write_performance_health_report(root, meta))
    artifacts.update(write_repair_briefing(root, meta))

    refreshed_at = datetime.now().isoformat(timespec="seconds")
    meta["diagnostics_refresh_status"] = "success"
    meta["diagnostics_refreshed_at"] = refreshed_at
    meta.pop("diagnostics_refresh_error", None)
    meta["workflow_strategy"] = strategy["id"]
    meta["workflow_strategy_label"] = strategy["label"]
    meta.setdefault("artifacts", {}).update(artifacts)

    health_payload = load_payload(root / PERFORMANCE_HEALTH_JSON_RELATIVE)
    repair_payload = build_repair_briefing(root, meta)
    return {
        "status": "success",
        "refreshed_at": refreshed_at,
        "workflow_strategy": public_workflow_strategy(strategy["id"]),
        "artifacts": artifacts,
        "health": compact_health_payload(health_payload),
        "repair": compact_repair_payload(repair_payload),
    }


def compact_health_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    concurrency = payload.get("concurrency") if isinstance(payload.get("concurrency"), dict) else {}
    reliability = payload.get("reliability") if isinstance(payload.get("reliability"), dict) else {}
    return {
        "status": payload.get("status", ""),
        "label": payload.get("label", ""),
        "headline": payload.get("headline", ""),
        "scores": payload.get("scores", {}) if isinstance(payload.get("scores"), dict) else {},
        "metrics": {
            "attachment_workers": concurrency.get("attachment_workers", 0),
            "planned_task_count": concurrency.get("planned_task_count", 0),
            "parallel_group_count": concurrency.get("parallel_group_count", 0),
            "planned_max_workers": concurrency.get("planned_max_workers", 0),
            "repair_count": reliability.get("repair_count", 0),
        },
    }


def compact_repair_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    primary_action = payload.get("primary_action") if isinstance(payload.get("primary_action"), dict) else {}
    return {
        "status": payload.get("status", ""),
        "label": payload.get("label", ""),
        "summary": payload.get("summary", ""),
        "can_resume": bool(payload.get("can_resume")),
        "primary_action": {
            "id": primary_action.get("id", ""),
            "label": primary_action.get("label", ""),
            "priority": primary_action.get("priority", ""),
        },
        "evidence_count": len(payload.get("evidence", []) if isinstance(payload.get("evidence"), list) else []),
    }


def load_payload(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = load_json(path)
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}
