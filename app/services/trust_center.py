from __future__ import annotations

from datetime import datetime
from statistics import mean
from typing import Any

from app.services.growth_metrics import is_deliverable, percent


ACTIVE_JOB_STATUSES = {"queued", "running"}
FAILED_JOB_STATUSES = {"failed", "interrupted", "requires_api_key", "cancelled"}


def build_trust_center(
    projects: list[dict[str, Any]],
    auto_jobs: dict[str, Any] | None = None,
    delivery_batch_jobs: dict[str, Any] | None = None,
    delivery_batches: dict[str, Any] | None = None,
) -> dict[str, Any]:
    project_rows = [project for project in projects if isinstance(project, dict) and project.get("id")]
    auto_snapshot = auto_jobs if isinstance(auto_jobs, dict) else {}
    delivery_job_snapshot = delivery_batch_jobs if isinstance(delivery_batch_jobs, dict) else {}
    delivery_batch_snapshot = delivery_batches if isinstance(delivery_batches, dict) else {}

    total = len(project_rows)
    analyzed = [project for project in project_rows if project.get("analysis_available") or project.get("status") == "analyzed"]
    deliverable = [project for project in project_rows if is_deliverable(project)]
    packages = [project for project in project_rows if has_package(project)]
    hashed_packages = [project for project in packages if has_package_hash(project)]
    failed_projects = [project for project in project_rows if project_failed(project)]
    repair_backlog = [project for project in project_rows if needs_repair(project)]
    scores = [float(project.get("delivery_readiness_score")) for project in project_rows if is_number(project.get("delivery_readiness_score"))]
    auto_jobs_rows = [job for job in auto_snapshot.get("jobs", []) if isinstance(job, dict)]
    delivery_jobs_rows = [job for job in delivery_job_snapshot.get("jobs", []) if isinstance(job, dict)]
    active_jobs = int(auto_snapshot.get("active_count") or 0) + int(delivery_job_snapshot.get("active_count") or 0)
    queued_jobs = int(auto_snapshot.get("queued_count") or 0) + int(delivery_job_snapshot.get("queued_count") or 0)
    failed_jobs = [job for job in auto_jobs_rows + delivery_jobs_rows if str(job.get("status") or "") in FAILED_JOB_STATUSES]
    latest_batch = latest_delivery_batch(delivery_batch_snapshot)

    score = trust_score(
        total=total,
        deliverable=len(deliverable),
        packages=len(packages),
        hashed_packages=len(hashed_packages),
        failed_projects=len(failed_projects),
        repair_backlog=len(repair_backlog),
        active_jobs=active_jobs,
        queued_jobs=queued_jobs,
        failed_jobs=len(failed_jobs),
        average_score=round(mean(scores), 1) if scores else None,
    )
    status, label = trust_status(score, total, len(repair_backlog), len(failed_projects), len(packages), len(hashed_packages), queued_jobs)
    return {
        "generated_at": now_iso(),
        "status": status,
        "label": label,
        "score": score,
        "summary": trust_summary(label, score, total, len(deliverable), len(packages), len(repair_backlog), queued_jobs),
        "project_count": total,
        "analyzed_count": len(analyzed),
        "deliverable_count": len(deliverable),
        "package_count": len(packages),
        "hashed_package_count": len(hashed_packages),
        "failed_project_count": len(failed_projects),
        "repair_backlog_count": len(repair_backlog),
        "active_job_count": active_jobs,
        "queued_job_count": queued_jobs,
        "failed_job_count": len(failed_jobs),
        "average_delivery_score": round(mean(scores), 1) if scores else None,
        "latest_delivery_batch": latest_batch,
        "sla": trust_sla_rows(total, len(deliverable), len(packages), len(hashed_packages), len(failed_projects), len(repair_backlog), active_jobs, queued_jobs, auto_snapshot),
        "metrics": trust_metric_cards(total, len(deliverable), len(packages), len(hashed_packages), len(failed_projects), len(repair_backlog), active_jobs, queued_jobs, len(failed_jobs)),
        "evidence": trust_evidence(project_rows, latest_batch, auto_snapshot, delivery_job_snapshot),
        "incidents": trust_incidents(failed_projects, repair_backlog, failed_jobs),
        "actions": trust_actions(total, len(deliverable), len(packages), len(hashed_packages), len(failed_projects), len(repair_backlog), queued_jobs, active_jobs),
    }


def trust_score(
    *,
    total: int,
    deliverable: int,
    packages: int,
    hashed_packages: int,
    failed_projects: int,
    repair_backlog: int,
    active_jobs: int,
    queued_jobs: int,
    failed_jobs: int,
    average_score: float | None,
) -> int:
    if total <= 0:
        return 0
    score = 42
    score += min(16, deliverable * 4)
    score += min(18, packages * 5)
    score += min(14, hashed_packages * 4)
    if average_score is not None:
        score += max(0, min(10, int(round((average_score - 70) / 30 * 10))))
    if active_jobs:
        score += min(4, active_jobs)
    score -= min(30, failed_projects * 7 + repair_backlog * 8)
    score -= min(18, failed_jobs * 5)
    score -= min(12, queued_jobs * 3)
    if packages and hashed_packages < packages:
        score -= min(14, (packages - hashed_packages) * 5)
    return max(0, min(100, int(score)))


def trust_status(
    score: int,
    total: int,
    repair_backlog: int,
    failed_projects: int,
    packages: int,
    hashed_packages: int,
    queued_jobs: int,
) -> tuple[str, str]:
    if not total:
        return "empty", "暂无信任证据"
    if repair_backlog or failed_projects:
        return "at_risk" if score >= 45 else "blocked", "信任存在风险" if score >= 45 else "已阻断"
    if queued_jobs > 2:
        return "watch", "队列观察"
    if packages and hashed_packages >= packages and score >= 88:
        return "trusted", "交付可信"
    if score >= 70:
        return "watch", "运营观察"
    return "at_risk", "信任存在风险"


def trust_summary(label: str, score: int, total: int, deliverable: int, packages: int, repair_backlog: int, queued_jobs: int) -> str:
    parts = [f"{label}：{total} 个项目的信任评分为 {score}/100"]
    if deliverable:
        parts.append(f"{deliverable} 个通过交付门禁")
    if packages:
        parts.append(f"{packages} 个可审计交付包")
    if repair_backlog:
        parts.append(f"{repair_backlog} 个修复项")
    if queued_jobs:
        parts.append(f"{queued_jobs} 个任务排队")
    return "；".join(parts) + "。"


def trust_sla_rows(
    total: int,
    deliverable: int,
    packages: int,
    hashed_packages: int,
    failed_projects: int,
    repair_backlog: int,
    active_jobs: int,
    queued_jobs: int,
    auto_jobs: dict[str, Any],
) -> list[dict[str, Any]]:
    throughput = auto_jobs.get("throughput", {}) if isinstance(auto_jobs.get("throughput"), dict) else {}
    success_rate = throughput.get("recent_success_rate")
    return [
        sla_row("delivery_gate", "交付门禁覆盖", percent(deliverable, total), 70, f"{deliverable}/{total} 个项目可提交"),
        sla_row("package_hash", "交付包哈希覆盖", percent(hashed_packages, packages), 100, f"{hashed_packages}/{packages} 个交付包带 SHA256 证明"),
        sla_row("repair_backlog", "修复积压清理", 100 if not repair_backlog and not failed_projects else 0, 100, f"{repair_backlog} 个修复项，{failed_projects} 个失败项目"),
        sla_row("queue_health", "队列压力", 100 if queued_jobs == 0 else max(0, 100 - queued_jobs * 25), 75, f"{active_jobs} 个活跃任务，{queued_jobs} 个排队任务"),
        sla_row("automation_success", "自动化可靠性", int(success_rate) if is_number(success_rate) else None, 70, "最近完成的后台工作流"),
    ]


def sla_row(row_id: str, label: str, value: int | None, target: int, detail: str) -> dict[str, Any]:
    if value is None:
        status = "pending"
    elif value >= target:
        status = "success"
    elif value >= max(0, target - 25):
        status = "warning"
    else:
        status = "failed"
    return {
        "id": row_id,
        "label": label,
        "value": value,
        "target": target,
        "status": status,
        "detail": detail,
    }


def trust_metric_cards(
    total: int,
    deliverable: int,
    packages: int,
    hashed_packages: int,
    failed_projects: int,
    repair_backlog: int,
    active_jobs: int,
    queued_jobs: int,
    failed_jobs: int,
) -> list[dict[str, Any]]:
    return [
        {
            "id": "delivery_gate",
            "label": "交付门禁",
            "value": deliverable,
            "detail": f"项目池覆盖率 {percent(deliverable, total)}%",
            "status": "success" if deliverable else "warning" if total else "pending",
        },
        {
            "id": "package_hashes",
            "label": "交付包哈希",
            "value": hashed_packages,
            "detail": f"哈希覆盖率 {percent(hashed_packages, packages)}%",
            "status": "success" if packages and hashed_packages >= packages else "warning" if packages else "pending",
        },
        {
            "id": "repair_backlog",
            "label": "修复积压",
            "value": repair_backlog,
            "detail": f"{failed_projects} 个失败项目",
            "status": "success" if not repair_backlog and not failed_projects else "failed",
        },
        {
            "id": "queue_health",
            "label": "队列健康",
            "value": active_jobs,
            "detail": f"{queued_jobs} 个排队任务，{failed_jobs} 个失败任务已跟踪",
            "status": "success" if not queued_jobs and not failed_jobs else "warning" if queued_jobs <= 2 else "failed",
        },
    ]


def trust_evidence(
    projects: list[dict[str, Any]],
    latest_batch: dict[str, Any],
    auto_jobs: dict[str, Any],
    delivery_batch_jobs: dict[str, Any],
) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    packages = [project for project in projects if has_package(project)]
    hashed = [project for project in packages if has_package_hash(project)]
    if hashed:
        evidence.append(
            {
                "id": "package_hashes",
                "label": "可审计交付包哈希",
                "detail": f"{len(hashed)} 个交付包包含 SHA256 指纹。",
                "status": "success",
            }
        )
    if latest_batch:
        evidence.append(
            {
                "id": "latest_batch",
                "label": "最新批量打包",
                "detail": latest_batch.get("summary") or f"{latest_batch.get('packaged_count', 0)} 个已生成 / {latest_batch.get('failed_count', 0)} 个失败。",
                "status": "failed" if int(latest_batch.get("failed_count") or 0) else "success" if int(latest_batch.get("packaged_count") or 0) else "warning",
            }
        )
    throughput = auto_jobs.get("throughput", {}) if isinstance(auto_jobs.get("throughput"), dict) else {}
    if throughput:
        evidence.append(
            {
                "id": "workflow_throughput",
                "label": "工作流吞吐",
                "detail": throughput.get("summary") or "",
                "status": throughput_status_tone(throughput.get("status")),
            }
        )
    delivery_active = int(delivery_batch_jobs.get("active_count") or 0)
    if delivery_active:
        evidence.append(
            {
                "id": "delivery_jobs",
                "label": "交付任务活跃",
                "detail": f"{delivery_active} 个交付打包任务正在排队或运行。",
                "status": "warning",
            }
        )
    return evidence[:6]


def trust_incidents(
    failed_projects: list[dict[str, Any]],
    repair_backlog: list[dict[str, Any]],
    failed_jobs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen_projects: set[str] = set()
    for project in failed_projects + repair_backlog:
        project_id = str(project.get("id") or "")
        if project_id in seen_projects:
            continue
        seen_projects.add(project_id)
        diagnosis = project.get("last_failure_diagnosis", {}) if isinstance(project.get("last_failure_diagnosis"), dict) else {}
        rows.append(
            {
                "id": project_id,
                "kind": "project",
                "label": str(project.get("name") or project_id),
                "detail": str(diagnosis.get("suggested_action") or diagnosis.get("repair_focus") or project.get("auto_workflow_error") or project.get("delivery_readiness_summary") or "需要修复跟进。"),
                "status": "failed",
            }
        )
    for job in failed_jobs[:6]:
        rows.append(
            {
                "id": str(job.get("id") or ""),
                "kind": str(job.get("kind") or "job"),
                "label": str(job.get("label") or job.get("project_name") or job.get("id") or "后台任务"),
                "detail": str(job.get("error") or job.get("summary") or job.get("status") or "失败任务"),
                "status": str(job.get("status") or "failed"),
            }
        )
    return rows[:8]


def trust_actions(
    total: int,
    deliverable: int,
    packages: int,
    hashed_packages: int,
    failed_projects: int,
    repair_backlog: int,
    queued_jobs: int,
    active_jobs: int,
) -> list[dict[str, str]]:
    actions: list[dict[str, str]] = []
    if failed_projects or repair_backlog:
        actions.append(
            {
                "id": "clear_repair_backlog",
                "label": "清理修复积压",
                "detail": "在提交复核前运行诊断并继续失败工作流。",
            }
        )
    if deliverable > packages:
        actions.append(
            {
                "id": "package_deliverables",
                "label": "打包可交付项目",
                "detail": "为每个就绪项目生成带清单和哈希的正式 ZIP 包。",
            }
        )
    if packages and hashed_packages < packages:
        actions.append(
            {
                "id": "refresh_package_hashes",
                "label": "刷新交付包哈希",
                "detail": "重新生成带清单的交付包，确保提交文件可审计。",
            }
        )
    if queued_jobs > 2:
        actions.append(
            {
                "id": "reduce_queue_pressure",
                "label": "降低队列压力",
                "detail": "提交复核前等待活跃任务结束，或提升工作线程容量。",
            }
        )
    if not total:
        actions.append(
            {
                "id": "seed_projects",
                "label": "补充证明项目",
                "detail": "上传样例竞赛并运行工作流，生成信任证据。",
            }
        )
    if not actions and active_jobs:
        actions.append(
            {
                "id": "watch_active_jobs",
                "label": "观察活跃任务",
                "detail": "导出下一份审计包前，确认活跃任务成功完成。",
            }
        )
    if not actions:
        actions.append(
            {
                "id": "export_audit_bundle",
                "label": "导出审计包",
                "detail": "当前信任证据足够干净，可以刷新交付审计包。",
            }
        )
    return actions[:4]


def latest_delivery_batch(snapshot: dict[str, Any]) -> dict[str, Any]:
    latest = snapshot.get("latest")
    if isinstance(latest, dict) and latest.get("id"):
        return latest
    rows = snapshot.get("batches")
    if isinstance(rows, list):
        for row in rows:
            if isinstance(row, dict) and row.get("id"):
                return row
    return {}


def project_failed(project: dict[str, Any]) -> bool:
    return project.get("auto_workflow_status") == "failed" or project.get("computed_solution_status") == "failed"


def needs_repair(project: dict[str, Any]) -> bool:
    if project.get("repair_center_status") in {"action_required", "repairable"}:
        return True
    if project.get("last_failure_diagnosis"):
        return True
    return project_failed(project)


def has_package(project: dict[str, Any]) -> bool:
    artifacts = project.get("artifacts", {}) if isinstance(project.get("artifacts"), dict) else {}
    return bool(project.get("delivery_package_status") == "success" or artifacts.get("delivery_package"))


def has_package_hash(project: dict[str, Any]) -> bool:
    sha = str(project.get("delivery_package_sha256") or "")
    return len(sha) >= 12


def is_number(value: Any) -> bool:
    try:
        float(value)
        return True
    except (TypeError, ValueError):
        return False


def throughput_status_tone(status: Any) -> str:
    if status in {"healthy", "idle"}:
        return "success"
    if status in {"busy"}:
        return "warning"
    if status in {"saturated"}:
        return "failed"
    return "pending"


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")
