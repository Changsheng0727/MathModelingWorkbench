from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from app.services.action_catalog import enrich_action
from app.services.store import load_json, save_json


DELIVERY_READINESS_RELATIVE = "artifacts/delivery_readiness.md"
DELIVERY_READINESS_JSON_RELATIVE = "artifacts/delivery_readiness.json"


def write_delivery_readiness_report(root: Path, meta: dict[str, Any] | None = None) -> dict[str, str]:
    payload = build_delivery_readiness(root, meta)
    save_json(root / DELIVERY_READINESS_JSON_RELATIVE, payload)
    (root / DELIVERY_READINESS_RELATIVE).write_text(render_delivery_markdown(payload), encoding="utf-8")
    if isinstance(meta, dict):
        primary_action = payload.get("primary_action", {})
        primary_action = primary_action if isinstance(primary_action, dict) else {}
        meta["delivery_readiness_status"] = payload.get("status", "")
        meta["delivery_readiness_label"] = payload.get("label", "")
        meta["delivery_readiness_summary"] = payload.get("summary", "")
        meta["delivery_readiness_score"] = payload.get("score", 0)
        meta["delivery_readiness_action"] = primary_action.get("id", "")
        meta["delivery_readiness_action_label"] = primary_action.get("label", "")
        meta["delivery_readiness_action_button_label"] = primary_action.get("button_label", "")
        meta["delivery_readiness_can_submit"] = payload.get("can_submit", False)
        meta.setdefault("artifacts", {}).update(
            {
                "delivery_readiness": DELIVERY_READINESS_RELATIVE,
                "delivery_readiness_json": DELIVERY_READINESS_JSON_RELATIVE,
            }
        )
    return {
        "delivery_readiness": DELIVERY_READINESS_RELATIVE,
        "delivery_readiness_json": DELIVERY_READINESS_JSON_RELATIVE,
    }


def build_delivery_readiness(root: Path, meta: dict[str, Any] | None = None) -> dict[str, Any]:
    metadata = meta if isinstance(meta, dict) else load_json_if_exists(root / "metadata.json")
    analysis = load_json_if_exists(root / "artifacts" / "analysis.json")
    paper_review = load_json_if_exists(root / "artifacts" / "paper_review.json")
    performance = load_json_if_exists(root / "artifacts" / "performance_health.json")
    repair = load_json_if_exists(root / "artifacts" / "repair_briefing.json")
    computed_manifest = load_json_if_exists(root / "results" / "computed_manifest.json")
    auto_report = load_json_if_exists(root / "artifacts" / "auto_workflow_report.json")

    checks = build_checks(root, metadata, analysis, paper_review, performance, repair, computed_manifest, auto_report)
    score = score_checks(checks)
    status, label = readiness_status(score, checks)
    can_submit = status in {"deliverable", "review"}
    actions = build_actions(metadata, checks, can_submit, score)
    summary = build_summary(label, score, checks, actions)
    return {
        "stage": "delivery_readiness",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "status": status,
        "label": label,
        "score": score,
        "summary": summary,
        "can_submit": can_submit,
        "primary_action": actions[0] if actions else {},
        "actions": actions,
        "checks": checks,
        "required_missing": [item for item in checks if item.get("required") and item.get("status") == "fail"],
        "warning_count": sum(1 for item in checks if item.get("status") == "warning"),
        "source_artifacts": source_artifacts(root),
    }


def build_checks(
    root: Path,
    metadata: dict[str, Any],
    analysis: dict[str, Any],
    paper_review: dict[str, Any],
    performance: dict[str, Any],
    repair: dict[str, Any],
    computed_manifest: dict[str, Any],
    auto_report: dict[str, Any],
) -> list[dict[str, Any]]:
    artifacts = metadata.get("artifacts", {}) if isinstance(metadata.get("artifacts"), dict) else {}
    checks: list[dict[str, Any]] = []
    checks.append(
        make_check(
            "analysis_ready",
            "赛题分析",
            "pass" if analysis else "fail",
            "已生成 analysis.json。" if analysis else "缺少 analysis.json，无法确认题目、附件和论文结构。",
            required=True,
            action="analyze_project",
        )
    )
    final_problem = metadata.get("final_problem") if isinstance(metadata.get("final_problem"), dict) else {}
    recommended = analysis.get("recommended_problem") if isinstance(analysis.get("recommended_problem"), dict) else {}
    checks.append(
        make_check(
            "problem_selected",
            "选题确认",
            "pass" if final_problem or recommended else "warning",
            "已确认或识别推荐题目。" if final_problem or recommended else "尚未稳定确认最终题目。",
            required=False,
            action="select_problem",
        )
    )
    computed_ready = bool(computed_manifest) or metadata.get("computed_solution_status") == "success"
    auto_success = metadata.get("auto_workflow_status") == "success" or auto_report.get("overall_status") == "success"
    checks.append(
        make_check(
            "computed_results",
            "代码结果",
            "pass" if computed_ready else "warning" if auto_success else "fail",
            "已找到代码计算结果和 manifest。"
            if computed_ready
            else "自动流程已完成但结果 manifest 不完整。"
            if auto_success
            else "缺少代码求解结果，论文结论可追溯性不足。",
            required=True,
            action="run_auto_workflow" if analysis else "analyze_project",
        )
    )
    checks.append(file_check(root, "paper_source", "论文 LaTeX", "paper/main.tex", required=True, action="fill_paper"))
    checks.append(file_check(root, "paper_pdf", "论文 PDF", artifacts.get("paper_pdf") or "paper/main.pdf", required=True, action="compile_latex"))
    checks.append(file_check(root, "paper_docx", "论文 Word", artifacts.get("paper_docx") or "paper/main.docx", required=False, action="compile_latex"))
    checks.append(file_check(root, "latex_log", "编译日志", artifacts.get("latex_log") or "artifacts/latex_compile.log", required=False, action="compile_latex"))
    checks.append(review_check(paper_review, metadata))
    checks.append(repair_check(repair, metadata))
    checks.append(performance_check(performance, metadata))
    checks.append(support_check(root))
    return checks


def file_check(root: Path, check_id: str, label: str, relative: str, *, required: bool, action: str) -> dict[str, Any]:
    path = root / relative if relative else root / "__missing__"
    exists = bool(relative) and path.exists() and path.is_file()
    return make_check(
        check_id,
        label,
        "pass" if exists else "fail" if required else "warning",
        f"已找到 {relative}。" if exists else f"缺少 {relative}。",
        required=required,
        action=action,
        artifact=relative if exists else "",
    )


def review_check(paper_review: dict[str, Any], metadata: dict[str, Any]) -> dict[str, Any]:
    overall = paper_review.get("overall", {}) if isinstance(paper_review.get("overall"), dict) else {}
    review_status = overall.get("status") or metadata.get("paper_review_status", "")
    score = overall.get("score")
    if review_status == "pass":
        status = "pass"
        detail = f"论文审查通过，得分 {score}。"
    elif review_status in {"warning", "success"}:
        status = "warning"
        detail = f"论文审查仍有警告，得分 {score}。"
    elif paper_review:
        status = "fail"
        detail = f"论文审查未通过，得分 {score}。"
    else:
        status = "warning"
        detail = "尚未生成论文审查报告。"
    return make_check("paper_review", "论文审查", status, detail, required=False, action="review_paper")


def repair_check(repair: dict[str, Any], metadata: dict[str, Any]) -> dict[str, Any]:
    status_value = repair.get("status") or metadata.get("repair_center_status", "")
    has_diagnosis = bool(metadata.get("last_failure_diagnosis"))
    if status_value in {"action_required"} or has_diagnosis or metadata.get("computed_solution_status") == "failed":
        return make_check(
            "blocking_repair",
            "阻断修复",
            "fail",
            repair.get("summary") or "仍存在失败诊断或代码求解失败。",
            required=True,
            action="resume_auto_workflow",
        )
    if status_value in {"repairable", "optimize"}:
        return make_check("blocking_repair", "阻断修复", "warning", repair.get("summary") or "仍建议复核修复中心。", action="refresh_repair")
    return make_check("blocking_repair", "阻断修复", "pass", "未发现阻断性交付问题。", action="refresh_repair")


def performance_check(performance: dict[str, Any], metadata: dict[str, Any]) -> dict[str, Any]:
    status_value = performance.get("status") or metadata.get("performance_health_status", "")
    score = metadata.get("performance_health_score") or (performance.get("scores", {}) or {}).get("overall")
    if status_value == "failed":
        status = "warning"
        detail = f"性能健康需关注，综合 {score}。"
    elif status_value == "warning":
        status = "warning"
        detail = f"性能健康可优化，综合 {score}。"
    elif status_value == "success":
        status = "pass"
        detail = f"性能健康良好，综合 {score}。"
    else:
        status = "warning"
        detail = "尚未刷新性能健康报告。"
    return make_check("performance_health", "性能健康", status, detail, required=False, action="refresh_diagnostics")


def support_check(root: Path) -> dict[str, Any]:
    evidence_dirs = ["artifacts", "paper", "code", "results"]
    file_count = 0
    for folder in evidence_dirs:
        path = root / folder
        if path.exists():
            file_count += sum(1 for item in path.rglob("*") if item.is_file() and "support_materials" not in item.parts)
    status = "pass" if file_count >= 3 else "warning"
    detail = f"支撑材料包可按需生成，当前可纳入 {file_count} 个文件。" if file_count else "暂未发现可打包的交付材料。"
    return make_check("support_package", "正式交付包", status, detail, required=False, action="build_delivery_package")


def make_check(
    check_id: str,
    label: str,
    status: str,
    detail: str,
    *,
    required: bool = False,
    action: str = "",
    artifact: str = "",
) -> dict[str, Any]:
    return {
        "id": check_id,
        "label": label,
        "status": status,
        "detail": detail,
        "required": required,
        "action": action,
        "artifact": artifact,
    }


def score_checks(checks: list[dict[str, Any]]) -> int:
    score = 100
    for item in checks:
        if item.get("status") == "fail":
            score -= 18 if item.get("required") else 10
        elif item.get("status") == "warning":
            score -= 5 if item.get("required") else 4
    return max(0, min(100, score))


def readiness_status(score: int, checks: list[dict[str, Any]]) -> tuple[str, str]:
    required_fail = any(item.get("required") and item.get("status") == "fail" for item in checks)
    any_fail = any(item.get("status") == "fail" for item in checks)
    if required_fail:
        return "blocked", "不可提交"
    if any_fail or score < 75:
        return "needs_work", "需补齐"
    if score < 92 or any(item.get("status") == "warning" for item in checks):
        return "review", "可提交但建议复核"
    return "deliverable", "可提交"


def build_actions(metadata: dict[str, Any], checks: list[dict[str, Any]], can_submit: bool, score: int = 0) -> list[dict[str, Any]]:
    project_id = str(metadata.get("id") or "")
    endpoint_map = {
        "resume_auto_workflow": ("继续生成并自动修复", "POST", f"/api/projects/{project_id}/auto/resume/start"),
        "analyze_project": ("重建赛题分析", "POST", f"/api/projects/{project_id}/analyze"),
        "run_auto_workflow": ("启动一键自动流程", "POST", f"/api/projects/{project_id}/auto/start"),
        "compile_latex": ("编译 PDF/Word", "POST", f"/api/projects/{project_id}/compile"),
        "review_paper": ("审查论文", "POST", f"/api/projects/{project_id}/paper/review"),
        "refresh_diagnostics": ("刷新诊断/性能", "POST", f"/api/projects/{project_id}/diagnostics/refresh"),
        "refresh_repair": ("刷新修复中心", "POST", f"/api/projects/{project_id}/repair/briefing"),
        "build_delivery_package": ("生成正式交付包", "POST", f"/api/projects/{project_id}/delivery/package"),
        "download_support_zip": ("下载支撑材料包", "GET", f"/api/projects/{project_id}/download/support.zip"),
    }
    actions: list[dict[str, Any]] = []
    package_first = can_submit and score >= 90 and not any(item.get("status") == "fail" for item in checks)
    if package_first:
        label, method, endpoint = endpoint_map["build_delivery_package"]
        actions.append(
            {
                "id": "build_delivery_package",
                "label": label,
                "method": method,
                "endpoint": endpoint if project_id else "",
                "priority": "high",
                "detail": "核心交付检查已通过，可生成带清单、哈希和论文结果索引的正式交付包。",
            }
        )
    for item in checks:
        if item.get("status") == "pass":
            continue
        action_id = str(item.get("action") or "")
        if action_id not in endpoint_map:
            continue
        label, method, endpoint = endpoint_map[action_id]
        priority = delivery_action_priority(item)
        if package_first and priority == "medium":
            priority = "low"
        actions.append(
            {
                "id": action_id,
                "label": label,
                "method": method,
                "endpoint": endpoint if project_id else "",
                "priority": priority,
                "detail": item.get("detail", ""),
            }
        )
    if can_submit and not package_first:
        label, method, endpoint = endpoint_map["build_delivery_package"]
        actions.append(
            {
                "id": "build_delivery_package",
                "label": label,
                "method": method,
                "endpoint": endpoint if project_id else "",
                "priority": "low",
                "detail": "核心交付件已具备，可生成正式交付包；建议同时处理上方提醒。",
            }
        )
    return [enrich_action(action) for action in dedupe_actions(actions)[:6]]


def delivery_action_priority(item: dict[str, Any]) -> str:
    if item.get("required") and item.get("status") == "fail":
        return "high"
    if item.get("status") == "fail":
        return "high"
    if item.get("required"):
        return "medium"
    if item.get("id") in {"paper_review", "performance_health", "blocking_repair"}:
        return "medium"
    return "low"


def dedupe_actions(actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    order = {"high": 0, "medium": 1, "low": 2}
    result = []
    for item in sorted(actions, key=lambda action: order.get(str(action.get("priority")), 9)):
        action_id = item.get("id")
        if not action_id or action_id in seen:
            continue
        seen.add(action_id)
        result.append(item)
    return result


def build_summary(label: str, score: int, checks: list[dict[str, Any]], actions: list[dict[str, Any]]) -> str:
    fail_count = sum(1 for item in checks if item.get("status") == "fail")
    warning_count = sum(1 for item in checks if item.get("status") == "warning")
    parts = [f"{label}，交付分 {score}"]
    if fail_count:
        parts.append(f"{fail_count} 个阻断")
    if warning_count:
        parts.append(f"{warning_count} 个提醒")
    if actions:
        parts.append(f"下一步：{actions[0].get('label')}")
    return "；".join(parts)


def source_artifacts(root: Path) -> dict[str, str]:
    candidates = {
        "delivery_readiness": DELIVERY_READINESS_RELATIVE,
        "analysis": "artifacts/analysis.json",
        "computed_manifest": "results/computed_manifest.json",
        "paper_review": "artifacts/paper_review.json",
        "performance_health": "artifacts/performance_health.json",
        "repair_briefing": "artifacts/repair_briefing.json",
        "paper_pdf": "paper/main.pdf",
        "paper_docx": "paper/main.docx",
        "delivery_package": "artifacts/delivery_package.zip",
        "delivery_package_manifest": "artifacts/delivery_package_manifest.json",
    }
    return {key: relative for key, relative in candidates.items() if (root / relative).exists()}


def render_delivery_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# 交付就绪中心",
        "",
        f"- 生成时间：{payload.get('generated_at', '-')}",
        f"- 状态：{payload.get('label', '-')}",
        f"- 交付分：{payload.get('score', '-')}",
        f"- 摘要：{payload.get('summary', '-')}",
        f"- 可提交：{payload.get('can_submit')}",
        "",
        "## 检查项",
    ]
    for item in payload.get("checks", []) or []:
        required = "必需" if item.get("required") else "建议"
        lines.append(f"- **{item.get('label')}**（{required} / {item.get('status')}）：{item.get('detail')}")
    lines.extend(["", "## 下一步动作"])
    for action in payload.get("actions", []) or []:
        lines.append(f"- **{action.get('label')}**：{action.get('detail')}")
        if action.get("endpoint"):
            lines.append(f"  - 接口：`{action.get('method')} {action.get('endpoint')}`")
    lines.extend(["", "## 来源文件"])
    for key, value in (payload.get("source_artifacts") or {}).items():
        if value:
            lines.append(f"- {key}: `{value}`")
    return "\n".join(lines) + "\n"


def load_json_if_exists(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = load_json(path)
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}
