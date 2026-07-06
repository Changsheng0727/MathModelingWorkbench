from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from app.services.action_catalog import enrich_action
from app.services.performance_health import latest_failure_diagnosis
from app.services.store import load_json, save_json


REPAIR_BRIEFING_RELATIVE = "artifacts/repair_briefing.md"
REPAIR_BRIEFING_JSON_RELATIVE = "artifacts/repair_briefing.json"


def write_repair_briefing(root: Path, meta: dict[str, Any] | None = None) -> dict[str, str]:
    payload = build_repair_briefing(root, meta)
    save_json(root / REPAIR_BRIEFING_JSON_RELATIVE, payload)
    (root / REPAIR_BRIEFING_RELATIVE).write_text(render_repair_briefing_markdown(payload), encoding="utf-8")
    if isinstance(meta, dict):
        meta["repair_center_status"] = payload.get("status", "")
        meta["repair_center_label"] = payload.get("label", "")
        meta["repair_center_summary"] = payload.get("summary", "")
        primary_action = payload.get("primary_action", {})
        primary_action = primary_action if isinstance(primary_action, dict) else {}
        meta["repair_center_action"] = primary_action.get("id", "")
        meta["repair_center_action_label"] = primary_action.get("label", "")
        meta["repair_center_action_button_label"] = primary_action.get("button_label", "")
        meta["repair_center_can_resume"] = payload.get("can_resume", False)
        meta.setdefault("artifacts", {}).update(
            {
                "repair_briefing": REPAIR_BRIEFING_RELATIVE,
                "repair_briefing_json": REPAIR_BRIEFING_JSON_RELATIVE,
            }
        )
    return {
        "repair_briefing": REPAIR_BRIEFING_RELATIVE,
        "repair_briefing_json": REPAIR_BRIEFING_JSON_RELATIVE,
    }


def build_repair_briefing(root: Path, meta: dict[str, Any] | None = None) -> dict[str, Any]:
    metadata = meta if isinstance(meta, dict) else load_json_if_exists(root / "metadata.json")
    progress = load_json_if_exists(root / "artifacts" / "auto_workflow_progress.json")
    run_status = load_json_if_exists(root / "artifacts" / "computed_solution_status.json")
    completeness = load_json_if_exists(root / "artifacts" / "computed_solution_completeness.json")
    repair = load_json_if_exists(root / "artifacts" / "computed_solver_repair.json")
    workflow = load_json_if_exists(root / "artifacts" / "auto_workflow_report.json")
    performance = load_json_if_exists(root / "artifacts" / "performance_health.json")

    diagnosis = latest_failure_diagnosis(progress, run_status, completeness, repair, workflow, metadata)
    statuses = collect_statuses(metadata, progress, run_status, completeness, performance)
    can_resume = can_resume_workflow(metadata, progress, workflow, diagnosis)
    evidence = collect_evidence(root, diagnosis, statuses)
    actions = build_actions(root, metadata, progress, diagnosis, statuses, can_resume)
    status, label = repair_status(diagnosis, statuses, can_resume, actions)
    summary = build_summary(label, diagnosis, statuses, actions)
    return {
        "stage": "repair_center",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "status": status,
        "label": label,
        "summary": summary,
        "can_resume": can_resume,
        "primary_action": actions[0] if actions else {},
        "actions": actions,
        "latest_failure_diagnosis": diagnosis,
        "status_snapshot": statuses,
        "evidence": evidence,
        "source_artifacts": source_artifacts(root),
    }


def collect_statuses(
    metadata: dict[str, Any],
    progress: dict[str, Any],
    run_status: dict[str, Any],
    completeness: dict[str, Any],
    performance: dict[str, Any],
) -> dict[str, Any]:
    return {
        "project_status": metadata.get("status", ""),
        "auto_workflow_status": metadata.get("auto_workflow_status", "") or progress.get("status", ""),
        "computed_solution_status": metadata.get("computed_solution_status", ""),
        "computed_solution_success": run_status.get("success") if isinstance(run_status, dict) else None,
        "completeness_success": completeness.get("success") if isinstance(completeness, dict) else None,
        "performance_health_status": metadata.get("performance_health_status", "") or performance.get("status", ""),
        "paper_fill_status": metadata.get("paper_fill_status", ""),
        "compile_status": metadata.get("compile_status", ""),
        "paper_review_status": metadata.get("paper_review_status", ""),
    }


def build_actions(
    root: Path,
    metadata: dict[str, Any],
    progress: dict[str, Any],
    diagnosis: dict[str, Any],
    statuses: dict[str, Any],
    can_resume: bool,
) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    project_id = str(metadata.get("id") or "")
    if can_resume:
        actions.append(
            {
                "id": "resume_auto_workflow",
                "label": "继续生成并自动修复",
                "priority": "high",
                "endpoint": f"/api/projects/{project_id}/auto/resume/start" if project_id else "",
                "method": "POST",
                "detail": diagnosis.get("suggested_action") or "系统会带着最近失败诊断继续运行自动修复。",
            }
        )
    if diagnosis:
        actions.append(
            {
                "id": "inspect_failure_evidence",
                "label": "查看失败证据",
                "priority": "high",
                "endpoint": "",
                "method": "OPEN_ARTIFACT",
                "detail": diagnosis.get("repair_focus") or diagnosis.get("evidence") or "查看错误日志、修复记录和完整性门禁。",
            }
        )
    if not (root / "artifacts" / "attachment_profile.json").exists() or not (root / "artifacts" / "parallel_task_plan.json").exists():
        actions.append(
            {
                "id": "refresh_diagnostics",
                "label": "刷新诊断与并行计划",
                "priority": "medium",
                "endpoint": f"/api/projects/{project_id}/diagnostics/refresh" if project_id else "",
                "method": "POST",
                "detail": "补齐附件画像、并行任务计划和性能健康报告，降低字段识别和脚本并发缺失风险。",
            }
        )
    if statuses.get("auto_workflow_status") in {"", "idle", "analyzed"} and not can_resume:
        actions.append(
            {
                "id": "start_auto_workflow",
                "label": "启动一键自动流程",
                "priority": "medium",
                "endpoint": f"/api/projects/{project_id}/auto/start" if project_id else "",
                "method": "POST",
                "detail": "当前没有阻断性失败，可直接进入后台任务池运行完整流程。",
            }
        )
    if statuses.get("completeness_success") is False:
        actions.append(
            {
                "id": "fix_completeness_gate",
                "label": "补齐完整性门禁",
                "priority": "high",
                "endpoint": f"/api/projects/{project_id}/auto/resume/start" if project_id else "",
                "method": "POST",
                "detail": "优先补齐每个子问题的结果表、图片、指标和 manifest 证据。",
            }
        )
    if not actions:
        actions.append(
            {
                "id": "continue_review",
                "label": "继续编译和审查",
                "priority": "low",
                "endpoint": "",
                "method": "MANUAL",
                "detail": "当前没有明显阻断，可继续论文编译、审查和支撑材料打包。",
            }
        )
    return [enrich_action(action) for action in dedupe_actions(actions)[:6]]


def collect_evidence(root: Path, diagnosis: dict[str, Any], statuses: dict[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    if diagnosis:
        rows.append(
            {
                "label": diagnosis.get("label") or diagnosis.get("category") or "失败诊断",
                "detail": diagnosis.get("evidence") or diagnosis.get("repair_focus") or "",
                "source": "last_failure_diagnosis",
            }
        )
    for key, relative in source_artifacts(root).items():
        rows.append({"label": key, "detail": relative, "source": relative})
    for key, value in statuses.items():
        if value not in (None, "", [], {}):
            rows.append({"label": key, "detail": str(value), "source": "metadata/status"})
    return rows[:20]


def source_artifacts(root: Path) -> dict[str, str]:
    candidates = {
        "auto_workflow_progress": "artifacts/auto_workflow_progress.json",
        "computed_solution_status": "artifacts/computed_solution_status.json",
        "computed_solver_repair": "artifacts/computed_solver_repair.json",
        "computed_solution_completeness": "artifacts/computed_solution_completeness.json",
        "performance_health": "artifacts/performance_health.json",
        "auto_workflow_report": "artifacts/auto_workflow_report.json",
    }
    return {key: relative for key, relative in candidates.items() if (root / relative).exists()}


def repair_status(
    diagnosis: dict[str, Any],
    statuses: dict[str, Any],
    can_resume: bool,
    actions: list[dict[str, Any]],
) -> tuple[str, str]:
    if diagnosis or statuses.get("computed_solution_status") == "failed" or statuses.get("completeness_success") is False:
        return "action_required", "需修复"
    if can_resume or statuses.get("auto_workflow_status") in {"failed", "cancelled", "interrupted", "completed_with_warnings"}:
        return "repairable", "可继续"
    if statuses.get("performance_health_status") in {"warning", "failed"}:
        return "optimize", "建议优化"
    if actions and actions[0].get("id") == "start_auto_workflow":
        return "ready", "可启动"
    return "clear", "无阻断"


def build_summary(
    label: str,
    diagnosis: dict[str, Any],
    statuses: dict[str, Any],
    actions: list[dict[str, Any]],
) -> str:
    parts = [label]
    if diagnosis:
        parts.append(str(diagnosis.get("label") or diagnosis.get("category") or "存在失败诊断"))
    elif statuses.get("performance_health_status"):
        parts.append(f"性能健康：{statuses.get('performance_health_status')}")
    if actions:
        parts.append(f"建议：{actions[0].get('label')}")
    return "；".join(part for part in parts if part)


def can_resume_workflow(
    metadata: dict[str, Any],
    progress: dict[str, Any],
    workflow: dict[str, Any],
    diagnosis: dict[str, Any],
) -> bool:
    if progress.get("can_resume"):
        return True
    if metadata.get("auto_workflow_status") in {"failed", "cancelled", "completed_with_warnings", "interrupted"}:
        return True
    if workflow.get("overall_status") in {"failed", "cancelled", "completed_with_warnings"}:
        return True
    return bool(diagnosis)


def dedupe_actions(actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    result = []
    order = {"high": 0, "medium": 1, "low": 2}
    for item in sorted(actions, key=lambda action: order.get(str(action.get("priority")), 9)):
        action_id = item.get("id")
        if not action_id or action_id in seen:
            continue
        seen.add(action_id)
        result.append(item)
    return result


def render_repair_briefing_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# 自动修复中心",
        "",
        f"- 生成时间：{payload.get('generated_at', '-')}",
        f"- 状态：{payload.get('label', '-')}",
        f"- 摘要：{payload.get('summary', '-')}",
        f"- 可继续生成：{payload.get('can_resume')}",
        "",
        "## 建议动作",
    ]
    for action in payload.get("actions", []) or []:
        lines.append(f"- **{action.get('label')}**（{action.get('priority')}）：{action.get('detail')}")
        if action.get("endpoint"):
            lines.append(f"  - 接口：`{action.get('method')} {action.get('endpoint')}`")
    diagnosis = payload.get("latest_failure_diagnosis") if isinstance(payload.get("latest_failure_diagnosis"), dict) else {}
    if diagnosis:
        lines.extend(
            [
                "",
                "## 最近失败诊断",
                f"- 类型：{diagnosis.get('label') or diagnosis.get('category')}",
                f"- 修复重点：{diagnosis.get('repair_focus', '-')}",
                f"- 建议动作：{diagnosis.get('suggested_action', '-')}",
            ]
        )
    lines.extend(["", "## 证据"])
    for item in payload.get("evidence", []) or []:
        lines.append(f"- {item.get('label')}: {item.get('detail')}")
    return "\n".join(lines) + "\n"


def load_json_if_exists(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = load_json(path)
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}
