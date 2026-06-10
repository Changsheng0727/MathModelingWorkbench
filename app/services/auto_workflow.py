from __future__ import annotations

import json
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from app.services.analyzer import apply_problem_selection
from app.services.attachment_profile import build_attachment_profile
from app.services.backend_skills import write_backend_skill_report
from app.services.code_graph import write_code_graph_report
from app.services.code_solution import integrate_existing_code_results, run_code_result_pipeline
from app.services.llm_settings import get_llm_settings
from app.services.llm_stream import bind_llm_stream
from app.services.llm_solution import require_llm_configured, run_llm_only_solution, run_llm_planning_solution
from app.services.performance_health import write_performance_health_report
from app.services.reviewer import review_paper
from app.services.runner import compile_latex
from app.services.store import load_json, make_support_zip, save_json
from app.services.workflow_strategy import get_workflow_strategy, public_workflow_strategy


StepFn = Callable[[], dict[str, Any]]
CONTROL_RELATIVE = "artifacts/auto_workflow_control.json"
AUTO_WORKFLOW_TOTAL_STEPS = 9
LLM_PLANNING_ARTIFACT_KEYS = {
    "llm_full_solution": "artifacts/llm_full_solution.md",
    "llm_full_solution_json": "artifacts/llm_full_solution.json",
}

LEGACY_MODELING_ARTIFACT_KEYS = {
    "modeling_script",
    "modeling_log",
    "modeling_manifest",
    "baseline_summary",
    "specialized_script",
    "specialized_log",
    "specialized_manifest",
    "specialized_summary",
    "llm_baseline_review",
    "llm_baseline_review_json",
    "llm_specialized_review",
    "llm_specialized_review_json",
    "paper_autofilled",
    "paper_fill_summary",
    "latex_skeleton",
}


class AutoWorkflowCancelled(RuntimeError):
    pass


def run_auto_workflow(root: Path, meta: dict[str, Any], resume: bool = False) -> dict[str, Any]:
    stream_title = "继续自动流程大模型直播" if resume else "一键自动流程大模型直播"
    stream_detail = "正在从最后成功阶段继续执行。" if resume else "正在先完成代码求解和图表完整性校验，再生成论文。"
    with bind_llm_stream(root, "auto_workflow", stream_title, stream_detail) as live_stream:
        report = _run_auto_workflow(root, meta, resume=resume)
        status = report.get("overall_status") or "success"
        live_status = "success" if status == "success" else "failed" if status == "failed" else "warning"
        live_stream.finish(live_status, f"自动流程结束：{status}。")
        return report


def _run_auto_workflow(root: Path, meta: dict[str, Any], resume: bool = False) -> dict[str, Any]:
    analysis_path = root / "artifacts" / "analysis.json"
    if not analysis_path.exists():
        raise FileNotFoundError("artifacts/analysis.json 不存在，请先上传并完成赛题分析。")

    clear_auto_workflow_control(root)
    require_llm_configured()
    workflow_strategy = get_workflow_strategy(get_llm_settings().get("workflow_strategy"))
    analysis = load_json(analysis_path)
    user_final_problem = meta.get("final_problem") if isinstance(meta.get("final_problem"), dict) else {}
    if user_final_problem.get("id") and user_final_problem.get("source") == "user":
        selected = apply_problem_selection(analysis, user_final_problem["id"], source="user")
        analysis["selected_problem"] = {
            "id": selected.get("id", ""),
            "title": selected.get("title", ""),
            "source": "user",
        }
        save_json(analysis_path, analysis)
    clear_legacy_modeling_artifacts(meta)
    previous_auto_workflow_error = meta.get("auto_workflow_error")
    report: dict[str, Any] = {
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "project_id": meta.get("id"),
        "project_name": meta.get("name"),
        "recommended_problem": analysis.get("recommended_problem", {}),
        "mode": "llm_code_results",
        "workflow_strategy": public_workflow_strategy(workflow_strategy["id"]),
        "steps": [],
        "artifacts": {},
        "resume": bool(resume),
    }
    if previous_auto_workflow_error:
        report["previous_auto_workflow_error"] = previous_auto_workflow_error
    if resume:
        previous_steps = load_resumable_steps(root)
        if previous_steps:
            report["steps"] = previous_steps
            report["resumed_completed_steps"] = len(previous_steps)
        completed_ids = {str(step.get("id")) for step in report["steps"] if isinstance(step, dict)}
        reusable_planning = reusable_llm_planning_artifacts(root, meta)
        if reusable_planning and "llm_planning" not in completed_ids:
            now = datetime.now().isoformat(timespec="seconds")
            report["steps"].append(
                {
                    "id": "llm_planning",
                    "title": "大模型当场分析、选题与代码求解规划",
                    "status": "success",
                    "success": True,
                    "required": True,
                    "started_at": now,
                    "finished_at": now,
                    "duration_seconds": 0.0,
                    "detail": "已复用上次成功生成的 LLM 求解规划，跳过重复请求。",
                    "artifacts": reusable_planning,
                }
            )
            update_artifacts(meta, reusable_planning)
            meta["llm_solution_status"] = "planning_success"
            meta["paper_fill_status"] = "waiting_for_computed_results"

    meta["auto_workflow_status"] = "running"
    meta["auto_workflow_mode"] = "llm_code_results"
    meta["workflow_strategy"] = workflow_strategy["id"]
    meta["workflow_strategy_label"] = workflow_strategy["label"]
    meta.pop("auto_workflow_error", None)
    meta.pop("last_failure_diagnosis", None)
    save_json(root / "metadata.json", meta)

    def llm_planning_step() -> dict[str, Any]:
        metadata_path = root / "metadata.json"
        metadata = load_json(metadata_path) if metadata_path.exists() else {}
        paper_options = metadata.get("paper_options", {}) if isinstance(metadata, dict) else {}
        artifacts = run_llm_planning_solution(root, analysis, paper_options)
        selection = load_llm_final_selection(root, artifacts)
        user_selected = meta.get("final_problem") if isinstance(meta.get("final_problem"), dict) else {}
        if user_selected.get("id") and user_selected.get("source") == "user":
            final_problem = {
                "id": user_selected.get("id", ""),
                "title": user_selected.get("title", ""),
                "reason": user_selected.get("reason", "用户手动确认选题，LLM 输出不得覆盖。"),
                "source": "user",
            }
            if selection:
                report["llm_suggested_problem"] = {
                    "id": selection.get("final_problem_id", ""),
                    "title": selection.get("final_problem_title", ""),
                    "reason": selection.get("reason", ""),
                    "source": "llm_only",
                }
            report["final_problem"] = final_problem
            report["recommended_problem"] = final_problem
            meta["final_problem"] = final_problem
        elif selection:
            final_problem = {
                "id": selection.get("final_problem_id", ""),
                "title": selection.get("final_problem_title", ""),
                "reason": normalize_auto_selection_reason(selection.get("reason", "")),
                "source": "llm_only",
            }
            report["final_problem"] = final_problem
            report["recommended_problem"] = final_problem
            meta["final_problem"] = final_problem
        update_artifacts(meta, artifacts)
        meta["llm_solution_status"] = "planning_success"
        meta["paper_fill_status"] = "waiting_for_computed_results"
        return {"success": True, "detail": "大模型已完成选题确认、子问题拆解和代码求解规划；尚未撰写论文。", "artifacts": artifacts}

    def computed_solution_step() -> dict[str, Any]:
        metadata_path = root / "metadata.json"
        metadata = load_json(metadata_path) if metadata_path.exists() else {}
        paper_options = metadata.get("paper_options", {}) if isinstance(metadata, dict) else {}
        analysis_for_code = load_json(analysis_path) if analysis_path.exists() else dict(analysis)
        final_problem = metadata.get("final_problem") if isinstance(metadata.get("final_problem"), dict) else {}
        if final_problem.get("id"):
            selected = apply_problem_selection(
                analysis_for_code,
                str(final_problem.get("id")),
                source=str(final_problem.get("source") or "workflow"),
            )
            analysis_for_code["selected_problem"] = {
                "id": selected.get("id", ""),
                "title": selected.get("title", ""),
                "source": final_problem.get("source") or "workflow",
            }
            save_json(analysis_path, analysis_for_code)
        repair_context = build_auto_solver_repair_context(
            root,
            metadata,
            report,
            resume=resume,
            previous_error=previous_auto_workflow_error,
        )
        artifacts = run_code_result_pipeline(
            root,
            analysis_for_code,
            paper_options,
            integrate_paper=False,
            resume=resume,
            repair_context=repair_context,
            workflow_strategy=workflow_strategy["id"],
        )
        update_artifacts(meta, artifacts)
        meta["computed_solution_status"] = "success"
        meta["paper_fill_status"] = "waiting_for_paper_generation"
        return {
            "success": True,
            "detail": "已根据 LLM 求解规范生成并运行代码；每个子问题的结果表和图片完整性检查已通过，下一步才开始撰写论文。",
            "artifacts": artifacts,
        }

    def paper_generation_step() -> dict[str, Any]:
        metadata_path = root / "metadata.json"
        metadata = load_json(metadata_path) if metadata_path.exists() else {}
        paper_options = metadata.get("paper_options", {}) if isinstance(metadata, dict) else {}
        analysis_for_paper = load_json(analysis_path) if analysis_path.exists() else dict(analysis)
        final_problem = metadata.get("final_problem") if isinstance(metadata.get("final_problem"), dict) else {}
        if final_problem.get("id"):
            selected = apply_problem_selection(
                analysis_for_paper,
                str(final_problem.get("id")),
                source=str(final_problem.get("source") or "workflow"),
            )
            analysis_for_paper["selected_problem"] = {
                "id": selected.get("id", ""),
                "title": selected.get("title", ""),
                "source": final_problem.get("source") or "workflow",
            }
            save_json(analysis_path, analysis_for_paper)
        paper_artifacts = run_llm_only_solution(root, analysis_for_paper, paper_options)
        result_artifacts = integrate_existing_code_results(root, analysis_for_paper, paper_options)
        artifacts = {**paper_artifacts, **result_artifacts}
        update_artifacts(meta, artifacts)
        meta["llm_solution_status"] = "success"
        meta["paper_fill_status"] = "success"
        return {
            "success": True,
            "detail": "代码求解完整性检查通过后，已生成论文并把计算结果、图表和模型检验回填到对应章节。",
            "artifacts": artifacts,
        }

    def compile_step() -> dict[str, Any]:
        result = compile_latex(root)
        artifacts = {"latex_log": result.get("log", "")}
        if result.get("pdf"):
            artifacts["paper_pdf"] = result["pdf"]
        if result.get("docx"):
            artifacts["paper_docx"] = result["docx"]
        if result.get("word_log"):
            artifacts["word_export_log"] = result["word_log"]
        update_artifacts(meta, artifacts)
        meta["compile_status"] = "success" if result.get("success") else "failed"
        return {
            "success": bool(result.get("success")),
            "detail": "PDF 与 Word 导出完成。" if result.get("success") else "PDF 编译未通过，已保留编译日志和 Word 导出日志。",
            "result": result,
        }

    def code_graph_step() -> dict[str, Any]:
        artifacts = write_code_graph_report(root)
        update_artifacts(meta, artifacts)
        return {"success": True, "detail": "已生成本地代码图谱，包含求解脚本入口、符号、导入和调用关系。", "artifacts": artifacts}

    def review_step() -> dict[str, Any]:
        artifacts = review_paper(root)
        update_artifacts(meta, artifacts)
        meta["paper_review_status"] = "success"
        review_json = load_json(root / "artifacts" / "paper_review.json")
        return {
            "success": review_json.get("overall", {}).get("status") != "fail",
            "detail": "论文质量审查完成。",
            "overall": review_json.get("overall", {}),
            "artifacts": artifacts,
        }

    def support_step() -> dict[str, Any]:
        archive = make_support_zip(root)
        relative = archive.relative_to(root).as_posix()
        update_artifacts(meta, {"support_package": relative})
        return {"success": archive.exists(), "detail": "支撑材料包已准备。", "path": relative}

    def skill_context_step() -> dict[str, Any]:
        artifacts = write_backend_skill_report(root)
        update_artifacts(meta, artifacts)
        return {"success": True, "detail": "GitHub 数学建模、科研写作与学术诚信技能库已注入后端上下文。", "artifacts": artifacts}

    def attachment_profile_step() -> dict[str, Any]:
        artifacts = build_attachment_profile(root, analysis)
        update_artifacts(meta, artifacts)
        profile_path = root / "artifacts" / "attachment_profile.json"
        profile = load_json(profile_path) if profile_path.exists() else {}
        summary = profile.get("summary", {}) if isinstance(profile, dict) else {}
        kind_counts = summary.get("kind_counts", {}) if isinstance(summary, dict) else {}
        return {
            "success": True,
            "detail": (
                f"已用 {profile.get('worker_count', 0) if isinstance(profile, dict) else 0} 个线程并发生成附件画像，"
                f"覆盖 {profile.get('profiled_count', 0) if isinstance(profile, dict) else 0} 个文件；"
                f"数据/文档分布：{kind_counts}。"
            ),
            "artifacts": artifacts,
        }

    steps: list[tuple[str, str, StepFn, bool]] = [
        ("backend_skills", "GitHub 技能库与诚信门禁上下文注入", skill_context_step, False),
        ("attachment_profile", "并发附件画像与字段缓存", attachment_profile_step, False),
        ("llm_planning", "大模型当场分析、选题与代码求解规划", llm_planning_step, True),
        ("computed_solution", "LLM 规划代码求解、运行结果、分问题与图表完整性校验", computed_solution_step, True),
        ("paper_generation", "完整解题通过后生成论文并回填图表结果", paper_generation_step, True),
        ("code_graph", "本地代码图谱与影响关系分析", code_graph_step, False),
        ("latex_compile", "LaTeX 双轮编译与 Word 导出", compile_step, False),
        ("paper_review", "论文质量审查", review_step, False),
        ("support_package", "支撑材料打包", support_step, False),
    ]
    completed_for_resume = {
        str(step.get("id"))
        for step in report.get("steps", [])
        if step.get("status") in {"success", "warning"}
    }
    for step_id, title, fn, required in steps:
        if resume and step_id in completed_for_resume:
            continue
        try:
            ensure_not_cancelled(root)
            run_step(root, meta, report, step_id, title, fn, required=required)
            save_json(root / "metadata.json", meta)
            ensure_not_cancelled(root)
        except AutoWorkflowCancelled as exc:
            append_cancelled_step(root, meta, report, str(exc))
            return finalize_report(root, meta, report)
        if report["steps"][-1].get("status") == "failed" and required:
            return finalize_report(root, meta, report)

    return finalize_report(root, meta, report)


def run_step(
    root: Path,
    meta: dict[str, Any],
    report: dict[str, Any],
    step_id: str,
    title: str,
    fn: StepFn,
    required: bool,
) -> None:
    started = time.time()
    item: dict[str, Any] = {
        "id": step_id,
        "title": title,
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "required": required,
        "status": "running",
        "detail": "正在执行该阶段。",
    }
    write_progress(root, meta, report, current_step=item)
    try:
        ensure_not_cancelled(root)
        result = fn()
        success = bool(result.get("success", True))
        item.update(result)
        item["status"] = "success" if success else "warning"
    except AutoWorkflowCancelled:
        raise
    except Exception as exc:
        item["status"] = "failed" if required else "warning"
        item["success"] = False
        item["detail"] = f"{type(exc).__name__}: {exc}"
        diagnosis = load_failure_diagnosis(root) or diagnose_auto_workflow_exception(exc, step_id)
        if diagnosis:
            item["failure_diagnosis"] = diagnosis
            meta["last_failure_diagnosis"] = compact_failure_diagnosis(diagnosis)
            meta["auto_workflow_repair_hint"] = meta["last_failure_diagnosis"].get(
                "suggested_action",
                "点击继续生成，系统会基于上次失败诊断继续自动修复。",
            )
        error_log = root / "artifacts" / f"auto_workflow_error_{step_id}.log"
        error_log.parent.mkdir(parents=True, exist_ok=True)
        error_log.write_text(
            "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)),
            encoding="utf-8",
        )
        error_relative = error_log.relative_to(root).as_posix()
        item["error_log"] = error_relative
        item.setdefault("artifacts", {})[f"{step_id}_error_log"] = error_relative
        update_artifacts(meta, {f"{step_id}_error_log": error_relative})
        meta["auto_workflow_error"] = item["detail"]
    item["duration_seconds"] = round(time.time() - started, 2)
    item["finished_at"] = datetime.now().isoformat(timespec="seconds")
    report["steps"].append(item)
    write_progress(root, meta, report, current_step=None)


def write_progress(
    root: Path,
    meta: dict[str, Any],
    report: dict[str, Any],
    current_step: dict[str, Any] | None,
) -> None:
    total = AUTO_WORKFLOW_TOTAL_STEPS
    completed = len(report.get("steps", []))
    progress = {
        "status": "running" if current_step else "between_steps",
        "started_at": report.get("started_at"),
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "workflow_strategy": report.get("workflow_strategy") or {},
        "current_step": compact_step(current_step) if current_step else None,
        "steps": [compact_step(step) for step in report.get("steps", [])],
        "completed_steps": completed,
        "total_steps": total,
        "percent": min(100, round((completed + (0.35 if current_step else 0)) / total * 100)),
        "cancel_requested": is_cancel_requested(root),
        "can_resume": False,
        "last_failure_diagnosis": meta.get("last_failure_diagnosis", {}),
        "resume_hint": meta.get("auto_workflow_repair_hint", ""),
    }
    meta["auto_workflow_progress"] = progress
    save_json(root / "artifacts" / "auto_workflow_progress.json", progress)
    save_json(root / "metadata.json", meta)


def compact_step(step: dict[str, Any] | None) -> dict[str, Any] | None:
    if not step:
        return None
    return {
        "id": step.get("id"),
        "title": step.get("title"),
        "status": step.get("status"),
        "detail": step.get("detail", ""),
        "required": step.get("required", False),
        "started_at": step.get("started_at"),
        "finished_at": step.get("finished_at"),
        "duration_seconds": step.get("duration_seconds"),
        "error_log": step.get("error_log", ""),
        "failure_diagnosis": step.get("failure_diagnosis") if isinstance(step.get("failure_diagnosis"), dict) else {},
    }


def load_failure_diagnosis(root: Path) -> dict[str, Any]:
    for relative in [
        "artifacts/computed_solution_status.json",
        "artifacts/computed_solution_completeness.json",
        "artifacts/computed_solver_repair.json",
    ]:
        if not (root / relative).exists():
            continue
        try:
            payload = load_json(root / relative)
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue
        diagnosis = payload.get("failure_diagnosis")
        if isinstance(diagnosis, dict) and diagnosis.get("category"):
            return diagnosis
        latest = payload.get("latest_attempt")
        if isinstance(latest, dict):
            diagnosis = latest.get("failure_diagnosis")
            if isinstance(diagnosis, dict) and diagnosis.get("category"):
                return diagnosis
    return {}


def diagnose_auto_workflow_exception(exc: Exception, step_id: str) -> dict[str, Any]:
    text = f"{type(exc).__name__}: {exc}"
    lower = text.lower()
    llm_markers = ["llm api", "base url", "chat/completions", "api key", "model", "模型", "服务商"]
    if ("not found" in lower or "http 404" in lower) and any(marker in lower for marker in llm_markers):
        return {
            "category": "llm_api_not_found",
            "label": "LLM 接口或模型不可用",
            "stage": step_id,
            "severity": "fatal",
            "repair_focus": "检查 AI 设置中的 Base URL 和模型名。",
            "suggested_action": (
                "在左侧 AI 设置中填写服务商的 OpenAI 兼容基础地址，不要包含 /chat/completions；"
                "确认模型名是当前 API Key 可调用的真实模型后，点击继续生成。"
            ),
            "evidence": text[:700],
        }
    if "api key" in lower or "401" in lower or "403" in lower:
        return {
            "category": "llm_auth",
            "label": "LLM 密钥或权限异常",
            "stage": step_id,
            "severity": "fatal",
            "repair_focus": "检查 API Key、额度和模型调用权限。",
            "suggested_action": "在左侧 AI 设置中更新有效 API Key，并确认账号有权限调用当前模型后继续生成。",
            "evidence": text[:700],
        }
    return {}


def compact_failure_diagnosis(diagnosis: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(diagnosis, dict) or not diagnosis.get("category"):
        return {}
    compact = {
        "category": diagnosis.get("category"),
        "label": diagnosis.get("label") or diagnosis.get("category"),
        "stage": diagnosis.get("stage", ""),
        "severity": diagnosis.get("severity", ""),
        "repair_focus": diagnosis.get("repair_focus", ""),
        "suggested_action": diagnosis.get("suggested_action", ""),
    }
    evidence = str(diagnosis.get("evidence") or "").strip()
    if evidence:
        compact["evidence"] = evidence[:700]
    return {key: value for key, value in compact.items() if value}


def request_auto_workflow_cancel(root: Path, meta: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "cancel_requested": True,
        "requested_at": datetime.now().isoformat(timespec="seconds"),
        "reason": "user_requested",
    }
    save_json(root / CONTROL_RELATIVE, payload)
    meta["auto_workflow_status"] = "cancel_requested"
    meta["auto_workflow_cancel_requested_at"] = payload["requested_at"]
    save_json(root / "metadata.json", meta)
    return payload


def clear_auto_workflow_control(root: Path) -> None:
    path = root / CONTROL_RELATIVE
    if path.exists():
        try:
            path.unlink()
        except OSError:
            save_json(path, {"cancel_requested": False, "cleared_at": datetime.now().isoformat(timespec="seconds")})


def is_cancel_requested(root: Path) -> bool:
    path = root / CONTROL_RELATIVE
    if not path.exists():
        return False
    try:
        payload = load_json(path)
    except Exception:
        return False
    return bool(isinstance(payload, dict) and payload.get("cancel_requested"))


def ensure_not_cancelled(root: Path) -> None:
    if is_cancel_requested(root):
        raise AutoWorkflowCancelled("用户已请求中断自动流程；当前阶段结束后已停止，可点击继续生成从断点恢复。")


def append_cancelled_step(root: Path, meta: dict[str, Any], report: dict[str, Any], detail: str) -> None:
    item = {
        "id": "cancelled",
        "title": "用户中断流程",
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "finished_at": datetime.now().isoformat(timespec="seconds"),
        "required": False,
        "status": "cancelled",
        "success": False,
        "detail": detail,
        "duration_seconds": 0,
    }
    report.setdefault("steps", []).append(item)
    write_progress(root, meta, report, current_step=None)


def build_auto_solver_repair_context(
    root: Path,
    metadata: dict[str, Any],
    report: dict[str, Any],
    *,
    resume: bool,
    previous_error: Any = None,
) -> dict[str, Any]:
    failed_steps = [
        {
            "id": step.get("id"),
            "title": step.get("title"),
            "status": step.get("status"),
            "detail": step.get("detail"),
            "error_log": step.get("error_log"),
        }
        for step in report.get("steps", [])
        if isinstance(step, dict) and step.get("status") in {"failed", "warning", "cancelled"}
    ]
    context: dict[str, Any] = {
        "source": "auto_workflow",
        "resume": bool(resume),
        "previous_auto_workflow_error": previous_error,
        "workflow_status": metadata.get("auto_workflow_status") if isinstance(metadata, dict) else "",
        "workflow_strategy": metadata.get("workflow_strategy") if isinstance(metadata, dict) else "",
        "computed_solution_status": metadata.get("computed_solution_status") if isinstance(metadata, dict) else "",
        "paper_fill_status": metadata.get("paper_fill_status") if isinstance(metadata, dict) else "",
        "final_problem": metadata.get("final_problem") if isinstance(metadata, dict) else {},
        "failed_or_warning_steps": failed_steps[-8:],
        "current_report_steps": [
            {
                "id": step.get("id"),
                "status": step.get("status"),
                "detail": step.get("detail"),
                "error_log": step.get("error_log"),
            }
            for step in report.get("steps", [])[-8:]
            if isinstance(step, dict)
        ],
    }
    log_paths = [root / "artifacts" / "auto_workflow_error_computed_solution.log"]
    artifacts_dir = root / "artifacts"
    if artifacts_dir.exists():
        log_paths.extend(sorted(artifacts_dir.glob("auto_workflow_error_*.log")))
    logs: list[dict[str, Any]] = []
    seen: set[str] = set()
    for path in log_paths:
        if not path.exists() or not path.is_file():
            continue
        try:
            relative = path.relative_to(root).as_posix()
        except ValueError:
            continue
        if relative in seen:
            continue
        seen.add(relative)
        logs.append({"path": relative, "tail": read_text_tail(path, 6000)})
    if logs:
        context["workflow_error_logs"] = logs[-8:]
        context["has_failure"] = True
    if previous_error:
        context["has_failure"] = True
    return context


def read_text_tail(path: Path, max_chars: int) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")[-max_chars:]


def load_resumable_steps(root: Path) -> list[dict[str, Any]]:
    candidates = [
        root / "artifacts" / "auto_workflow_report.json",
        root / "artifacts" / "auto_workflow_progress.json",
    ]
    for path in candidates:
        if not path.exists():
            continue
        try:
            payload = load_json(path)
        except Exception:
            continue
        steps = payload.get("steps") if isinstance(payload, dict) else []
        if not isinstance(steps, list):
            continue
        reusable = []
        for step in steps:
            if not isinstance(step, dict):
                continue
            if step.get("status") in {"success", "warning"} and step.get("id") != "cancelled":
                reusable.append(step)
            else:
                break
        if reusable:
            return reusable
    return []


def reusable_llm_planning_artifacts(root: Path, meta: dict[str, Any]) -> dict[str, str]:
    artifacts = meta.get("artifacts") if isinstance(meta.get("artifacts"), dict) else {}
    candidates: dict[str, str] = {}
    for key, fallback in LLM_PLANNING_ARTIFACT_KEYS.items():
        value = str(artifacts.get(key) or fallback or "").strip()
        if value:
            candidates[key] = value
    required = candidates.get("llm_full_solution_json", "")
    if not required or not (root / required).exists():
        return {}
    return {key: value for key, value in candidates.items() if value and (root / value).exists()}


def update_artifacts(meta: dict[str, Any], artifacts: dict[str, str]) -> None:
    clean = {key: value for key, value in artifacts.items() if value}
    if clean:
        meta.setdefault("artifacts", {}).update(clean)


def clear_legacy_modeling_artifacts(meta: dict[str, Any]) -> None:
    artifacts = meta.get("artifacts")
    if isinstance(artifacts, dict):
        for key in LEGACY_MODELING_ARTIFACT_KEYS:
            artifacts.pop(key, None)
    for key in ["modeling_status", "specialized_status"]:
        meta.pop(key, None)


def load_llm_final_selection(root: Path, artifacts: dict[str, str]) -> dict[str, Any]:
    relative = artifacts.get("llm_full_solution_json")
    if not relative:
        return {}
    path = root / relative
    if not path.exists():
        return {}
    payload = load_json(path)
    sections = payload.get("sections") if isinstance(payload, dict) else {}
    selection = sections.get("selection") if isinstance(sections, dict) else {}
    return selection if isinstance(selection, dict) else {}


def normalize_auto_selection_reason(reason: Any) -> str:
    text = str(reason or "").strip()
    replacements = {
        "用户已确认选择": "大模型自动推荐选择",
        "用户确认选择": "大模型自动推荐选择",
        "用户已确认": "大模型自动推荐",
        "用户确认": "大模型自动推荐",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text


def finalize_report(root: Path, meta: dict[str, Any], report: dict[str, Any]) -> dict[str, Any]:
    report["finished_at"] = datetime.now().isoformat(timespec="seconds")
    report["overall_status"] = overall_status(report["steps"])
    report["artifacts"] = meta.get("artifacts", {})
    if report["overall_status"] == "success":
        meta.pop("last_failure_diagnosis", None)
        meta.pop("auto_workflow_repair_hint", None)
    elif not meta.get("last_failure_diagnosis"):
        for step in reversed(report.get("steps", [])):
            diagnosis = step.get("failure_diagnosis") if isinstance(step, dict) else {}
            if isinstance(diagnosis, dict) and diagnosis.get("category"):
                meta["last_failure_diagnosis"] = compact_failure_diagnosis(diagnosis)
                break
    if meta.get("last_failure_diagnosis"):
        diagnosis = meta["last_failure_diagnosis"]
        meta["auto_workflow_repair_hint"] = diagnosis.get("suggested_action") or "点击继续生成，系统会基于上次失败诊断继续自动修复。"

    json_path = root / "artifacts" / "auto_workflow_report.json"
    md_path = root / "artifacts" / "auto_workflow_report.md"
    save_json(json_path, report)
    md_path.write_text(render_auto_report(report), encoding="utf-8")
    update_artifacts(
        meta,
        {
            "auto_workflow_report": "artifacts/auto_workflow_report.md",
            "auto_workflow_report_json": "artifacts/auto_workflow_report.json",
        },
    )
    update_artifacts(meta, write_performance_health_report(root, meta))
    report["artifacts"] = meta.get("artifacts", {})
    save_json(json_path, report)
    md_path.write_text(render_auto_report(report), encoding="utf-8")
    make_support_zip(root)
    meta["auto_workflow_status"] = report["overall_status"]
    meta["auto_workflow_progress"] = {
        "status": report["overall_status"],
        "started_at": report.get("started_at"),
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "workflow_strategy": report.get("workflow_strategy") or {},
        "current_step": None,
        "steps": [compact_step(step) for step in report.get("steps", [])],
        "completed_steps": len(report.get("steps", [])),
        "total_steps": AUTO_WORKFLOW_TOTAL_STEPS,
        "percent": 100,
        "cancel_requested": is_cancel_requested(root),
        "can_resume": report["overall_status"] in {"failed", "cancelled", "completed_with_warnings"},
        "last_failure_diagnosis": meta.get("last_failure_diagnosis", {}),
        "resume_hint": meta.get("auto_workflow_repair_hint", ""),
    }
    save_json(root / "artifacts" / "auto_workflow_progress.json", meta["auto_workflow_progress"])
    save_json(root / "metadata.json", meta)
    return report


def overall_status(steps: list[dict[str, Any]]) -> str:
    if any(item.get("status") == "cancelled" for item in steps):
        return "cancelled"
    required_failed = any(item.get("required") and item.get("status") == "failed" for item in steps)
    if required_failed:
        return "failed"
    if any(item.get("status") in {"failed", "warning"} for item in steps):
        return "completed_with_warnings"
    return "success"


def render_auto_report(report: dict[str, Any]) -> str:
    rec = report.get("recommended_problem") or {}
    lines = [
        "# 自动解题与论文生成报告",
        "",
        f"- 项目：{report.get('project_name') or report.get('project_id')}",
        f"- 最终选题：{rec.get('id', '-')} 题 {rec.get('title', '')}",
        f"- 开始时间：{report.get('started_at')}",
        f"- 完成时间：{report.get('finished_at')}",
        f"- 总体状态：{report.get('overall_status')}",
        f"- 执行模式：{report.get('mode', 'llm_only')}",
        f"- 求解策略：{(report.get('workflow_strategy') or {}).get('label', '-')} / {(report.get('workflow_strategy') or {}).get('id', '-')}",
        "",
        "## 自动流程",
    ]
    for step in report.get("steps", []):
        status = {
            "success": "成功",
            "warning": "需注意",
            "failed": "失败",
        }.get(step.get("status"), step.get("status"))
        lines.append(f"- **{step.get('title')}**：{status}，耗时 {step.get('duration_seconds')} 秒。{step.get('detail', '')}")
        diagnosis = step.get("failure_diagnosis") if isinstance(step.get("failure_diagnosis"), dict) else {}
        if diagnosis:
            lines.append(f"  - 失败类型：{diagnosis.get('label') or diagnosis.get('category')}；修复重点：{diagnosis.get('repair_focus')}")
            if diagnosis.get("suggested_action"):
                lines.append(f"  - 建议动作：{diagnosis.get('suggested_action')}")
    lines.extend(["", "## 关键输出"])
    artifacts = report.get("artifacts") or {}
    for key, value in artifacts.items():
        lines.append(f"- {key}: `{value}`")
    if not artifacts:
        lines.append("- 暂无输出文件。")
    lines.extend(
        [
            "",
            "## 使用说明",
            "- 若编译或审查出现警告，优先查看 `论文审查报告` 和 `编译日志`。",
            "- 当前自动流程为 LLM 当场分析 + 代码求解执行 + 计算结果整合进论文，不使用旧的本地基线/专项建模路径。",
            "- 论文中的新增精确数值应优先追溯到 `results/computed_manifest.json`、结果表、图片和运行日志。",
        ]
    )
    return "\n".join(lines)
