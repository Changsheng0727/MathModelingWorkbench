from __future__ import annotations

import csv
import io
import threading
import uuid
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

from app.config import SETTINGS_ROOT
from app.services.delivery_package import format_bytes, sha256_file
from app.services.growth_metrics import is_deliverable
from app.services.store import load_json, save_json
from app.services.trust_center import build_trust_center, has_package, has_package_hash, needs_repair, project_failed


TRUST_EXPORT_ROOT = SETTINGS_ROOT / "trust_exports"
_LEDGER_PATH = SETTINGS_ROOT / "trust_audit_exports.json"
_LOCK = threading.RLock()


def build_trust_report_export(
    projects: list[dict[str, Any]],
    auto_jobs: dict[str, Any] | None = None,
    delivery_batch_jobs: dict[str, Any] | None = None,
    delivery_batches: dict[str, Any] | None = None,
    *,
    project_limit: int = 100,
) -> dict[str, Any]:
    TRUST_EXPORT_ROOT.mkdir(parents=True, exist_ok=True)
    generated_at = now_iso()
    export_id = f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"
    project_rows = [project for project in projects if isinstance(project, dict) and project.get("id")]
    trust = build_trust_center(project_rows, auto_jobs, delivery_batch_jobs, delivery_batches)
    audit_projects = select_audit_projects(project_rows, project_limit)
    payload = {
        "stage": "trust_audit_export",
        "id": export_id,
        "generated_at": generated_at,
        "product": {
            "name": "ModelArk",
            "positioning": "Math-modeling automation workbench with auditable delivery packages and repair evidence.",
        },
        "trust": trust,
        "projects": audit_projects,
        "attestation": build_attestation(trust),
        "download_notes": [
            "Use this bundle as submission-facing quality evidence before final review, team handoff, or archival.",
            "The audit is a point-in-time snapshot. Re-export after package jobs, repair jobs, or workflow runs finish.",
            "Project rows are risk-sorted so repair backlog, failed jobs, missing hashes, and package gaps surface first.",
        ],
    }

    base_name = f"modelark_trust_audit_{export_id}"
    json_path = TRUST_EXPORT_ROOT / f"{base_name}.json"
    markdown_path = TRUST_EXPORT_ROOT / f"{base_name}.md"
    csv_path = TRUST_EXPORT_ROOT / f"{base_name}.csv"
    zip_path = TRUST_EXPORT_ROOT / f"{base_name}.zip"

    save_json(json_path, payload)
    markdown_path.write_text(render_trust_markdown(payload), encoding="utf-8")
    csv_path.write_text(render_project_csv(audit_projects), encoding="utf-8", newline="")
    write_trust_zip(zip_path, markdown_path, json_path, csv_path)

    export = public_export(
        export_id=export_id,
        generated_at=generated_at,
        zip_path=zip_path,
        markdown_path=markdown_path,
        json_path=json_path,
        csv_path=csv_path,
        payload=payload,
    )
    record_trust_export(export)
    return {
        **export,
        "trust": trust,
        "project_count": len(project_rows),
        "projects": audit_projects[:12],
        "attestation": payload["attestation"],
    }


def list_trust_report_exports(limit: int = 30) -> dict[str, Any]:
    limit = max(1, min(100, int(limit or 30)))
    with _LOCK:
        ledger = load_trust_ledger()
        exports = ledger.get("exports", [])
        rows = [normalize_export(row) for row in exports[:limit] if isinstance(row, dict)]
        return {
            "generated_at": now_iso(),
            "ledger_path": str(_LEDGER_PATH),
            "total_tracked": len(exports),
            "latest": rows[0] if rows else {},
            "exports": rows,
        }


def resolve_trust_report_file(filename: str) -> Path:
    safe_name = Path(str(filename or "")).name
    allowed_suffixes = {".zip", ".md", ".json", ".csv"}
    if not safe_name.startswith("modelark_trust_audit_") or Path(safe_name).suffix.lower() not in allowed_suffixes:
        raise FileNotFoundError(filename)
    target = (TRUST_EXPORT_ROOT / safe_name).resolve()
    root = TRUST_EXPORT_ROOT.resolve()
    if root not in target.parents and target != root:
        raise FileNotFoundError(filename)
    if not target.exists() or not target.is_file():
        raise FileNotFoundError(filename)
    return target


def select_audit_projects(projects: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    limit = max(1, min(500, int(limit or 100)))
    candidates = [project for project in projects if isinstance(project, dict) and project.get("id")]
    candidates.sort(key=project_audit_rank, reverse=True)
    return [compact_project(project) for project in candidates[:limit]]


def project_audit_rank(project: dict[str, Any]) -> tuple[int, int, int, str]:
    risk = 0
    if project_failed(project):
        risk += 40
    if needs_repair(project):
        risk += 35
    if has_package(project) and not has_package_hash(project):
        risk += 22
    if is_deliverable(project) and not has_package(project):
        risk += 18
    if not is_deliverable(project):
        risk += 8
    queued_hint = str(project.get("auto_workflow_status") or "")
    if queued_hint in {"queued", "running", "cancel_requested"}:
        risk += 6
    score = safe_int(project.get("delivery_readiness_score"))
    return risk, 100 - score, safe_int(project.get("created_at")), str(project.get("id") or "")


def compact_project(project: dict[str, Any]) -> dict[str, Any]:
    artifacts = project.get("artifacts", {}) if isinstance(project.get("artifacts"), dict) else {}
    diagnosis = project.get("last_failure_diagnosis", {}) if isinstance(project.get("last_failure_diagnosis"), dict) else {}
    sha = str(project.get("delivery_package_sha256") or "")
    size = safe_int(project.get("delivery_package_size_bytes"))
    package = has_package(project)
    package_hash = has_package_hash(project)
    return {
        "id": str(project.get("id") or ""),
        "name": str(project.get("name") or project.get("original_name") or project.get("id") or ""),
        "status": str(project.get("status") or ""),
        "analysis_available": bool(project.get("analysis_available") or project.get("status") == "analyzed"),
        "deliverable": bool(is_deliverable(project)),
        "auto_workflow_status": str(project.get("auto_workflow_status") or ""),
        "computed_solution_status": str(project.get("computed_solution_status") or ""),
        "delivery_status": str(project.get("delivery_readiness_status") or ""),
        "delivery_label": str(project.get("delivery_readiness_label") or ""),
        "delivery_score": safe_int(project.get("delivery_readiness_score")),
        "can_submit": bool(project.get("delivery_readiness_can_submit")),
        "package_status": "success" if package else str(project.get("delivery_package_status") or ""),
        "package_present": package,
        "package_hash_present": package_hash,
        "package_sha256": sha,
        "package_sha256_short": sha[:12] if sha else "",
        "package_size_bytes": size,
        "package_size": format_bytes(size) if size else "",
        "package_manifest": str(artifacts.get("delivery_package_manifest") or ""),
        "needs_repair": bool(needs_repair(project)),
        "repair_status": str(project.get("repair_center_status") or ""),
        "repair_summary": str(project.get("repair_center_summary") or ""),
        "failure_category": str(diagnosis.get("category") or ""),
        "failure_label": str(diagnosis.get("label") or ""),
        "suggested_action": str(diagnosis.get("suggested_action") or diagnosis.get("repair_focus") or ""),
    }


def build_attestation(trust: dict[str, Any]) -> list[str]:
    return [
        f"Delivery quality status: {trust.get('label') or trust.get('status') or '-'} at {trust.get('score', 0)}/100.",
        f"Delivery gate coverage: {trust.get('deliverable_count', 0)}/{trust.get('project_count', 0)} projects.",
        f"Package hash coverage: {trust.get('hashed_package_count', 0)}/{trust.get('package_count', 0)} packages.",
        f"Repair backlog: {trust.get('repair_backlog_count', 0)} items; failed projects: {trust.get('failed_project_count', 0)}.",
        f"Queue pressure: {trust.get('active_job_count', 0)} active jobs and {trust.get('queued_job_count', 0)} queued jobs.",
    ]


def render_trust_markdown(payload: dict[str, Any]) -> str:
    trust = payload.get("trust", {}) if isinstance(payload.get("trust"), dict) else {}
    projects = payload.get("projects", []) if isinstance(payload.get("projects"), list) else []
    lines = [
        "# ModelArk Delivery Quality Export",
        "",
        f"- Generated at: {payload.get('generated_at', '-')}",
        f"- Delivery quality status: {trust.get('label') or trust.get('status') or '-'}",
        f"- Delivery quality score: {trust.get('score', 0)}/100",
        f"- Projects: {trust.get('project_count', 0)} total, {trust.get('deliverable_count', 0)} deliverable, {trust.get('package_count', 0)} packaged",
        f"- Package hash coverage: {trust.get('hashed_package_count', 0)}/{trust.get('package_count', 0)}",
        "",
        "## Executive Summary",
        "",
        str(trust.get("summary") or "No delivery quality summary is available yet."),
        "",
        "## Attestation",
        "",
    ]
    for item in payload.get("attestation", []) or []:
        lines.append(f"- {item}")
    lines.extend(["", "## SLA Snapshot", "", "| SLA | Value | Target | Status | Detail |", "| --- | ---: | ---: | --- | --- |"])
    for row in trust.get("sla", []) or []:
        if isinstance(row, dict):
            value = row.get("value")
            value_text = "-" if value is None else f"{value}%"
            lines.append(
                "| {label} | {value} | {target}% | {status} | {detail} |".format(
                    label=markdown_cell(row.get("label") or row.get("id") or "-"),
                    value=markdown_cell(value_text),
                    target=markdown_cell(row.get("target") or "-"),
                    status=markdown_cell(row.get("status") or "-"),
                    detail=markdown_cell(row.get("detail") or ""),
                )
            )
    lines.extend(["", "## Evidence", ""])
    append_rows(lines, trust.get("evidence", []) if isinstance(trust.get("evidence"), list) else [], "No evidence has been captured yet.")
    lines.extend(["", "## Incidents", ""])
    append_rows(lines, trust.get("incidents", []) if isinstance(trust.get("incidents"), list) else [], "No active incidents.")
    lines.extend(["", "## Recommended Actions", ""])
    append_rows(lines, trust.get("actions", []) if isinstance(trust.get("actions"), list) else [], "No delivery quality actions are required.")
    lines.extend(
        [
            "",
            "## Project Audit Index",
            "",
            "| Project | Deliverable | Package | Hash | Repair | Score | Suggested action |",
            "| --- | --- | --- | --- | --- | ---: | --- |",
        ]
    )
    for project in projects:
        lines.append(
            "| {name} | {deliverable} | {package} | {hash} | {repair} | {score} | {action} |".format(
                name=markdown_cell(project.get("name") or project.get("id") or "-"),
                deliverable="yes" if project.get("deliverable") else "no",
                package="yes" if project.get("package_present") else "no",
                hash=markdown_cell(project.get("package_sha256_short") or "-"),
                repair="yes" if project.get("needs_repair") else "no",
                score=project.get("delivery_score") or 0,
                action=markdown_cell(project.get("suggested_action") or project.get("repair_summary") or "-"),
            )
        )
    return "\n".join(lines) + "\n"


def append_rows(lines: list[str], rows: list[Any], empty_text: str) -> None:
    if not rows:
        lines.append(f"- {empty_text}")
        return
    for row in rows:
        if isinstance(row, dict):
            label = row.get("label") or row.get("id") or "Item"
            detail = row.get("detail") or ""
            status = row.get("status") or ""
            lines.append(f"- {label}: {detail} ({status})")


def render_project_csv(projects: list[dict[str, Any]]) -> str:
    output = io.StringIO()
    fieldnames = [
        "id",
        "name",
        "deliverable",
        "delivery_score",
        "delivery_status",
        "package_present",
        "package_hash_present",
        "package_sha256",
        "needs_repair",
        "repair_status",
        "failure_category",
        "suggested_action",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for project in projects:
        writer.writerow({key: project.get(key, "") for key in fieldnames})
    return output.getvalue()


def write_trust_zip(zip_path: Path, markdown_path: Path, json_path: Path, csv_path: Path) -> None:
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "README.md",
            "\n".join(
                [
                    "# ModelArk Delivery Quality Bundle",
                    "",
                    "This bundle contains a submission-facing delivery quality, SLA, incident, and package-hash snapshot.",
                    "",
                    "- `trust_audit.md`: readable delivery quality report",
                    "- `trust_audit.json`: structured delivery quality metrics, SLA rows, incidents, actions, and project audit rows",
                    "- `project_audit.csv`: spreadsheet-friendly project evidence index",
                    "",
                ]
            ),
        )
        archive.write(markdown_path, "trust_audit.md")
        archive.write(json_path, "trust_audit.json")
        archive.write(csv_path, "project_audit.csv")


def public_export(
    *,
    export_id: str,
    generated_at: str,
    zip_path: Path,
    markdown_path: Path,
    json_path: Path,
    csv_path: Path,
    payload: dict[str, Any],
) -> dict[str, Any]:
    trust = payload.get("trust", {}) if isinstance(payload.get("trust"), dict) else {}
    projects = payload.get("projects", []) if isinstance(payload.get("projects"), list) else []
    return {
        "id": export_id,
        "stage": "trust_audit_export",
        "generated_at": generated_at,
        "filename": zip_path.name,
        "markdown_filename": markdown_path.name,
        "json_filename": json_path.name,
        "csv_filename": csv_path.name,
        "size_bytes": zip_path.stat().st_size,
        "size": format_bytes(zip_path.stat().st_size),
        "sha256": sha256_file(zip_path),
        "trust_status": str(trust.get("status") or ""),
        "trust_label": str(trust.get("label") or ""),
        "trust_score": safe_int(trust.get("score")),
        "project_count": safe_int(trust.get("project_count")),
        "incident_count": len(trust.get("incidents", []) or []),
        "action_count": len(trust.get("actions", []) or []),
        "audit_project_count": len(projects),
        "summary": str(trust.get("summary") or ""),
        "download_url": f"/api/product/trust/export/download/{quote(zip_path.name, safe='')}",
        "markdown_url": f"/api/product/trust/export/download/{quote(markdown_path.name, safe='')}",
        "json_url": f"/api/product/trust/export/download/{quote(json_path.name, safe='')}",
        "csv_url": f"/api/product/trust/export/download/{quote(csv_path.name, safe='')}",
    }


def record_trust_export(export: dict[str, Any], limit: int = 80) -> None:
    row = normalize_export(export)
    if not row.get("id"):
        return
    with _LOCK:
        ledger = load_trust_ledger()
        existing = ledger.get("exports", [])
        rows = [row]
        rows.extend(item for item in existing if isinstance(item, dict) and item.get("id") != row.get("id"))
        payload = {
            "updated_at": now_iso(),
            "exports": rows[: max(1, min(300, int(limit or 80)))],
        }
        try:
            save_json(_LEDGER_PATH, payload)
        except Exception:
            pass


def load_trust_ledger() -> dict[str, Any]:
    if not _LEDGER_PATH.exists():
        return {"updated_at": "", "exports": []}
    try:
        payload = load_json(_LEDGER_PATH)
    except Exception:
        return {"updated_at": "", "exports": []}
    rows = payload.get("exports") if isinstance(payload, dict) else []
    if not isinstance(rows, list):
        rows = []
    normalized = [normalize_export(row) for row in rows if isinstance(row, dict)]
    normalized.sort(key=lambda item: str(item.get("generated_at") or ""), reverse=True)
    return {
        "updated_at": str(payload.get("updated_at") or "") if isinstance(payload, dict) else "",
        "exports": normalized,
    }


def normalize_export(row: dict[str, Any]) -> dict[str, Any]:
    filename = Path(str(row.get("filename") or "")).name
    markdown_filename = Path(str(row.get("markdown_filename") or "")).name
    json_filename = Path(str(row.get("json_filename") or "")).name
    csv_filename = Path(str(row.get("csv_filename") or "")).name
    return {
        "id": str(row.get("id") or ""),
        "stage": str(row.get("stage") or "trust_audit_export"),
        "generated_at": str(row.get("generated_at") or ""),
        "filename": filename,
        "markdown_filename": markdown_filename,
        "json_filename": json_filename,
        "csv_filename": csv_filename,
        "size_bytes": safe_int(row.get("size_bytes")),
        "size": str(row.get("size") or format_bytes(row.get("size_bytes") or 0)),
        "sha256": str(row.get("sha256") or ""),
        "trust_status": str(row.get("trust_status") or ""),
        "trust_label": str(row.get("trust_label") or ""),
        "trust_score": safe_int(row.get("trust_score")),
        "project_count": safe_int(row.get("project_count")),
        "incident_count": safe_int(row.get("incident_count")),
        "action_count": safe_int(row.get("action_count")),
        "audit_project_count": safe_int(row.get("audit_project_count")),
        "summary": str(row.get("summary") or ""),
        "download_url": f"/api/product/trust/export/download/{quote(filename, safe='')}" if filename else "",
        "markdown_url": f"/api/product/trust/export/download/{quote(markdown_filename, safe='')}" if markdown_filename else "",
        "json_url": f"/api/product/trust/export/download/{quote(json_filename, safe='')}" if json_filename else "",
        "csv_url": f"/api/product/trust/export/download/{quote(csv_filename, safe='')}" if csv_filename else "",
    }


def markdown_cell(value: Any) -> str:
    return str(value or "").replace("|", "\\|").replace("\n", " ")


def safe_int(value: Any) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")
