from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from app.services.store import load_json, save_json


PERFORMANCE_HEALTH_RELATIVE = "artifacts/performance_health.md"
PERFORMANCE_HEALTH_JSON_RELATIVE = "artifacts/performance_health.json"


def write_performance_health_report(root: Path, meta: dict[str, Any] | None = None) -> dict[str, str]:
    payload = build_performance_health(root, meta)
    save_json(root / PERFORMANCE_HEALTH_JSON_RELATIVE, payload)
    (root / PERFORMANCE_HEALTH_RELATIVE).write_text(render_performance_health_markdown(payload), encoding="utf-8")
    if isinstance(meta, dict):
        scores = payload.get("scores", {}) if isinstance(payload.get("scores"), dict) else {}
        concurrency = payload.get("concurrency", {}) if isinstance(payload.get("concurrency"), dict) else {}
        reliability = payload.get("reliability", {}) if isinstance(payload.get("reliability"), dict) else {}
        meta["performance_health_status"] = payload.get("status", "")
        meta["performance_health_label"] = payload.get("label", "")
        meta["performance_health_summary"] = payload.get("headline", "")
        meta["performance_health_score"] = scores.get("overall")
        meta["performance_health_scores"] = scores
        meta["performance_health_generated_at"] = payload.get("generated_at", "")
        meta["performance_health_metrics"] = {
            "speed": scores.get("speed"),
            "reliability": scores.get("reliability"),
            "attachment_workers": concurrency.get("attachment_workers", 0),
            "planned_task_count": concurrency.get("planned_task_count", 0),
            "parallel_group_count": concurrency.get("parallel_group_count", 0),
            "planned_max_workers": concurrency.get("planned_max_workers", 0),
            "repair_count": reliability.get("repair_count", 0),
        }
        meta.setdefault("artifacts", {}).update(
            {
                "performance_health": PERFORMANCE_HEALTH_RELATIVE,
                "performance_health_json": PERFORMANCE_HEALTH_JSON_RELATIVE,
            }
        )
    return {
        "performance_health": PERFORMANCE_HEALTH_RELATIVE,
        "performance_health_json": PERFORMANCE_HEALTH_JSON_RELATIVE,
    }


def build_performance_health(root: Path, meta: dict[str, Any] | None = None) -> dict[str, Any]:
    metadata = meta if isinstance(meta, dict) else load_json_if_exists(root / "metadata.json")
    attachment = load_json_if_exists(root / "artifacts" / "attachment_profile.json")
    parallel_plan = load_json_if_exists(root / "artifacts" / "parallel_task_plan.json")
    run_status = load_json_if_exists(root / "artifacts" / "computed_solution_status.json")
    repair = load_json_if_exists(root / "artifacts" / "computed_solver_repair.json")
    completeness = load_json_if_exists(root / "artifacts" / "computed_solution_completeness.json")
    workflow = load_json_if_exists(root / "artifacts" / "auto_workflow_report.json")
    manifest = load_json_if_exists(root / "results" / "computed_manifest.json")

    execution_profile = manifest.get("execution_profile", {}) if isinstance(manifest, dict) else {}
    concurrency = run_status.get("concurrency_evidence", {}) if isinstance(run_status, dict) else {}
    if not concurrency and isinstance(execution_profile, dict):
        concurrency = execution_profile.get("concurrency_evidence", {})
    repair_history = repair.get("history", []) if isinstance(repair, dict) and isinstance(repair.get("history"), list) else []
    latest_diagnosis = latest_failure_diagnosis(run_status, completeness, repair, workflow, metadata)
    workflow_steps = workflow.get("steps", []) if isinstance(workflow, dict) and isinstance(workflow.get("steps"), list) else []
    bottlenecks = slowest_steps(workflow_steps)

    speed = {
        "attachment_duration_seconds": attachment.get("duration_seconds") if isinstance(attachment, dict) else None,
        "attachment_worker_count": attachment.get("worker_count") if isinstance(attachment, dict) else None,
        "attachment_file_count": attachment.get("file_count") if isinstance(attachment, dict) else None,
        "planned_task_count": parallel_plan.get("planned_task_count") if isinstance(parallel_plan, dict) else None,
        "parallel_group_count": parallel_plan.get("parallel_group_count") if isinstance(parallel_plan, dict) else None,
        "planned_max_workers": parallel_plan.get("suggested_max_workers") if isinstance(parallel_plan, dict) else None,
        "solver_duration_seconds": run_status.get("duration_seconds") if isinstance(run_status, dict) else execution_profile.get("duration_seconds") if isinstance(execution_profile, dict) else None,
        "workflow_duration_seconds": sum_float(step.get("duration_seconds") for step in workflow_steps if isinstance(step, dict)),
        "bottleneck_steps": bottlenecks,
    }
    concurrency_summary = {
        "attachment_parallel": int(speed.get("attachment_worker_count") or 0) > 1,
        "attachment_workers": speed.get("attachment_worker_count") or 0,
        "parallel_plan_ready": bool(parallel_plan.get("success")) if isinstance(parallel_plan, dict) else False,
        "planned_task_count": parallel_plan.get("planned_task_count") if isinstance(parallel_plan, dict) else 0,
        "parallel_group_count": parallel_plan.get("parallel_group_count") if isinstance(parallel_plan, dict) else 0,
        "planned_max_workers": parallel_plan.get("suggested_max_workers") if isinstance(parallel_plan, dict) else 0,
        "solver_thread_pool": bool(concurrency.get("thread_pool")),
        "solver_dispatch": bool(concurrency.get("dispatch")),
        "solver_max_workers": concurrency.get("max_workers", []),
        "solver_submit_calls": concurrency.get("submit_calls", 0),
        "solver_map_calls": concurrency.get("map_calls", 0),
        "solver_as_completed_calls": concurrency.get("as_completed_calls", 0),
        "strategy": run_status.get("workflow_strategy") if isinstance(run_status, dict) else metadata.get("workflow_strategy", ""),
    }
    reliability = {
        "auto_workflow_status": metadata.get("auto_workflow_status", "") if isinstance(metadata, dict) else "",
        "computed_solution_success": bool(run_status.get("success")) if isinstance(run_status, dict) else False,
        "completeness_success": completeness.get("success") if isinstance(completeness, dict) else None,
        "repair_count": len(repair_history),
        "latest_failure_diagnosis": latest_diagnosis,
        "can_resume": can_resume(metadata, workflow),
    }
    scores = score_health(speed, concurrency_summary, reliability)
    recommendations = build_recommendations(scores, speed, concurrency_summary, reliability)
    status, label = health_status(scores, reliability)
    headline = build_headline(scores, speed, concurrency_summary, reliability)
    return {
        "stage": "performance_health",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "status": status,
        "label": label,
        "headline": headline,
        "scores": scores,
        "speed": speed,
        "concurrency": concurrency_summary,
        "reliability": reliability,
        "recommendations": recommendations,
        "source_artifacts": {
            "attachment_profile": "artifacts/attachment_profile.json" if (root / "artifacts" / "attachment_profile.json").exists() else "",
            "parallel_task_plan": "artifacts/parallel_task_plan.json" if (root / "artifacts" / "parallel_task_plan.json").exists() else "",
            "computed_solution_status": "artifacts/computed_solution_status.json" if (root / "artifacts" / "computed_solution_status.json").exists() else "",
            "computed_solver_repair": "artifacts/computed_solver_repair.json" if (root / "artifacts" / "computed_solver_repair.json").exists() else "",
            "computed_manifest": "results/computed_manifest.json" if (root / "results" / "computed_manifest.json").exists() else "",
            "auto_workflow_report": "artifacts/auto_workflow_report.json" if (root / "artifacts" / "auto_workflow_report.json").exists() else "",
        },
    }


def score_health(speed: dict[str, Any], concurrency: dict[str, Any], reliability: dict[str, Any]) -> dict[str, int]:
    speed_score = 56
    if concurrency.get("attachment_parallel"):
        speed_score += 14
    if concurrency.get("parallel_plan_ready"):
        speed_score += 8
    if concurrency.get("solver_thread_pool") and concurrency.get("solver_dispatch"):
        speed_score += 18
    if safe_float(speed.get("solver_duration_seconds")) and safe_float(speed.get("solver_duration_seconds")) <= 180:
        speed_score += 8
    if safe_float(speed.get("workflow_duration_seconds")) and safe_float(speed.get("workflow_duration_seconds")) > 1200:
        speed_score -= 10

    reliability_score = 58
    if reliability.get("computed_solution_success"):
        reliability_score += 18
    if reliability.get("completeness_success") is True:
        reliability_score += 16
    if reliability.get("latest_failure_diagnosis"):
        reliability_score -= 12
    repair_count = int(reliability.get("repair_count") or 0)
    if repair_count:
        reliability_score += min(8, repair_count * 2)
        reliability_score -= max(0, repair_count - 2) * 4
    if reliability.get("can_resume"):
        reliability_score += 4

    speed_score = clamp_score(speed_score)
    reliability_score = clamp_score(reliability_score)
    overall = clamp_score(round(speed_score * 0.48 + reliability_score * 0.52))
    return {"speed": speed_score, "reliability": reliability_score, "overall": overall}


def build_headline(
    scores: dict[str, int],
    speed: dict[str, Any],
    concurrency: dict[str, Any],
    reliability: dict[str, Any],
) -> str:
    workers = int(concurrency.get("attachment_workers") or 0)
    planned_groups = int(concurrency.get("parallel_group_count") or 0)
    solver_parallel = concurrency.get("solver_thread_pool") and concurrency.get("solver_dispatch")
    repair_count = int(reliability.get("repair_count") or 0)
    solver_time = speed.get("solver_duration_seconds")
    parts = [f"综合 {scores.get('overall', 0)} 分"]
    if workers:
        parts.append(f"附件画像 {workers} 线程")
    if planned_groups:
        parts.append(f"并行计划 {planned_groups} 组")
    if solver_parallel:
        parts.append("求解脚本已启用线程池并发")
    elif concurrency.get("strategy") and isinstance(concurrency.get("strategy"), dict) and concurrency["strategy"].get("requires_parallel"):
        parts.append("极速策略仍需更多脚本并发证据")
    if solver_time:
        parts.append(f"代码求解 {solver_time}s")
    if repair_count:
        parts.append(f"自动修复 {repair_count} 轮")
    return "；".join(parts)


def build_recommendations(
    scores: dict[str, int],
    speed: dict[str, Any],
    concurrency: dict[str, Any],
    reliability: dict[str, Any],
) -> list[str]:
    items: list[str] = []
    if not concurrency.get("attachment_parallel"):
        items.append("附件数量较少或未生成并发画像；上传大型赛题包时建议先生成附件画像以减少字段识别错误。")
    if not concurrency.get("parallel_plan_ready"):
        items.append("尚未生成并行求解任务计划；建议先拆分附件读取、分问题求解和检验导出任务。")
    if not (concurrency.get("solver_thread_pool") and concurrency.get("solver_dispatch")):
        items.append("代码求解脚本缺少线程池派发证据；极速策略下建议并行读取附件、工作表画像和独立子问题。")
    if reliability.get("latest_failure_diagnosis"):
        diagnosis = reliability["latest_failure_diagnosis"]
        action = diagnosis.get("suggested_action") or diagnosis.get("repair_focus") or "点击继续生成执行自动修复。"
        items.append(str(action))
    if reliability.get("completeness_success") is False:
        items.append("完整性门禁未通过；优先补齐每个子问题的结果表、图片、指标和检验证据。")
    if safe_float(speed.get("workflow_duration_seconds")) > 1200:
        items.append("自动流程耗时较长；建议保留附件画像缓存，并将后续可独立阶段拆成并行任务。")
    if not items and scores.get("overall", 0) >= 82:
        items.append("当前速度和可靠性状态良好，可直接继续论文编译、审查和支撑材料打包。")
    return items[:6]


def health_status(scores: dict[str, int], reliability: dict[str, Any]) -> tuple[str, str]:
    if reliability.get("latest_failure_diagnosis") and not reliability.get("computed_solution_success"):
        return "failed", "需修复"
    overall = int(scores.get("overall") or 0)
    if overall >= 82:
        return "success", "健康"
    if overall >= 62:
        return "warning", "可优化"
    return "failed", "需关注"


def render_performance_health_markdown(payload: dict[str, Any]) -> str:
    scores = payload.get("scores", {})
    speed = payload.get("speed", {})
    concurrency = payload.get("concurrency", {})
    reliability = payload.get("reliability", {})
    lines = [
        "# 性能与修复健康报告",
        "",
        f"- 生成时间：{payload.get('generated_at', '-')}",
        f"- 状态：{payload.get('label', '-')}",
        f"- 摘要：{payload.get('headline', '-')}",
        f"- 综合评分：{scores.get('overall', '-')}",
        f"- 速度评分：{scores.get('speed', '-')}",
        f"- 可靠性评分：{scores.get('reliability', '-')}",
        "",
        "## 速度与并发",
        f"- 附件画像线程数：{concurrency.get('attachment_workers', 0)}",
        f"- 附件画像耗时：{speed.get('attachment_duration_seconds', '-')}",
        f"- 并行计划任务数：{concurrency.get('planned_task_count', 0)}",
        f"- 并行计划组数：{concurrency.get('parallel_group_count', 0)}",
        f"- 计划建议线程数：{concurrency.get('planned_max_workers', 0)}",
        f"- 求解脚本线程池：{'是' if concurrency.get('solver_thread_pool') else '否'}",
        f"- 求解脚本派发：{'是' if concurrency.get('solver_dispatch') else '否'}",
        f"- 求解脚本耗时：{speed.get('solver_duration_seconds', '-')}",
        "",
        "## 自动修复",
        f"- 自动修复轮数：{reliability.get('repair_count', 0)}",
        f"- 完整性门禁：{reliability.get('completeness_success')}",
        f"- 可继续生成：{reliability.get('can_resume')}",
    ]
    diagnosis = reliability.get("latest_failure_diagnosis") if isinstance(reliability.get("latest_failure_diagnosis"), dict) else {}
    if diagnosis:
        lines.extend(
            [
                f"- 最近诊断：{diagnosis.get('label') or diagnosis.get('category')}",
                f"- 修复重点：{diagnosis.get('repair_focus', '-')}",
                f"- 建议动作：{diagnosis.get('suggested_action', '-')}",
            ]
        )
    bottlenecks = speed.get("bottleneck_steps") if isinstance(speed.get("bottleneck_steps"), list) else []
    if bottlenecks:
        lines.extend(["", "## 慢阶段"])
        for item in bottlenecks:
            lines.append(f"- {item.get('title') or item.get('id')}: {item.get('duration_seconds')} 秒")
    lines.extend(["", "## 建议"])
    for item in payload.get("recommendations", []) or []:
        lines.append(f"- {item}")
    lines.extend(["", "## 来源文件"])
    for key, value in (payload.get("source_artifacts") or {}).items():
        if value:
            lines.append(f"- {key}: `{value}`")
    return "\n".join(lines) + "\n"


def latest_failure_diagnosis(*payloads: Any) -> dict[str, Any]:
    for payload in payloads:
        if not isinstance(payload, dict):
            continue
        diagnosis = payload.get("failure_diagnosis") or payload.get("last_failure_diagnosis")
        if isinstance(diagnosis, dict) and diagnosis.get("category"):
            return diagnosis
        latest = payload.get("latest_attempt")
        if isinstance(latest, dict):
            diagnosis = latest.get("failure_diagnosis")
            if isinstance(diagnosis, dict) and diagnosis.get("category"):
                return diagnosis
        steps = payload.get("steps")
        if isinstance(steps, list):
            for step in reversed(steps):
                if isinstance(step, dict) and isinstance(step.get("failure_diagnosis"), dict) and step["failure_diagnosis"].get("category"):
                    return step["failure_diagnosis"]
    return {}


def slowest_steps(steps: list[Any], limit: int = 4) -> list[dict[str, Any]]:
    rows = []
    for step in steps:
        if not isinstance(step, dict):
            continue
        duration = safe_float(step.get("duration_seconds"))
        if duration <= 0:
            continue
        rows.append(
            {
                "id": step.get("id"),
                "title": step.get("title"),
                "status": step.get("status"),
                "duration_seconds": duration,
            }
        )
    return sorted(rows, key=lambda item: item["duration_seconds"], reverse=True)[:limit]


def can_resume(metadata: dict[str, Any], workflow: dict[str, Any]) -> bool:
    progress = metadata.get("auto_workflow_progress", {}) if isinstance(metadata, dict) else {}
    if isinstance(progress, dict) and progress.get("can_resume"):
        return True
    status = metadata.get("auto_workflow_status") if isinstance(metadata, dict) else ""
    if status in {"failed", "cancelled", "completed_with_warnings", "interrupted"}:
        return True
    if isinstance(workflow, dict) and workflow.get("overall_status") in {"failed", "cancelled", "completed_with_warnings"}:
        return True
    return False


def load_json_if_exists(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = load_json(path)
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def sum_float(values: Any) -> float:
    total = 0.0
    for value in values:
        total += safe_float(value)
    return round(total, 3)


def safe_float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def clamp_score(value: float) -> int:
    return max(0, min(100, int(round(value))))
