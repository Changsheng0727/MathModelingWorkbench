from __future__ import annotations

from pathlib import Path
from typing import Any


def build_project_readiness(
    root: Path,
    metadata: dict[str, Any],
    analysis: dict[str, Any] | None,
    *,
    llm_settings: dict[str, Any] | None = None,
    repair: dict[str, Any] | None = None,
    delivery: dict[str, Any] | None = None,
    package: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Small, user-facing readiness model for the current project overview."""
    checks = [
        check_metadata(metadata),
        check_llm(llm_settings or {}),
        check_analysis(analysis),
        check_problem(metadata, analysis),
        check_results(root, metadata),
        check_paper(root, metadata),
        check_pdf(root, metadata),
        check_delivery(metadata, delivery or {}, package or {}),
    ]
    required = [item for item in checks if item.get("required")]
    blockers = [item for item in checks if item.get("required") and item.get("status") == "fail"]
    warnings = [item for item in checks if item.get("status") == "warning"]
    score = score_checks(checks)
    status = "failed" if blockers else "warning" if warnings or score < 86 else "success"
    todo_items = readiness_todo_items(checks)
    blocking_item = next((item for item in checks if item.get("status") == "fail" and item.get("action")), None)
    warning_item = next((item for item in checks if item.get("status") == "warning" and item.get("action")), None)
    action_item = blocking_item
    primary_action = action_with_detail(blocking_item) if blocking_item else None
    if not primary_action and delivery_is_packaged(metadata, package or {}):
        primary_action = output_action(metadata, "打开交付包")
        action_item = None
    if not primary_action:
        primary_action = action_with_detail(warning_item) if warning_item else None
        action_item = warning_item
    primary_action = primary_action or output_action(metadata, "打开最新输出")
    return {
        "status": status,
        "label": readiness_label(status, score),
        "score": score,
        "summary": readiness_summary(status, score, blockers, warnings, metadata, repair or {}),
        "primary_action": primary_action,
        "next_step": readiness_next_step(primary_action, action_item),
        "phase": readiness_phase(status, primary_action),
        "completion": readiness_completion(checks, required, todo_items),
        "todo_items": todo_items,
        "checks": checks,
        "blockers": blockers,
        "warning_count": len(warnings),
        "required_passed": sum(1 for item in required if item.get("status") != "fail"),
        "required_total": len(required),
    }


def check_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    error = str(metadata.get("metadata_error") or "").strip()
    return readiness_check(
        "metadata",
        "项目元数据",
        "fail" if error else "pass",
        f"metadata.json 读取失败：{error}" if error else "项目元数据可读取。",
        required=True,
        action={"id": "open_project_root", "label": "打开文件夹"},
    )


def check_llm(settings: dict[str, Any]) -> dict[str, Any]:
    configured = bool(settings.get("configured"))
    return readiness_check(
        "llm",
        "大模型接口",
        "pass" if configured else "fail",
        "接口已保存并可用于自动求解。" if configured else "尚未配置可用 API Key。",
        required=True,
        action={"id": "focus_llm", "label": "填写接口"},
    )


def check_analysis(analysis: dict[str, Any] | None) -> dict[str, Any]:
    available = bool(analysis)
    return readiness_check(
        "analysis",
        "赛题分析",
        "pass" if available else "fail",
        "已完成题目、附件和候选题分析。" if available else "还没有赛题分析结果。",
        required=True,
        action={"id": "focus_upload", "label": "上传赛题"},
    )


def check_problem(metadata: dict[str, Any], analysis: dict[str, Any] | None) -> dict[str, Any]:
    final_problem = metadata.get("final_problem") if isinstance(metadata.get("final_problem"), dict) else {}
    analysis_data = analysis or {}
    recommended = analysis_data.get("recommended_problem") if isinstance(analysis_data.get("recommended_problem"), dict) else {}
    system_recommended = (
        analysis_data.get("system_recommended_problem")
        if isinstance(analysis_data.get("system_recommended_problem"), dict)
        else {}
    )
    selected = final_problem or recommended or system_recommended
    problem_id = selected.get("id") or selected.get("final_problem_id") or ""
    return readiness_check(
        "problem",
        "选题确认",
        "pass" if problem_id else "warning",
        f"当前将使用 {problem_id} 题。" if problem_id else "尚未确认最终选题。",
        required=False,
        action={"id": "open_problems", "label": "确认选题"},
    )


def check_results(root: Path, metadata: dict[str, Any]) -> dict[str, Any]:
    manifest = root / "results" / "computed_manifest.json"
    auto_status = str(metadata.get("auto_workflow_status") or "")
    computed_status = str(metadata.get("computed_solution_status") or "")
    failed = auto_status in {"failed", "cancelled", "interrupted"} or computed_status == "failed"
    ready = manifest.exists() or computed_status == "success"
    if ready:
        status = "pass"
        detail = "已找到代码运行结果和 manifest。"
        action = {"id": "open_outputs", "label": "查看结果"}
    elif failed:
        status = "fail"
        detail = "代码求解或自动流程失败，需要继续修复。"
        action = {"id": "resume_auto", "label": "继续修复"}
    else:
        status = "fail"
        detail = "还没有代码求解结果。"
        action = {"id": "start_auto", "label": "一键求解"}
    return readiness_check("results", "代码结果", status, detail, required=True, action=action)


def check_paper(root: Path, metadata: dict[str, Any]) -> dict[str, Any]:
    artifacts = metadata.get("artifacts", {}) if isinstance(metadata.get("artifacts"), dict) else {}
    relative = str(artifacts.get("paper_llm") or artifacts.get("paper_autofilled") or "paper/main.tex")
    exists = (root / relative).exists()
    return readiness_check(
        "paper",
        "论文正文",
        "pass" if exists else "warning",
        f"已生成 {relative}。" if exists else "还没有可检查的论文 LaTeX。",
        required=False,
        action={"id": "open_outputs", "label": "查看输出"},
    )


def check_pdf(root: Path, metadata: dict[str, Any]) -> dict[str, Any]:
    artifacts = metadata.get("artifacts", {}) if isinstance(metadata.get("artifacts"), dict) else {}
    relative = str(artifacts.get("paper_pdf") or "paper/main.pdf")
    exists = (root / relative).exists()
    compile_status = str(metadata.get("compile_status") or "")
    status = "pass" if exists else "warning" if compile_status != "failed" else "fail"
    detail = f"已生成 {relative}。" if exists else "PDF 尚未生成或编译失败。"
    return readiness_check(
        "pdf",
        "PDF 论文",
        status,
        detail,
        required=False,
        action={"id": "compile", "label": "编译论文"},
    )


def check_delivery(metadata: dict[str, Any], delivery: dict[str, Any], package: dict[str, Any]) -> dict[str, Any]:
    status_value = str(delivery.get("status") or metadata.get("delivery_readiness_status") or "")
    packaged = delivery_is_packaged(metadata, package)
    if packaged:
        status = "pass"
        detail = "正式交付包已生成。"
        action = output_action(metadata, "打开交付包", {"id": "open_project_root", "label": "打开文件夹"})
    elif status_value in {"ready", "success", "deliverable", "review"}:
        status = "warning"
        detail = "论文已接近可交付，建议生成交付包。"
        action = {"id": "build_delivery_package", "label": "生成交付包"}
    else:
        status = "warning"
        detail = "交付检查尚未完成。"
        action = {"id": "refresh_delivery", "label": "检查交付"}
    return readiness_check("delivery", "交付文件", status, detail, required=False, action=action)


def delivery_is_packaged(metadata: dict[str, Any], package: dict[str, Any]) -> bool:
    return bool(package) or metadata.get("delivery_package_status") == "success" or bool(metadata.get("delivery_package_sha256"))


def output_action(metadata: dict[str, Any], label: str, fallback: dict[str, str] | None = None) -> dict[str, str]:
    summary = metadata.get("artifact_summary") if isinstance(metadata.get("artifact_summary"), dict) else {}
    path = str(metadata.get("primary_output_path") or summary.get("latest_path") or "").strip()
    if path:
        return {"id": "open_primary_output", "label": label, "path": path}
    return fallback or {"id": "open_outputs", "label": "查看输出"}


def readiness_check(
    check_id: str,
    label: str,
    status: str,
    detail: str,
    *,
    required: bool,
    action: dict[str, str],
) -> dict[str, Any]:
    return {
        "id": check_id,
        "label": label,
        "status": status,
        "detail": detail,
        "required": required,
        "action": action,
    }


def action_with_detail(item: dict[str, Any]) -> dict[str, str]:
    if not item:
        return {}
    action = dict(item.get("action") or {})
    detail = str(item.get("detail") or "").strip()
    if detail:
        action.setdefault("detail", detail)
    return action


def readiness_next_step(action: dict[str, Any], item: dict[str, Any] | None) -> dict[str, str]:
    action_id = str(action.get("id") or "").strip()
    label = str(action.get("label") or "").strip()
    if not action_id or not label:
        return {}
    detail = str(action.get("detail") or "").strip()
    if not detail and item:
        detail = str(item.get("detail") or "").strip()
    if not detail and action.get("path"):
        detail = f"打开 {Path(str(action.get('path'))).name or '输出文件'} 所在位置。"
    return {
        "id": action_id,
        "label": label,
        "detail": detail,
        "check_id": str((item or {}).get("id") or ""),
        "check_label": str((item or {}).get("label") or ""),
        "path": str(action.get("path") or ""),
    }


def readiness_phase(status: str, action: dict[str, Any]) -> dict[str, str]:
    action_id = str(action.get("id") or "")
    phases = {
        "focus_llm": ("configure", "配置接口", "先保存可用的大模型接口。"),
        "focus_upload": ("analyze", "上传分析", "先上传赛题并完成材料分析。"),
        "open_problems": ("select", "确认选题", "确认最终解题题号。"),
        "start_auto": ("solve", "自动求解", "启动代码求解、运行和论文回填。"),
        "resume_auto": ("repair", "继续修复", "从中断或失败处继续生成。"),
        "open_outputs": ("paper", "整理论文", "检查代码结果和论文文件。"),
        "compile": ("compile", "编译论文", "生成或修复 PDF 论文。"),
        "refresh_delivery": ("delivery", "交付检查", "检查论文、结果和支撑材料。"),
        "build_delivery_package": ("package", "生成交付包", "打包最终提交材料。"),
        "open_primary_output": ("done", "交付完成", "查看已经生成的交付材料。"),
    }
    phase_id, label, detail = phases.get(action_id, ("review", "人工复核", "检查当前项目输出。"))
    if status == "success" and action_id != "open_primary_output":
        phase_id, label, detail = "review", "最终复核", "关键步骤已完成，可做最终人工检查。"
    return {"id": phase_id, "label": label, "detail": detail}


def readiness_todo_items(checks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    priorities = {"fail": 0, "warning": 1}
    items = [item for item in checks if str(item.get("status") or "") != "pass"]
    items.sort(key=lambda item: (0 if item.get("required") else 1, priorities.get(str(item.get("status") or ""), 2)))
    rows = []
    for item in items:
        action = action_with_detail(item)
        rows.append(
            {
                "id": str(item.get("id") or ""),
                "label": str(item.get("label") or ""),
                "status": str(item.get("status") or ""),
                "detail": str(item.get("detail") or ""),
                "required": bool(item.get("required")),
                "action": action,
                "action_id": str(action.get("id") or ""),
                "action_label": str(action.get("label") or ""),
                "action_path": str(action.get("path") or ""),
            }
        )
    return rows


def readiness_completion(
    checks: list[dict[str, Any]],
    required: list[dict[str, Any]],
    todo_items: list[dict[str, Any]],
) -> dict[str, Any]:
    passed = sum(1 for item in checks if item.get("status") == "pass")
    required_passed = sum(1 for item in required if item.get("status") != "fail")
    failed = sum(1 for item in checks if item.get("status") == "fail")
    warning = sum(1 for item in checks if item.get("status") == "warning")
    total = len(checks)
    todo_count = len(todo_items)
    percent = round(100 * passed / total) if total else 0
    required_percent = round(100 * required_passed / len(required)) if required else 0
    return {
        "passed": passed,
        "total": total,
        "percent": percent,
        "failed": failed,
        "warning": warning,
        "todo_count": todo_count,
        "required_passed": required_passed,
        "required_total": len(required),
        "required_percent": required_percent,
        "label": f"已通过 {passed}/{total}，待处理 {todo_count} 项",
    }


def score_checks(checks: list[dict[str, Any]]) -> int:
    if not checks:
        return 0
    weights = {"pass": 1.0, "warning": 0.58, "fail": 0.0}
    weighted = 0.0
    total = 0.0
    for item in checks:
        weight = 1.4 if item.get("required") else 0.8
        total += weight
        weighted += weight * weights.get(str(item.get("status") or ""), 0.0)
    return round(100 * weighted / max(1.0, total))


def readiness_label(status: str, score: int) -> str:
    if status == "failed":
        return "还不能一键交付"
    if score >= 90:
        return "已接近可交付"
    if score >= 70:
        return "可以继续推进"
    return "需要补齐关键步骤"


def readiness_summary(
    status: str,
    score: int,
    blockers: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
    metadata: dict[str, Any],
    repair: dict[str, Any],
) -> str:
    if blockers:
        labels = "、".join(str(item.get("label") or "") for item in blockers[:2])
        return f"当前准备度 {score} 分，优先处理：{labels}。"
    if status == "warning" and warnings:
        labels = "、".join(str(item.get("label") or "") for item in warnings[:2])
        return f"核心链路可继续，建议补齐：{labels}。"
    if repair.get("summary"):
        return str(repair.get("summary"))
    if metadata.get("delivery_package_status") == "success":
        return "论文、结果和交付包已经比较完整，可以做最终人工复核。"
    return "关键步骤已经就绪，可以继续检查论文和交付材料。"
