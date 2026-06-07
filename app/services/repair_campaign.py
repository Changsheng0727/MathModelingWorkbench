from __future__ import annotations

import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from app.config import SETTINGS_ROOT
from app.services.auto_workflow_jobs import start_auto_workflow_job
from app.services.diagnostic_refresh import refresh_diagnostic_assets
from app.services.llm_settings import get_llm_settings
from app.services.repair_center import build_repair_briefing, write_repair_briefing
from app.services.store import load_json, project_root, save_json
from app.services.trust_center import needs_repair


_LEDGER_PATH = SETTINGS_ROOT / "repair_campaigns.json"
_LOCK = threading.RLock()


def start_repair_campaign(
    projects: list[dict[str, Any]],
    *,
    queue_resumes: bool = True,
    refresh_diagnostics: bool = True,
    limit: int = 20,
) -> dict[str, Any]:
    limit = max(1, min(80, int(limit or 20)))
    campaign_id = f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"
    generated_at = now_iso()
    api_configured = bool(get_llm_settings().get("configured"))
    candidates = [project for project in projects if isinstance(project, dict) and project.get("id") and needs_repair(project)]
    candidates.sort(key=campaign_rank, reverse=True)
    rows: list[dict[str, Any]] = []
    counts = {
        "requested": len(candidates[:limit]),
        "diagnosed": 0,
        "briefed": 0,
        "queued": 0,
        "skipped": 0,
        "failed": 0,
    }

    for project in candidates[:limit]:
        row = repair_project(project, queue_resumes=queue_resumes and api_configured, refresh_diagnostics=refresh_diagnostics)
        rows.append(row)
        status = row.get("status")
        if row.get("diagnostics_status") == "success":
            counts["diagnosed"] += 1
        if row.get("repair_status") == "success":
            counts["briefed"] += 1
        if status == "queued":
            counts["queued"] += 1
        elif status == "failed":
            counts["failed"] += 1
        elif status == "skipped":
            counts["skipped"] += 1

    campaign = {
        "id": campaign_id,
        "stage": "repair_campaign",
        "generated_at": generated_at,
        "queue_resumes_requested": bool(queue_resumes),
        "queue_resumes_enabled": bool(queue_resumes and api_configured),
        "refresh_diagnostics": bool(refresh_diagnostics),
        "api_configured": api_configured,
        "candidate_count": len(candidates),
        **counts,
        "summary": campaign_summary(counts, api_configured, queue_resumes),
        "projects": rows,
    }
    record_campaign(campaign)
    return campaign


def list_repair_campaigns(limit: int = 30) -> dict[str, Any]:
    limit = max(1, min(100, int(limit or 30)))
    with _LOCK:
        ledger = load_ledger()
        rows = [normalize_campaign(row) for row in ledger.get("campaigns", [])[:limit] if isinstance(row, dict)]
        return {
            "generated_at": now_iso(),
            "ledger_path": str(_LEDGER_PATH),
            "total_tracked": len(ledger.get("campaigns", [])),
            "latest": rows[0] if rows else {},
            "campaigns": rows,
        }


def repair_project(project: dict[str, Any], *, queue_resumes: bool, refresh_diagnostics: bool) -> dict[str, Any]:
    project_id = str(project.get("id") or "")
    name = str(project.get("name") or project.get("original_name") or project_id)
    row: dict[str, Any] = {
        "project_id": project_id,
        "project_name": name,
        "status": "skipped",
        "reason": "",
        "diagnostics_status": "skipped",
        "repair_status": "skipped",
        "queued_job": {},
        "repair_label": "",
        "repair_summary": "",
    }
    try:
        root = resolve_project_root(project)
    except FileNotFoundError:
        row["reason"] = "project_root_missing"
        return row

    meta_path = root / "metadata.json"
    meta = load_json(meta_path) if meta_path.exists() else dict(project)
    analysis_path = root / "artifacts" / "analysis.json"
    analysis = load_json(analysis_path) if analysis_path.exists() else {}

    if refresh_diagnostics and isinstance(analysis, dict) and analysis:
        try:
            settings = get_llm_settings()
            strategy = meta.get("workflow_strategy") or settings.get("workflow_strategy")
            refresh_diagnostic_assets(root, meta, analysis, workflow_strategy=strategy, force_attachment=True)
            row["diagnostics_status"] = "success"
        except Exception as exc:
            row["diagnostics_status"] = "failed"
            row["diagnostics_error"] = f"{type(exc).__name__}: {exc}"
    elif refresh_diagnostics:
        row["diagnostics_status"] = "skipped"
        row["diagnostics_error"] = "analysis_missing"

    try:
        artifacts = write_repair_briefing(root, meta)
        repair = build_repair_briefing(root, meta)
        row["repair_status"] = "success"
        row["repair_label"] = str(repair.get("label") or "")
        row["repair_summary"] = str(repair.get("summary") or "")
        row["repair_can_resume"] = bool(repair.get("can_resume"))
        row["repair_artifacts"] = artifacts
    except Exception as exc:
        row["repair_status"] = "failed"
        row["repair_error"] = f"{type(exc).__name__}: {exc}"

    can_resume = bool(row.get("repair_can_resume")) or meta.get("auto_workflow_status") in {
        "failed",
        "cancelled",
        "completed_with_warnings",
        "interrupted",
    }
    save_json(meta_path, meta)
    if queue_resumes and can_resume and analysis_path.exists():
        try:
            job = start_auto_workflow_job(project_id, root, resume=True)
            row["status"] = "queued"
            row["queued_job"] = job
            row["reason"] = "resume_queued"
        except Exception as exc:
            row["status"] = "failed"
            row["reason"] = f"{type(exc).__name__}: {exc}"
    elif queue_resumes and not analysis_path.exists():
        row["status"] = "skipped"
        row["reason"] = "analysis_missing"
    elif queue_resumes and not can_resume:
        row["status"] = "skipped"
        row["reason"] = "not_resume_ready"
    else:
        row["status"] = "diagnosed" if row.get("repair_status") == "success" or row.get("diagnostics_status") == "success" else "skipped"
        row["reason"] = "diagnostics_only"

    return row


def resolve_project_root(project: dict[str, Any]) -> Path:
    root_value = project.get("root")
    if root_value:
        root = Path(str(root_value))
        if root.exists():
            return root
    return project_root(str(project.get("id") or ""))


def campaign_rank(project: dict[str, Any]) -> tuple[int, int, str]:
    score = 0
    if project.get("auto_workflow_status") in {"failed", "cancelled", "completed_with_warnings", "interrupted"}:
        score += 40
    if project.get("computed_solution_status") == "failed":
        score += 35
    if project.get("last_failure_diagnosis"):
        score += 28
    if project.get("repair_center_status") in {"action_required", "repairable"}:
        score += 24
    if project.get("delivery_readiness_status") in {"blocked", "failed", "needs_work"}:
        score += 12
    return score, safe_int(project.get("delivery_readiness_score")), str(project.get("created_at") or "")


def campaign_summary(counts: dict[str, int], api_configured: bool, queue_resumes: bool) -> str:
    parts = [
        f"已处理 {counts.get('requested', 0)} 个修复候选项目",
        f"已刷新 {counts.get('diagnosed', 0)} 个诊断",
        f"已重建 {counts.get('briefed', 0)} 个修复简报",
    ]
    if queue_resumes:
        parts.append(f"{counts.get('queued', 0)} 个继续生成任务已入队" if api_configured else "未配置 API 密钥，已跳过继续生成入队")
    if counts.get("failed"):
        parts.append(f"{counts.get('failed', 0)} 个失败")
    return "；".join(parts) + "。"


def record_campaign(campaign: dict[str, Any], limit: int = 80) -> None:
    row = normalize_campaign(campaign)
    if not row.get("id"):
        return
    with _LOCK:
        ledger = load_ledger()
        rows = [row]
        rows.extend(item for item in ledger.get("campaigns", []) if isinstance(item, dict) and item.get("id") != row.get("id"))
        save_json(
            _LEDGER_PATH,
            {
                "updated_at": now_iso(),
                "campaigns": rows[: max(1, min(300, int(limit or 80)))],
            },
        )


def load_ledger() -> dict[str, Any]:
    if not _LEDGER_PATH.exists():
        return {"updated_at": "", "campaigns": []}
    try:
        payload = load_json(_LEDGER_PATH)
    except Exception:
        return {"updated_at": "", "campaigns": []}
    rows = payload.get("campaigns") if isinstance(payload, dict) else []
    if not isinstance(rows, list):
        rows = []
    normalized = [normalize_campaign(row) for row in rows if isinstance(row, dict)]
    normalized.sort(key=lambda item: str(item.get("generated_at") or ""), reverse=True)
    return {
        "updated_at": str(payload.get("updated_at") or "") if isinstance(payload, dict) else "",
        "campaigns": normalized,
    }


def normalize_campaign(row: dict[str, Any]) -> dict[str, Any]:
    projects = row.get("projects") if isinstance(row.get("projects"), list) else []
    return {
        "id": str(row.get("id") or ""),
        "stage": str(row.get("stage") or "repair_campaign"),
        "generated_at": str(row.get("generated_at") or ""),
        "queue_resumes_requested": bool(row.get("queue_resumes_requested")),
        "queue_resumes_enabled": bool(row.get("queue_resumes_enabled")),
        "refresh_diagnostics": bool(row.get("refresh_diagnostics")),
        "api_configured": bool(row.get("api_configured")),
        "candidate_count": safe_int(row.get("candidate_count")),
        "requested": safe_int(row.get("requested")),
        "diagnosed": safe_int(row.get("diagnosed")),
        "briefed": safe_int(row.get("briefed")),
        "queued": safe_int(row.get("queued")),
        "skipped": safe_int(row.get("skipped")),
        "failed": safe_int(row.get("failed")),
        "summary": str(row.get("summary") or ""),
        "projects": projects[:30],
    }


def safe_int(value: Any) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")
