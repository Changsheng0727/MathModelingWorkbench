from __future__ import annotations

from datetime import datetime
from statistics import mean
from typing import Any

from app.services.action_catalog import enrich_action


def build_growth_metrics(
    projects: list[dict[str, Any]],
    auto_jobs: dict[str, Any] | None = None,
    delivery_batches: dict[str, Any] | None = None,
    delivery_batch_jobs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    jobs_snapshot = auto_jobs if isinstance(auto_jobs, dict) else {}
    delivery_batch_snapshot = delivery_batches if isinstance(delivery_batches, dict) else {}
    delivery_job_snapshot = delivery_batch_jobs if isinstance(delivery_batch_jobs, dict) else {}
    latest_delivery_batch = latest_batch_run(delivery_batch_snapshot)
    active_delivery_batch_jobs = int(delivery_job_snapshot.get("active_count") or 0)
    projects = [project for project in projects if isinstance(project, dict)]
    total = len(projects)
    analyzed = [project for project in projects if project.get("analysis_available") or project.get("status") == "analyzed"]
    auto_started = [project for project in projects if project.get("auto_workflow_status")]
    auto_success = [
        project
        for project in projects
        if project.get("auto_workflow_status") in {"success", "completed_with_warnings"}
        or project.get("computed_solution_status") == "success"
    ]
    deliverable = [project for project in projects if is_deliverable(project)]
    packages = [project for project in projects if project.get("delivery_package_status") == "success" or artifact_exists(project, "delivery_package")]
    failed = [project for project in projects if project.get("auto_workflow_status") == "failed" or project.get("computed_solution_status") == "failed"]
    needs_repair = [project for project in projects if project.get("repair_center_status") in {"action_required", "repairable"}]
    scores = [float(project.get("delivery_readiness_score")) for project in projects if is_number(project.get("delivery_readiness_score"))]

    package_rate = percent(len(packages), total)
    delivery_rate = percent(len(deliverable), total)
    activation_rate = percent(len(analyzed), total)
    automation_success_rate = percent(len(auto_success), len(auto_started)) if auto_started else None
    avg_score = round(mean(scores), 1) if scores else None
    hours_saved = estimate_hours_saved(len(analyzed), len(auto_success), len(packages))
    status, label = growth_status(total, len(deliverable), len(packages), jobs_snapshot)
    summary = growth_summary(label, total, len(deliverable), len(packages), hours_saved, jobs_snapshot)
    workflow = workflow_readiness(
        total=total,
        analyzed=len(analyzed),
        auto_success=len(auto_success),
        deliverable=len(deliverable),
        packages=len(packages),
        failed=len(failed),
        needs_repair=len(needs_repair),
        hours_saved=hours_saved,
        automation_success_rate=automation_success_rate,
        jobs_snapshot=jobs_snapshot,
        active_delivery_batch_jobs=active_delivery_batch_jobs,
    )

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "status": status,
        "label": label,
        "summary": summary,
        "project_count": total,
        "analyzed_count": len(analyzed),
        "auto_started_count": len(auto_started),
        "auto_success_count": len(auto_success),
        "deliverable_count": len(deliverable),
        "delivery_package_count": len(packages),
        "failed_count": len(failed),
        "needs_repair_count": len(needs_repair),
        "average_delivery_score": avg_score,
        "activation_rate": activation_rate,
        "delivery_rate": delivery_rate,
        "package_rate": package_rate,
        "automation_success_rate": automation_success_rate,
        "estimated_hours_saved": hours_saved,
        "delivery_batch": latest_delivery_batch,
        "workflow": workflow,
        "metrics": metric_cards(
            total,
            len(analyzed),
            len(deliverable),
            len(packages),
            avg_score,
            hours_saved,
            jobs_snapshot,
        ),
        "funnel": funnel_rows(total, len(analyzed), len(auto_success), len(deliverable), len(packages)),
        "signals": growth_signals(
            projects,
            jobs_snapshot,
            activation_rate,
            delivery_rate,
            package_rate,
            automation_success_rate,
            len(needs_repair),
            latest_delivery_batch,
            active_delivery_batch_jobs,
        ),
        "recommended_action": enrich_action(
            recommended_action(
                total,
                len(analyzed),
                len(deliverable),
                len(packages),
                jobs_snapshot,
                active_delivery_batch_jobs,
            )
        ),
    }


def metric_cards(
    total: int,
    analyzed: int,
    deliverable: int,
    packages: int,
    avg_score: float | None,
    hours_saved: float,
    jobs_snapshot: dict[str, Any],
) -> list[dict[str, Any]]:
    throughput = jobs_snapshot.get("throughput", {}) if isinstance(jobs_snapshot.get("throughput"), dict) else {}
    active = int(jobs_snapshot.get("active_count") or 0)
    return [
        {
            "id": "project_count",
            "label": "项目资产",
            "value": total,
            "detail": f"{analyzed} 个已分析",
            "status": "success" if analyzed else "pending",
        },
        {
            "id": "deliverable_count",
            "label": "可交付项目",
            "value": deliverable,
            "detail": f"平均交付分 {avg_score}" if avg_score is not None else "等待交付评分",
            "status": "success" if deliverable else "warning" if total else "pending",
        },
        {
            "id": "package_count",
            "label": "正式交付包",
            "value": packages,
            "detail": "带清单与 SHA256",
            "status": "success" if packages else "warning" if deliverable else "pending",
        },
        {
            "id": "hours_saved",
            "label": "估算节省",
            "value": f"{hours_saved:.1f}h",
            "detail": "按分析、自动求解和交付打包折算",
            "status": "success" if hours_saved >= 8 else "warning" if hours_saved else "pending",
        },
        {
            "id": "throughput",
            "label": "任务吞吐",
            "value": active,
            "detail": throughput.get("summary") or "后台任务池待命",
            "status": throughput_status_tone(throughput.get("status")),
        },
    ]


def funnel_rows(total: int, analyzed: int, auto_success: int, deliverable: int, packages: int) -> list[dict[str, Any]]:
    return [
        funnel_row("uploaded", "项目上传", total, total, "进入项目资产池"),
        funnel_row("analyzed", "赛题分析", analyzed, total, "完成题面、附件和选题识别"),
        funnel_row("computed", "自动求解", auto_success, total, "完成代码求解或自动流程"),
        funnel_row("deliverable", "交付就绪", deliverable, total, "论文、结果和审查可提交"),
        funnel_row("packaged", "正式交付包", packages, total, "生成带 manifest 的可下载交付包"),
    ]


def funnel_row(row_id: str, label: str, count: int, total: int, detail: str) -> dict[str, Any]:
    return {
        "id": row_id,
        "label": label,
        "count": count,
        "conversion": percent(count, total),
        "detail": detail,
    }


def growth_signals(
    projects: list[dict[str, Any]],
    jobs_snapshot: dict[str, Any],
    activation_rate: int,
    delivery_rate: int,
    package_rate: int,
    automation_success_rate: int | None,
    needs_repair_count: int,
    latest_delivery_batch: dict[str, Any],
    active_delivery_batch_jobs: int = 0,
) -> list[str]:
    throughput = jobs_snapshot.get("throughput", {}) if isinstance(jobs_snapshot.get("throughput"), dict) else {}
    signals = [
        f"激活率 {activation_rate}%",
        f"交付率 {delivery_rate}%",
        f"打包率 {package_rate}%",
    ]
    if latest_delivery_batch:
        signals.append(delivery_batch_signal(latest_delivery_batch))
    if active_delivery_batch_jobs:
        signals.append(f"交付打包任务活跃：{active_delivery_batch_jobs}")
    if automation_success_rate is not None:
        signals.append(f"自动流程成功率 {automation_success_rate}%")
    if throughput.get("label"):
        signals.append(f"后台任务：{throughput.get('label')}")
    if needs_repair_count:
        signals.append(f"{needs_repair_count} 个项目需要修复跟进")
    if projects:
        latest = max((str(project.get("created_at") or "") for project in projects), default="")
        if latest:
            signals.append(f"最近项目 {latest.replace('T', ' ')[:16]}")
    return signals[:7]


def latest_batch_run(delivery_batches: dict[str, Any]) -> dict[str, Any]:
    latest = delivery_batches.get("latest")
    if isinstance(latest, dict) and latest.get("id"):
        return compact_latest_batch(latest)
    rows = delivery_batches.get("batches")
    if isinstance(rows, list):
        for row in rows:
            if isinstance(row, dict) and row.get("id"):
                return compact_latest_batch(row)
    return {}


def compact_latest_batch(batch: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(batch.get("id") or ""),
        "generated_at": str(batch.get("generated_at") or ""),
        "duration_seconds": int(batch.get("duration_seconds") or 0),
        "force": bool(batch.get("force")),
        "max_workers": int(batch.get("max_workers") or 0),
        "requested_count": int(batch.get("requested_count") or 0),
        "packaged_count": int(batch.get("packaged_count") or 0),
        "skipped_count": int(batch.get("skipped_count") or 0),
        "failed_count": int(batch.get("failed_count") or 0),
        "total_package_bytes": int(batch.get("total_package_bytes") or 0),
        "summary": str(batch.get("summary") or ""),
    }


def delivery_batch_signal(batch: dict[str, Any]) -> str:
    packaged = int(batch.get("packaged_count") or 0)
    skipped = int(batch.get("skipped_count") or 0)
    failed = int(batch.get("failed_count") or 0)
    return f"最近批量打包：{packaged} 生成 / {skipped} 跳过 / {failed} 失败"


def workflow_readiness(
    *,
    total: int,
    analyzed: int,
    auto_success: int,
    deliverable: int,
    packages: int,
    failed: int,
    needs_repair: int,
    hours_saved: float,
    automation_success_rate: int | None,
    jobs_snapshot: dict[str, Any],
    active_delivery_batch_jobs: int,
) -> dict[str, Any]:
    queued = int(jobs_snapshot.get("queued_count") or 0)
    capacity = int(jobs_snapshot.get("capacity") or 0)
    active_jobs = int(jobs_snapshot.get("active_count") or 0) + int(active_delivery_batch_jobs or 0)
    solution_assets = packages + deliverable
    score = workflow_score(
        total,
        analyzed,
        auto_success,
        deliverable,
        packages,
        failed,
        needs_repair,
        automation_success_rate,
        active_jobs,
    )
    stage, label = workflow_stage(score, packages, deliverable, total)
    risks = workflow_risks(total, analyzed, deliverable, packages, failed, needs_repair, automation_success_rate, queued)
    actions = workflow_actions(total, analyzed, deliverable, packages, failed, needs_repair, queued, active_delivery_batch_jobs)
    proof_points = workflow_proof_points(packages, deliverable, auto_success, hours_saved, capacity)
    return {
        "stage": stage,
        "label": label,
        "score": score,
        "summary": workflow_summary(label, score, solution_assets, packages, hours_saved),
        "solution_assets": solution_assets,
        "package_count": packages,
        "deliverable_count": deliverable,
        "estimated_hours_saved": hours_saved,
        "active_jobs": active_jobs,
        "risks": risks,
        "actions": actions,
        "proof_points": proof_points,
    }


def workflow_score(
    total: int,
    analyzed: int,
    auto_success: int,
    deliverable: int,
    packages: int,
    failed: int,
    needs_repair: int,
    automation_success_rate: int | None,
    active_jobs: int,
) -> int:
    score = 0
    score += min(20, total * 2)
    score += min(18, analyzed * 2)
    score += min(18, auto_success * 3)
    score += min(20, deliverable * 6)
    score += min(24, packages * 11)
    if automation_success_rate is not None:
        score += max(0, min(8, int(round((automation_success_rate - 50) / 50 * 8))))
    if active_jobs:
        score += min(4, active_jobs)
    score -= min(16, failed * 4 + needs_repair * 3)
    return max(0, min(100, int(score)))


def workflow_stage(score: int, packages: int, deliverable: int, total: int) -> tuple[str, str]:
    if packages >= 3 and score >= 78:
        return "submission_ready", "提交准备就绪"
    if packages or (deliverable >= 2 and score >= 55):
        return "solution_ready", "求解结果就绪"
    if total:
        return "building", "解题推进中"
    return "empty", "等待赛题"


def workflow_summary(label: str, score: int, solution_assets: int, packages: int, hours_saved: float) -> str:
    return f"{label}：评分 {score}/100，{solution_assets} 个解题资产，{packages} 个正式交付包，估算节省 {hours_saved:.1f} 小时。"


def workflow_risks(
    total: int,
    analyzed: int,
    deliverable: int,
    packages: int,
    failed: int,
    needs_repair: int,
    automation_success_rate: int | None,
    queued: int,
) -> list[str]:
    risks: list[str] = []
    if total < 5:
        risks.append("赛题样本偏少，批量解题稳定性还需要更多项目验证。")
    if analyzed < total:
        risks.append("仍有项目尚未完成赛题分析。")
    if deliverable and packages < deliverable:
        risks.append("可交付项目仍需生成正式交付包。")
    if not packages:
        risks.append("尚无可下载的交付包证明。")
    if failed or needs_repair:
        risks.append("修复积压可能影响结果可靠性。")
    if automation_success_rate is not None and automation_success_rate < 70:
        risks.append("自动求解流程成功率偏低，需要复核失败环节。")
    if queued:
        risks.append("后台队列压力可能拖慢批量求解。")
    return risks[:5]


def workflow_actions(
    total: int,
    analyzed: int,
    deliverable: int,
    packages: int,
    failed: int,
    needs_repair: int,
    queued: int,
    active_delivery_batch_jobs: int,
) -> list[dict[str, str]]:
    actions: list[dict[str, str]] = []
    if active_delivery_batch_jobs:
        actions.append(
            {
                "id": "watch_delivery_jobs",
                "label": "关注交付打包",
                "detail": "批量交付包任务正在运行；请在任务中心确认生成、跳过和失败数量。",
            }
        )
    elif deliverable > packages:
        actions.append(
            {
                "id": "package_deliverables",
                "label": "打包全部可交付项目",
                "detail": "把可提交项目转成带清单和哈希的可审计 ZIP 包，便于提交与复核。",
            }
        )
    if analyzed < total:
        actions.append(
            {
                "id": "complete_analysis",
                "label": "补齐分析覆盖",
                "detail": "每个上传项目都应有分析数据，让漏斗看起来完整且可解释。",
            }
        )
    if failed or needs_repair:
        actions.append(
            {
                "id": "clear_repair_backlog",
                "label": "清理修复积压",
                "detail": "运行诊断并继续失败流程，以增强可靠性证明。",
            }
        )
    if queued:
        actions.append(
            {
                "id": "stabilize_queue",
                "label": "稳定队列压力",
                "detail": "等待活跃任务完成或提升并发容量，保证批量求解稳定。",
            }
        )
    if not actions:
        actions.append(
            {
                "id": "review_solution_outputs",
                "label": "复核解题产出",
                "detail": "重点检查论文结构、图表、代码输出和附件清单。",
            }
        )
    return [enrich_action(action) for action in actions[:4]]


def workflow_proof_points(
    packages: int,
    deliverable: int,
    auto_success: int,
    hours_saved: float,
    capacity: int,
) -> list[str]:
    points = [
        f"{packages} 个可审计交付包",
        f"{deliverable} 个项目通过交付门禁",
        f"{auto_success} 个自动流程成功完成",
        f"估算节省 {hours_saved:.1f} 小时",
    ]
    if capacity:
        points.append(f"{capacity} 个后台流程并发槽")
    return points[:6]


def recommended_action(
    total: int,
    analyzed: int,
    deliverable: int,
    packages: int,
    jobs_snapshot: dict[str, Any],
    active_delivery_batch_jobs: int = 0,
) -> dict[str, str]:
    queued = int(jobs_snapshot.get("queued_count") or 0)
    throughput = jobs_snapshot.get("throughput", {}) if isinstance(jobs_snapshot.get("throughput"), dict) else {}
    if not total:
        return {
            "id": "upload_project",
            "label": "上传赛题项目",
            "detail": "先导入赛题、附件和格式要求，系统才能完成分析、求解与交付检查。",
            "command": "",
        }
    if queued:
        return {
            "id": "scale_workers",
            "label": "观察并发容量",
            "detail": throughput.get("scaling_action") or "后台队列已有任务，关注等待时间和成功率。",
            "command": "",
        }
    if active_delivery_batch_jobs:
        return {
            "id": "observe_delivery_batch",
            "label": "观察交付打包",
            "detail": "交付包批处理已入队或正在运行，请在任务中心关注生成、跳过和失败数量。",
            "command": "",
        }
    if deliverable > packages:
        return {
            "id": "build_packages",
            "label": "生成正式交付包",
            "detail": "已有可交付项目尚未形成可审计交付包，建议优先打包。",
            "command": "batch_delivery_packages",
        }
    if analyzed < total:
        return {
            "id": "analyze_projects",
            "label": "补齐赛题分析",
            "detail": "项目资产需要先完成分析，才能进入批量求解和交付漏斗。",
            "command": "",
        }
    return {
        "id": "batch_more",
        "label": "批量导入更多赛题",
        "detail": "当前漏斗健康，可继续导入更多赛题或扩展对比实验。",
        "command": "",
    }


def growth_status(total: int, deliverable: int, packages: int, jobs_snapshot: dict[str, Any]) -> tuple[str, str]:
    queued = int(jobs_snapshot.get("queued_count") or 0)
    if queued:
        return "operating", "产能运行中"
    if packages:
        return "growth_ready", "解题就绪"
    if deliverable:
        return "delivery_ready", "交付待打包"
    if total:
        return "building", "资产建设中"
    return "empty", "等待项目"


def growth_summary(
    label: str,
    total: int,
    deliverable: int,
    packages: int,
    hours_saved: float,
    jobs_snapshot: dict[str, Any],
) -> str:
    active = int(jobs_snapshot.get("active_count") or 0)
    parts = [f"{label}：{total} 个项目，{deliverable} 个可交付，{packages} 个正式交付包"]
    if active:
        parts.append(f"{active} 个后台任务活跃")
    if hours_saved:
        parts.append(f"估算节省 {hours_saved:.1f} 小时")
    return "；".join(parts)


def estimate_hours_saved(analyzed: int, auto_success: int, packages: int) -> float:
    return round(analyzed * 0.6 + auto_success * 5.5 + packages * 1.2, 1)


def is_deliverable(project: dict[str, Any]) -> bool:
    if project.get("delivery_readiness_can_submit") is True:
        return True
    return project.get("delivery_readiness_status") in {"deliverable", "review"}


def artifact_exists(project: dict[str, Any], key: str) -> bool:
    artifacts = project.get("artifacts", {})
    return isinstance(artifacts, dict) and bool(artifacts.get(key))


def percent(part: int, total: int) -> int:
    if total <= 0:
        return 0
    return int(round(part / total * 100))


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
