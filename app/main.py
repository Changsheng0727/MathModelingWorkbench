from __future__ import annotations

import asyncio
import platform
import subprocess
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.services.analyzer import apply_problem_selection, build_analysis
from app.services.analysis_progress import AnalysisProgress, load_analysis_progress
from app.services.auto_workflow import diagnose_auto_workflow_exception, request_auto_workflow_cancel, run_auto_workflow
from app.services.auto_workflow_jobs import (
    cancel_queued_auto_workflow_job,
    configure_auto_workflow_capacity,
    get_auto_workflow_job,
    get_project_auto_workflow_job,
    list_auto_workflow_jobs,
    start_auto_workflow_job,
)
from app.services.backend_skills import (
    list_backend_skills,
    list_model_method_routes,
    list_model_selection_rubric,
    list_modeling_process_gates,
    list_standard_paper_checklist,
    list_standard_paper_workflow,
    write_backend_skill_report,
)
from app.services.code_solution import run_code_result_pipeline
from app.services.code_graph import write_code_graph_report
from app.services.capacity_autotune import list_capacity_autotune_events, record_capacity_autotune_event
from app.services.capacity_settings import load_capacity_settings, save_capacity_settings
from app.services.delivery_batch import build_batch_delivery_packages, list_delivery_package_batches
from app.services.delivery_batch_jobs import (
    configure_delivery_batch_job_capacity,
    get_delivery_batch_job,
    list_delivery_batch_jobs,
    start_delivery_batch_job,
)
from app.services.delivery_package import DELIVERY_PACKAGE_MANIFEST_JSON_RELATIVE, write_delivery_package
from app.services.delivery_readiness import DELIVERY_READINESS_JSON_RELATIVE, write_delivery_readiness_report
from app.services.diagnostic_refresh import refresh_diagnostic_assets
from app.services.executor import detect_environments
from app.services.experience_center import build_experience_center
from app.services.extractors import save_upload, unpack_upload, validate_upload_name
from app.services.extractors import safe_folder_target
from app.services.growth_metrics import build_growth_metrics, is_deliverable
from app.services.llm_assistant import (
    MODEL_ASSISTANT_PROGRESS_RELATIVE,
    call_chat_completion,
    run_baseline_llm_review,
    run_full_llm_refresh,
    run_custom_model_assistance,
    run_problem_structure_enhancement,
    run_problem_llm_analysis,
    run_specialized_llm_review,
    write_material_passport,
)
from app.services.llm_stream import bind_llm_stream, load_llm_live_stream
from app.services.llm_settings import clear_llm_settings, get_llm_settings, save_llm_settings
from app.services.modeling import generate_modeling_script, run_modeling_script
from app.services.paper import write_artifacts
from app.services.paper_fill import fill_paper_with_results
from app.services.performance_health import write_performance_health_report
from app.services.parsers import extract_all_document_text, inventory_files
from app.services.project_readiness import build_project_readiness
from app.services.repair_campaign import list_repair_campaigns, start_repair_campaign
from app.services.repair_center import REPAIR_BRIEFING_JSON_RELATIVE, write_repair_briefing
from app.services.reviewer import review_paper
from app.services.runner import compile_latex
from app.services.specialized import generate_specialized_script, run_specialized_script
from app.services.store import (
    attach_project_artifact_fields,
    attach_project_runtime_fields,
    create_project,
    list_projects,
    load_json,
    make_support_zip,
    project_metadata_error_stub,
    project_root,
    save_json,
)
from app.services.templates import (
    DEFAULT_TEMPLATE_ID,
    create_template,
    delete_template,
    list_templates,
    validate_template_id,
)
from app.services.trust_center import build_trust_center, has_package
from app.services.trust_export import (
    build_trust_report_export,
    list_trust_report_exports,
    resolve_trust_report_file,
)


app = FastAPI(title="ModelArk", version="0.1.0")
static_dir = Path(__file__).resolve().parent / "static"
next_static_dir = static_dir / "_next"
next_static_dir.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")
app.mount("/_next", StaticFiles(directory=next_static_dir), name="next_static")

MAX_FOLDER_UPLOAD_FILES = 1200
MAX_FOLDER_UPLOAD_BYTES = 500 * 1024 * 1024


class LLMSettingsPayload(BaseModel):
    api_key: str | None = None
    base_url: str | None = None
    model: str | None = None
    workflow_strategy: str | None = None


class PaperOptionsPayload(BaseModel):
    template_id: str | None = None
    target_body_pages: int | None = None


class ModelAssistantPayload(BaseModel):
    problem_ref: str
    model_name: str
    user_goal: str | None = None


class ProblemSelectionPayload(BaseModel):
    problem_id: str


class BatchAutoWorkflowPayload(BaseModel):
    project_ids: list[str]
    mode: str | None = "auto"


class BatchDeliveryPackagePayload(BaseModel):
    force: bool = False
    max_workers: int | None = None


class CapacitySettingsPayload(BaseModel):
    auto_workflow_workers: int | None = None
    delivery_batch_job_workers: int | None = None
    delivery_package_workers: int | None = None


class RepairCampaignPayload(BaseModel):
    queue_resumes: bool = True
    refresh_diagnostics: bool = True
    limit: int | None = 20


@app.get("/")
def index() -> FileResponse:
    return FileResponse(static_dir / "index.html")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/environments")
def environments() -> dict:
    return detect_environments()


@app.get("/api/product/capacity")
def product_capacity_settings() -> dict:
    return {
        "capacity_settings": load_capacity_settings(),
        "auto_jobs": list_auto_workflow_jobs(),
        "delivery_batch_jobs": list_delivery_batch_jobs(),
        "capacity_autotune": list_capacity_autotune_events(),
    }


@app.put("/api/product/capacity")
def update_product_capacity_settings(payload: CapacitySettingsPayload) -> dict:
    settings_payload = payload.model_dump(exclude_none=True) if hasattr(payload, "model_dump") else payload.dict(exclude_none=True)
    settings = save_capacity_settings(settings_payload)
    auto_update = None
    delivery_update = None
    if "auto_workflow_workers" in settings_payload:
        auto_update = configure_auto_workflow_capacity(int(settings.get("auto_workflow_workers") or 2))
    if "delivery_batch_job_workers" in settings_payload:
        delivery_update = configure_delivery_batch_job_capacity(int(settings.get("delivery_batch_job_workers") or 1))
    return {
        "capacity_settings": load_capacity_settings(),
        "auto_update": auto_update or {},
        "delivery_update": delivery_update or {},
        "auto_jobs": list_auto_workflow_jobs(),
        "delivery_batch_jobs": list_delivery_batch_jobs(),
    }


@app.post("/api/product/capacity/autotune")
def autotune_product_capacity() -> dict:
    projects_snapshot = list_projects()
    auto_jobs_before = list_auto_workflow_jobs()
    delivery_jobs_before = list_delivery_batch_jobs()
    settings_before = load_capacity_settings()
    plan = build_capacity_autotune_plan(projects_snapshot, auto_jobs_before, delivery_jobs_before, settings_before)
    updates = plan.get("updates", {}) if isinstance(plan.get("updates"), dict) else {}
    if updates:
        save_capacity_settings(updates)
    auto_update = {}
    delivery_update = {}
    if "auto_workflow_workers" in updates:
        auto_update = configure_auto_workflow_capacity(int(updates["auto_workflow_workers"]))
    if "delivery_batch_job_workers" in updates:
        delivery_update = configure_delivery_batch_job_capacity(int(updates["delivery_batch_job_workers"]))
    settings_after = load_capacity_settings()
    event = record_capacity_autotune_event(plan, settings_after)
    history = list_capacity_autotune_events()
    return {
        "capacity_autotune": event,
        "capacity_autotune_history": history,
        "capacity_settings": settings_after,
        "auto_update": auto_update,
        "delivery_update": delivery_update,
        "auto_jobs": list_auto_workflow_jobs(),
        "delivery_batch_jobs": list_delivery_batch_jobs(),
    }


def build_capacity_autotune_plan(
    projects_snapshot: list[dict],
    auto_jobs: dict,
    delivery_batch_jobs: dict,
    settings: dict,
) -> dict:
    throughput = auto_jobs.get("throughput", {}) if isinstance(auto_jobs.get("throughput"), dict) else {}
    updates: dict[str, int] = {}
    reasons: list[str] = []

    current_auto = int(settings.get("auto_workflow_workers") or auto_jobs.get("capacity") or 2)
    max_auto = int(settings.get("max_auto_workflow_workers") or 8)
    recommended_auto = int(throughput.get("recommended_workers") or current_auto)
    queued_auto = int(auto_jobs.get("queued_count") or 0)
    pressure = float(throughput.get("active_pressure") or 0)
    target_auto = max(current_auto, min(max_auto, recommended_auto))
    if queued_auto and target_auto == current_auto and current_auto < max_auto:
        target_auto = min(max_auto, current_auto + 1)
    if target_auto > current_auto:
        updates["auto_workflow_workers"] = target_auto
        reasons.append(f"自动流程队列压力建议调整到 {target_auto} 个槽位。")

    current_delivery_jobs = int(settings.get("delivery_batch_job_workers") or delivery_batch_jobs.get("capacity") or 1)
    max_delivery_jobs = int(settings.get("max_delivery_batch_job_workers") or 4)
    active_delivery = int(delivery_batch_jobs.get("active_count") or 0)
    queued_delivery = int(delivery_batch_jobs.get("queued_count") or 0)
    target_delivery_jobs = current_delivery_jobs
    if queued_delivery or active_delivery >= current_delivery_jobs:
        target_delivery_jobs = min(max_delivery_jobs, max(current_delivery_jobs + 1, active_delivery + queued_delivery))
    if target_delivery_jobs > current_delivery_jobs:
        updates["delivery_batch_job_workers"] = target_delivery_jobs
        reasons.append(f"交付批处理队列建议调整到 {target_delivery_jobs} 个任务槽。")

    current_package_workers = int(settings.get("delivery_package_workers") or 4)
    max_package_workers = int(settings.get("max_delivery_package_workers") or 8)
    deliverable = [project for project in projects_snapshot if is_deliverable(project)]
    packaged_deliverables = [project for project in deliverable if has_package(project)]
    package_backlog = max(0, len(deliverable) - len(packaged_deliverables))
    target_package_workers = current_package_workers
    if package_backlog >= 8:
        target_package_workers = min(max_package_workers, max(current_package_workers + 2, 6))
    elif package_backlog > 0:
        target_package_workers = min(max_package_workers, max(current_package_workers + 1, 4))
    if target_package_workers > current_package_workers:
        updates["delivery_package_workers"] = target_package_workers
        reasons.append(f"{package_backlog} 个可交付项目正在等待生成交付包。")

    status = "applied" if updates else "already_optimal"
    summary = (
        "容量推荐已应用：" + "；".join(reasons)
        if updates
        else "当前容量已匹配队列压力和打包积压。"
    )
    after = {
        "auto_workflow_workers": updates.get("auto_workflow_workers", current_auto),
        "delivery_batch_job_workers": updates.get("delivery_batch_job_workers", current_delivery_jobs),
        "delivery_package_workers": updates.get("delivery_package_workers", current_package_workers),
    }
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "status": status,
        "summary": summary,
        "updates": updates,
        "reasons": reasons,
        "signals": {
            "auto_queue": queued_auto,
            "active_pressure": pressure,
            "delivery_queue": queued_delivery,
            "delivery_active": active_delivery,
            "package_backlog": package_backlog,
        },
        "before": {
            "auto_workflow_workers": current_auto,
            "delivery_batch_job_workers": current_delivery_jobs,
            "delivery_package_workers": current_package_workers,
        },
        "after": after,
    }


@app.get("/api/product/growth")
def product_growth_metrics() -> dict:
    projects_snapshot = list_projects()
    jobs_snapshot = list_auto_workflow_jobs()
    delivery_batches = list_delivery_package_batches()
    delivery_batch_jobs = list_delivery_batch_jobs()
    growth = build_growth_metrics(projects_snapshot, jobs_snapshot, delivery_batches, delivery_batch_jobs)
    trust = build_trust_center(projects_snapshot, jobs_snapshot, delivery_batch_jobs, delivery_batches)
    growth["trust"] = compact_trust_snapshot(trust)
    return {
        "growth": growth,
        "trust": trust,
    }


@app.get("/api/product/experience")
def product_experience_center() -> dict:
    projects_snapshot = list_projects()
    auto_jobs = list_auto_workflow_jobs()
    delivery_jobs = list_delivery_batch_jobs()
    settings = load_capacity_settings()
    llm_settings = get_llm_settings()
    return {
        "experience": build_experience_center(
            projects_snapshot,
            auto_jobs,
            delivery_jobs,
            settings,
            llm_settings,
        )
    }


@app.get("/api/product/trust")
def product_trust_center() -> dict:
    projects_snapshot = list_projects()
    jobs_snapshot = list_auto_workflow_jobs()
    delivery_batch_jobs = list_delivery_batch_jobs()
    delivery_batches = list_delivery_package_batches()
    return {
        "trust": build_trust_center(projects_snapshot, jobs_snapshot, delivery_batch_jobs, delivery_batches),
        "trust_exports": list_trust_report_exports(),
        "repair_campaigns": list_repair_campaigns(),
    }


def compact_trust_snapshot(trust: dict) -> dict:
    return {
        "generated_at": trust.get("generated_at", ""),
        "status": trust.get("status", ""),
        "label": trust.get("label", ""),
        "score": trust.get("score", 0),
        "summary": trust.get("summary", ""),
        "repair_backlog_count": trust.get("repair_backlog_count", 0),
        "failed_project_count": trust.get("failed_project_count", 0),
        "queued_job_count": trust.get("queued_job_count", 0),
        "hashed_package_count": trust.get("hashed_package_count", 0),
    }


@app.post("/api/product/trust/export")
def product_trust_report_export() -> dict:
    projects_snapshot = list_projects()
    jobs_snapshot = list_auto_workflow_jobs()
    delivery_batch_jobs = list_delivery_batch_jobs()
    delivery_batches = list_delivery_package_batches()
    trust_report = build_trust_report_export(projects_snapshot, jobs_snapshot, delivery_batch_jobs, delivery_batches)
    return {
        "trust_report": trust_report,
        "trust": trust_report.get("trust") or build_trust_center(projects_snapshot, jobs_snapshot, delivery_batch_jobs, delivery_batches),
        "trust_exports": list_trust_report_exports(),
    }


@app.get("/api/product/trust/export")
def list_product_trust_report_exports() -> dict:
    return {"trust_exports": list_trust_report_exports()}


@app.get("/api/product/trust/export/download/{filename}")
def download_product_trust_report(filename: str) -> FileResponse:
    try:
        target = resolve_trust_report_file(filename)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="未找到信任审计导出文件。") from exc
    return FileResponse(target, filename=target.name)


@app.post("/api/product/trust/repair-campaign/start")
def start_product_trust_repair_campaign(payload: RepairCampaignPayload | None = None) -> dict:
    options = payload or RepairCampaignPayload()
    projects_snapshot = list_projects()
    campaign = start_repair_campaign(
        projects_snapshot,
        queue_resumes=bool(options.queue_resumes),
        refresh_diagnostics=bool(options.refresh_diagnostics),
        limit=options.limit or 20,
    )
    projects_after = list_projects()
    jobs_snapshot = list_auto_workflow_jobs()
    delivery_batch_jobs = list_delivery_batch_jobs()
    delivery_batches = list_delivery_package_batches()
    growth = build_growth_metrics(projects_after, jobs_snapshot, delivery_batches, delivery_batch_jobs)
    return {
        "repair_campaign": campaign,
        "repair_campaigns": list_repair_campaigns(),
        "trust": build_trust_center(projects_after, jobs_snapshot, delivery_batch_jobs, delivery_batches),
        "growth": growth,
        "auto_jobs": jobs_snapshot,
        "delivery_batch_jobs": delivery_batch_jobs,
    }


@app.get("/api/product/trust/repair-campaigns")
def list_product_trust_repair_campaigns() -> dict:
    return {"repair_campaigns": list_repair_campaigns()}


@app.post("/api/delivery/packages/batch")
def batch_build_delivery_packages(payload: BatchDeliveryPackagePayload | None = None) -> dict:
    options = payload or BatchDeliveryPackagePayload()
    projects_snapshot = list_projects()
    batch = build_batch_delivery_packages(
        projects_snapshot,
        force=bool(options.force),
        max_workers=options.max_workers or int(load_capacity_settings().get("delivery_package_workers") or 4),
    )
    updated_projects = list_projects()
    delivery_batches = list_delivery_package_batches()
    growth = build_growth_metrics(updated_projects, list_auto_workflow_jobs(), delivery_batches, list_delivery_batch_jobs())
    return {
        "batch": batch,
        "delivery_batches": delivery_batches,
        "growth": growth,
    }


@app.get("/api/delivery/packages/batch")
def list_batch_delivery_package_runs() -> dict:
    return {"delivery_batches": list_delivery_package_batches()}


@app.post("/api/delivery/packages/batch/start")
def start_batch_delivery_package_job(payload: BatchDeliveryPackagePayload | None = None) -> dict:
    options = payload or BatchDeliveryPackagePayload()
    projects_snapshot = list_projects()
    job = start_delivery_batch_job(
        projects_snapshot,
        force=bool(options.force),
        max_workers=options.max_workers or int(load_capacity_settings().get("delivery_package_workers") or 4),
    )
    delivery_batches = list_delivery_package_batches()
    delivery_batch_jobs = list_delivery_batch_jobs()
    growth = build_growth_metrics(projects_snapshot, list_auto_workflow_jobs(), delivery_batches, delivery_batch_jobs)
    return {
        "delivery_batch_job": job,
        "delivery_batch_jobs": delivery_batch_jobs,
        "delivery_batches": delivery_batches,
        "growth": growth,
    }


@app.get("/api/delivery/packages/batch/jobs")
def list_batch_delivery_package_jobs() -> dict:
    return {"delivery_batch_jobs": list_delivery_batch_jobs()}


@app.get("/api/delivery/packages/batch/jobs/{job_id}")
def batch_delivery_package_job(job_id: str) -> dict:
    job = get_delivery_batch_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Delivery batch job not found.")
    return {"delivery_batch_job": job}


@app.get("/api/upload-analysis-progress/{progress_id}")
def upload_analysis_progress(progress_id: str) -> dict:
    progress = load_analysis_progress(progress_id)
    if isinstance(progress, dict) and progress.get("project_id"):
        try:
            root = project_root(str(progress["project_id"]))
            live_stream = load_llm_live_stream(root)
            if live_stream.get("channel") == "upload_analysis":
                progress = dict(progress)
                progress["live_stream"] = live_stream
        except Exception:
            pass
    return {"progress": progress or {}}


@app.get("/api/skills/backend")
def backend_skills() -> dict:
    return {
        "skills": list_backend_skills(),
        "standard_paper_workflow": list_standard_paper_workflow(),
        "standard_paper_checklist": list_standard_paper_checklist(),
        "model_method_routes": list_model_method_routes(),
        "model_selection_rubric": list_model_selection_rubric(),
        "modeling_process_gates": list_modeling_process_gates(),
    }


@app.post("/api/projects/{project_id}/skills/report")
def write_project_backend_skill_report(project_id: str) -> dict:
    try:
        root = project_root(project_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="项目不存在。") from exc
    meta = load_json(root / "metadata.json")
    artifacts = write_backend_skill_report(root)
    meta.setdefault("artifacts", {}).update(artifacts)
    save_json(root / "metadata.json", meta)
    return {"artifacts": artifacts, "project": project_detail(project_id)}


@app.post("/api/projects/{project_id}/codegraph/report")
def write_project_code_graph_report(project_id: str) -> dict:
    try:
        root = project_root(project_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="项目不存在。") from exc
    meta = load_json(root / "metadata.json")
    artifacts = write_code_graph_report(root)
    meta.setdefault("artifacts", {}).update(artifacts)
    save_json(root / "metadata.json", meta)
    return {"artifacts": artifacts, "project": project_detail(project_id)}


@app.get("/api/settings/llm")
def read_llm_settings() -> dict:
    return get_llm_settings()


@app.put("/api/settings/llm")
def update_llm_settings(payload: LLMSettingsPayload) -> dict:
    try:
        return save_llm_settings(payload.api_key, payload.base_url, payload.model, payload.workflow_strategy)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/settings/llm/test")
def test_llm_settings() -> dict:
    settings = get_llm_settings()
    if not settings.get("configured"):
        return {
            "ok": False,
            "status": "requires_api_key",
            "message": "请先填写 API 密钥后再测试连接。",
            "diagnosis": {
                "category": "llm_auth",
                "label": "未配置 API 密钥",
                "suggested_action": "在左侧 AI 设置中填写有效 API Key 后再测试连接。",
            },
        }
    try:
        content = call_chat_completion(
            "请只回复 OK，用于数学建模客户端连接测试。",
            max_tokens=16,
            attempts=1,
            stream_label="测试 AI 连接",
        )
    except Exception as exc:
        diagnosis = diagnose_auto_workflow_exception(exc, "llm_settings_test")
        return {
            "ok": False,
            "status": "failed",
            "message": f"{type(exc).__name__}: {exc}",
            "diagnosis": diagnosis,
            "settings": {
                "base_url": settings.get("base_url", ""),
                "model": settings.get("model", ""),
                "masked_api_key": settings.get("masked_api_key", ""),
            },
        }
    return {
        "ok": True,
        "status": "success",
        "message": "AI 连接测试成功。",
        "sample": content[:80],
        "settings": {
            "base_url": settings.get("base_url", ""),
            "model": settings.get("model", ""),
            "masked_api_key": settings.get("masked_api_key", ""),
        },
    }


@app.delete("/api/settings/llm")
def delete_llm_settings() -> dict:
    return clear_llm_settings()


@app.get("/api/templates")
def read_templates() -> dict:
    return {"templates": list_templates()}


@app.post("/api/templates")
async def upload_template(name: str | None = Form(None), file: UploadFile = File(...)) -> dict:
    if not file.filename:
        raise HTTPException(status_code=400, detail="缺少模板文件名。")
    try:
        record = create_template(name, file.filename, await file.read())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"template": record, "templates": list_templates()}


@app.delete("/api/templates/{template_id}")
def remove_template(template_id: str) -> dict:
    try:
        result = delete_template(template_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {**result, "templates": list_templates()}


def attach_artifacts_safely(meta: dict, artifacts: dict[str, str]) -> None:
    if artifacts:
        meta.setdefault("artifacts", {}).update(artifacts)


def count_files(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(1 for item in path.rglob("*") if item.is_file())


def format_bytes(value: int) -> str:
    size = float(max(value, 0))
    for unit in ["B", "KB", "MB", "GB"]:
        if size < 1024 or unit == "GB":
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024


@app.get("/api/projects")
def projects() -> list[dict]:
    llm_settings = get_llm_settings()
    items = [attach_project_readiness_summary(project, llm_settings) for project in list_projects()]
    items.sort(key=lambda item: str(item.get("project_updated_at") or item.get("created_at") or ""), reverse=True)
    items.sort(key=lambda item: int(item.get("readiness_attention_rank") or 99))
    if items:
        items[0]["default_open"] = True
        items[0]["default_open_reason"] = items[0].get("readiness_attention_reason") or (
            "优先处理" if int(items[0].get("readiness_attention_rank") or 99) <= 20 else "最近更新"
        )
    return items


def attach_project_readiness_summary(project: dict, llm_settings: dict) -> dict:
    project = dict(project)
    root = Path(project.get("root") or project_root(str(project.get("id", ""))))
    project["can_open"] = root.exists()
    project["open_warning"] = "项目元数据异常，可打开项目文件夹修复。" if project.get("metadata_error") else ""
    normalize_project_auto_status_for_summary(root, project)
    analysis = project.get("analysis_summary") if isinstance(project.get("analysis_summary"), dict) else None
    if project.get("analysis_available") and not analysis:
        analysis = {"analysis_available": True}
    readiness = build_project_readiness(
        root,
        project,
        analysis,
        llm_settings=llm_settings,
    )
    project = attach_project_readiness_fields(project, readiness)
    project.pop("root", None)
    return project


def attach_project_readiness_fields(project: dict, readiness: dict) -> dict:
    project["readiness_status"] = readiness.get("status")
    project["readiness_label"] = readiness.get("label")
    project["readiness_score"] = readiness.get("score")
    project["readiness_summary"] = readiness.get("summary")
    action = readiness.get("primary_action", {})
    action = action if isinstance(action, dict) else {}
    project["readiness_action"] = action
    project["readiness_action_id"] = action.get("id", "")
    project["readiness_action_label"] = action.get("label", "")
    project["readiness_action_detail"] = action.get("detail", "")
    action_hint = project_readiness_action_hint(action, project)
    project["readiness_action_hint"] = action_hint
    project["readiness_top_action_id"] = action.get("id", "")
    project["readiness_top_action_label"] = action.get("label", "")
    project["readiness_top_action_detail"] = action.get("detail", "")
    project["readiness_top_action_hint"] = action_hint
    project["readiness_top_action_path"] = action.get("path", "")
    next_step = readiness.get("next_step", {})
    next_step = next_step if isinstance(next_step, dict) else {}
    project["readiness_next_step"] = next_step
    project["readiness_next_step_label"] = next_step.get("label", "")
    project["readiness_next_step_detail"] = next_step.get("detail", "")
    project["readiness_next_step_context"] = next_step.get("context", "")
    project["readiness_next_step_tone"] = next_step.get("tone", "")
    project["readiness_next_step_urgency"] = next_step.get("urgency", "")
    phase = readiness.get("phase", {})
    phase = phase if isinstance(phase, dict) else {}
    project["readiness_phase"] = phase
    project["readiness_phase_label"] = phase.get("label", "")
    project["readiness_phase_detail"] = phase.get("detail", "")
    project["readiness_phase_step"] = phase.get("step", 0)
    project["readiness_phase_total"] = phase.get("total", 0)
    completion = readiness.get("completion", {})
    completion = completion if isinstance(completion, dict) else {}
    project["readiness_completion"] = completion
    project["readiness_completion_label"] = completion.get("label", "")
    todo_items = readiness.get("todo_items", [])
    todo_items = todo_items if isinstance(todo_items, list) else []
    gap_items = [item for item in todo_items if isinstance(item, dict) and item.get("required")]
    warning_todos = [item for item in todo_items if isinstance(item, dict) and not item.get("required")]
    project["readiness_todo_count"] = len(todo_items)
    project["readiness_todo_preview"] = todo_items[:3]
    project["readiness_gap_count"] = len(gap_items)
    project["readiness_gap_preview"] = gap_items[:3]
    project["readiness_warning_todo_count"] = len(warning_todos)
    project["readiness_gap_label"] = project_readiness_gap_label(gap_items, warning_todos)
    project["readiness_required_passed"] = readiness.get("required_passed", 0)
    project["readiness_required_total"] = readiness.get("required_total", 0)
    required_total = int(project["readiness_required_total"] or 0)
    required_passed = int(project["readiness_required_passed"] or 0)
    project["readiness_required_percent"] = round(100 * required_passed / required_total) if required_total else 0
    project["readiness_required_label"] = f"必需 {required_passed}/{required_total}" if required_total else ""
    project["readiness_bucket"] = project_readiness_bucket(project)
    project["readiness_bucket_label"] = project_readiness_bucket_label(project["readiness_bucket"])
    project["readiness_attention_rank"] = project_attention_rank(project)
    project["readiness_attention_reason"] = project_attention_reason(project)
    project["readiness_header_summary"] = project_readiness_header_summary(project)
    project["readiness_header_detail"] = project_readiness_header_detail(project)
    return project


def normalize_project_auto_status_for_summary(root: Path, project: dict) -> None:
    project_id = str(project.get("id") or "")
    active_job = get_project_auto_workflow_job(project_id) if project_id else {}
    if active_job.get("status") in {"queued", "running"}:
        project["auto_workflow_status"] = str(active_job.get("status") or "")
        project["auto_workflow_job_summary"] = str(active_job.get("summary") or "")
        return
    status = str(project.get("auto_workflow_status") or "")
    if status not in {"queued", "running", "between_steps", "cancel_requested"}:
        return
    progress_path = root / "artifacts" / "auto_workflow_progress.json"
    try:
        progress = load_json(progress_path) if progress_path.exists() else project.get("auto_workflow_progress", {})
    except Exception:
        progress = {}
    if auto_progress_is_missing_or_stale(progress):
        project["auto_workflow_status"] = "interrupted"
        project["auto_workflow_repair_hint"] = "上次自动流程已没有后台任务，可点击继续生成。"


def project_readiness_bucket(project: dict) -> str:
    if project.get("metadata_error"):
        return "needs_action"
    auto_status = str(project.get("auto_workflow_status") or "")
    if auto_status in {"queued", "running", "between_steps", "cancel_requested"}:
        return "running"
    if project.get("delivery_package_status") == "success" or project.get("delivery_package_sha256"):
        return "deliverable"
    action = project.get("readiness_action") if isinstance(project.get("readiness_action"), dict) else {}
    if project.get("readiness_status") == "failed" or action.get("id") in {"focus_llm", "focus_upload", "start_auto", "resume_auto"}:
        return "needs_action"
    try:
        score = int(float(project.get("readiness_score") or 0))
    except (TypeError, ValueError):
        score = 0
    if project.get("readiness_status") == "success" or score >= 90:
        return "deliverable"
    return "needs_action" if project.get("readiness_status") == "warning" else "normal"


def project_readiness_bucket_label(bucket: str) -> str:
    return {
        "needs_action": "需处理",
        "running": "运行中",
        "deliverable": "可交付",
        "normal": "普通",
    }.get(bucket, "普通")


def project_readiness_gap_label(gap_items: list[dict], warning_todos: list[dict]) -> str:
    if gap_items:
        labels = "、".join(filter(None, (str(item.get("label") or item.get("id") or "").strip() for item in gap_items[:3])))
        suffix = "等" if len(gap_items) > 3 else ""
        return f"必需缺口 {len(gap_items)} 项" + (f"：{labels}{suffix}" if labels else "")
    if warning_todos:
        labels = "、".join(filter(None, (str(item.get("label") or item.get("id") or "").strip() for item in warning_todos[:3])))
        suffix = "等" if len(warning_todos) > 3 else ""
        return f"建议处理 {len(warning_todos)} 项" + (f"：{labels}{suffix}" if labels else "")
    return ""


def project_readiness_header_summary(project: dict) -> str:
    phase_label = str(project.get("readiness_phase_label") or "").strip()
    try:
        phase_step = int(project.get("readiness_phase_step") or 0)
        phase_total = int(project.get("readiness_phase_total") or 0)
    except (TypeError, ValueError):
        phase_step = 0
        phase_total = 0
    phase = f"阶段 {phase_step}/{phase_total}：{phase_label}" if phase_label and phase_step and phase_total else phase_label
    gap = str(project.get("readiness_gap_label") or project.get("readiness_attention_reason") or "").strip()
    action = str(project.get("readiness_action_label") or "").strip()
    action_text = f"下一步：{action}" if action else ""
    return " · ".join(part for part in [phase, gap, action_text] if part)


def project_readiness_header_detail(project: dict) -> str:
    return " · ".join(
        part
        for part in [
            str(project.get("readiness_phase_detail") or "").strip(),
            str(project.get("readiness_action_hint") or "").strip(),
        ]
        if part
    )


def project_readiness_action_hint(action: dict, project: dict) -> str:
    action_id = str(action.get("id") or project.get("readiness_action_id") or "")
    detail = str(action.get("detail") or project.get("readiness_action_detail") or "").strip()
    hints = {
        "focus_llm": "保存接口后才能调用大模型。",
        "focus_upload": "上传赛题包并完成材料分析。",
        "open_problems": "确认最终题号再开始求解。",
        "start_auto": "启动代码求解、图表生成和论文回填。",
        "watch_auto": "查看后台自动流程进度。",
        "resume_auto": "从失败或中断处继续生成。",
        "open_outputs": "查看论文、日志和结果文件。",
        "compile": "生成或修复 PDF 论文。",
        "refresh_delivery": "检查论文、结果和支撑材料。",
        "build_delivery_package": "生成最终提交压缩包。",
        "open_project_root": "打开本地项目文件夹。",
        "open_primary_output": "打开最新输出文件位置。",
    }
    return hints.get(action_id) or detail or str(project.get("readiness_summary") or "").strip()


def project_attention_rank(project: dict) -> int:
    urgency = str(project.get("readiness_next_step_urgency") or "")
    if urgency == "high":
        return 0
    auto_status = str(project.get("auto_workflow_status") or "")
    if auto_status in {"queued", "running", "between_steps", "cancel_requested"}:
        return 10
    if project.get("metadata_error") or project.get("artifact_health_status") in {"error", "warning"}:
        return 20
    if urgency == "medium":
        return 30
    bucket = str(project.get("readiness_bucket") or "")
    return {"needs_action": 40, "normal": 60, "deliverable": 80}.get(bucket, 70)


def project_attention_reason(project: dict) -> str:
    try:
        rank_value = project.get("readiness_attention_rank")
        rank = int(rank_value if rank_value is not None else project_attention_rank(project))
    except (TypeError, ValueError):
        rank = project_attention_rank(project)
    next_focus = str(
        project.get("readiness_next_step_context")
        or project.get("readiness_next_step_label")
        or project.get("readiness_next_step_detail")
        or project.get("readiness_summary")
        or ""
    ).strip()
    if rank == 0:
        return f"优先处理：{next_focus or '有必需步骤未完成'}"
    if rank == 10:
        detail = str(project.get("auto_workflow_job_summary") or project.get("auto_workflow_status") or "自动流程正在运行").strip()
        return f"正在生成：{detail}"
    if rank == 20 and project.get("metadata_error"):
        return "元数据异常：可打开项目文件夹修复"
    if rank == 20:
        detail = str(project.get("artifact_health_summary") or project.get("artifact_health_label") or "生成文件需要复核").strip()
        return f"文件异常：{detail}"
    if rank == 30:
        return f"建议处理：{next_focus or '有步骤建议补齐'}"
    if rank == 40:
        return f"待处理：{next_focus or '还有生成步骤未完成'}"
    if rank == 80:
        detail = str(project.get("delivery_package_summary") or "交付文件已生成").strip()
        return f"可交付：{detail}"
    return str(project.get("readiness_summary") or project.get("status") or "").strip()


def summarize_analysis_for_metadata(analysis: dict) -> dict:
    summary: dict = {
        "analysis_available": True,
        "problem_count": len(analysis.get("problems", []) or []),
        "recommended_problem": analysis.get("recommended_problem", {}) or {},
        "system_recommended_problem": analysis.get("system_recommended_problem", {}) or {},
        "contest_summary": analysis.get("contest_summary", {}) or {},
    }
    for key in ["recommended_problem", "system_recommended_problem"]:
        problem = summary.get(key)
        if isinstance(problem, dict):
            summary[key] = {
                "id": problem.get("id") or problem.get("final_problem_id") or "",
                "title": problem.get("title") or problem.get("final_problem_title") or "",
            }
    return summary


@app.post("/api/projects")
async def create(file: UploadFile = File(...), progress_id: str | None = Form(None)) -> dict:
    if not file.filename:
        raise HTTPException(status_code=400, detail="缺少文件名")
    try:
        validate_upload_name(file.filename)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    meta = create_project(file.filename)
    root = Path(meta["root"])
    progress = AnalysisProgress(root, meta, progress_id)
    progress.start_step("upload", "上传赛题材料", f"正在保存上传文件：{file.filename}")
    upload_path = root / "uploads" / Path(file.filename).name
    uploaded_bytes = 0
    try:
        with upload_path.open("wb") as fh:
            while chunk := await file.read(1024 * 1024):
                uploaded_bytes += len(chunk)
                fh.write(chunk)
                progress.update(f"已接收 {format_bytes(uploaded_bytes)}：{file.filename}")
        progress.finish_step("success", f"上传文件已保存：{upload_path.name}，{format_bytes(uploaded_bytes)}")
        progress.start_step("unpack", "解包并整理原始材料", "正在展开压缩包或复制单个赛题文件。")
        await asyncio.to_thread(unpack_upload, upload_path, root / "raw")
        raw_count = count_files(root / "raw")
        progress.finish_step("success", f"原始材料已整理完成，共 {raw_count} 个文件。")
        await asyncio.to_thread(analyze_project_materials, root, meta, progress)
    except Exception as exc:
        meta["status"] = "failed"
        meta["error"] = f"{type(exc).__name__}: {exc}"
        save_json(root / "metadata.json", meta)
        progress.fail(meta["error"])
        raise HTTPException(status_code=500, detail=meta["error"]) from exc

    return project_detail(meta["id"])


@app.post("/api/projects/folder")
async def create_from_folder(
    folder_name: str = Form("赛题文件夹"),
    progress_id: str | None = Form(None),
    files: list[UploadFile] = File(...),
) -> dict:
    if not files:
        raise HTTPException(status_code=400, detail="请选择一个包含赛题材料的文件夹。")
    if len(files) > MAX_FOLDER_UPLOAD_FILES:
        raise HTTPException(status_code=400, detail=f"文件夹中文件过多，请控制在 {MAX_FOLDER_UPLOAD_FILES} 个以内。")

    meta = create_project(folder_name or "赛题文件夹")
    root = Path(meta["root"])
    progress = AnalysisProgress(root, meta, progress_id)
    progress.start_step("upload", "上传赛题文件夹", f"正在接收文件夹中的 {len(files)} 个文件。")
    raw_dir = root / "raw"
    upload_manifest = []
    total_bytes = 0

    try:
        for file_index, upload in enumerate(files, 1):
            if not upload.filename:
                continue
            target = safe_folder_target(raw_dir, upload.filename)
            target.parent.mkdir(parents=True, exist_ok=True)
            file_bytes = 0
            with target.open("wb") as fh:
                while chunk := await upload.read(1024 * 1024):
                    file_bytes += len(chunk)
                    total_bytes += len(chunk)
                    if total_bytes > MAX_FOLDER_UPLOAD_BYTES:
                        raise ValueError("文件夹总大小过大，请控制在 500 MB 以内。")
                    fh.write(chunk)
                    progress.update(
                        f"正在接收 {file_index}/{len(files)}：{target.relative_to(raw_dir).as_posix()}，累计 {format_bytes(total_bytes)}"
                    )
            upload_manifest.append(
                {
                    "path": target.relative_to(raw_dir).as_posix(),
                    "size": file_bytes,
                    "content_type": upload.content_type or "",
                }
            )
        if not upload_manifest:
            raise ValueError("文件夹中没有可上传文件。")
        save_json(root / "uploads" / "folder_upload_manifest.json", upload_manifest)
        meta["folder_upload"] = {
            "file_count": len(upload_manifest),
            "total_bytes": total_bytes,
        }
        progress.finish_step("success", f"文件夹上传完成：{len(upload_manifest)} 个文件，{format_bytes(total_bytes)}。")
        await asyncio.to_thread(analyze_project_materials, root, meta, progress)
    except Exception as exc:
        meta["status"] = "failed"
        meta["error"] = f"{type(exc).__name__}: {exc}"
        save_json(root / "metadata.json", meta)
        progress.fail(meta["error"])
        raise HTTPException(status_code=500, detail=meta["error"]) from exc

    return project_detail(meta["id"])


def analyze_project_materials(root: Path, meta: dict, progress: AnalysisProgress | None = None) -> None:
    raw_dir = root / "raw"

    if progress:
        progress.start_step("inventory", "盘点赛题材料", "正在识别文档、数据表、压缩包展开后的目录结构。")

    def on_inventory_file(event: dict) -> None:
        if not progress:
            return
        progress.update(
            f"正在读取 {event.get('index')}/{event.get('total')}：{event.get('path')}",
            kind=event.get("kind"),
            suffix=event.get("suffix"),
        )

    inventory = inventory_files(raw_dir, on_file=on_inventory_file)
    document_count = len([item for item in inventory if item.get("kind") == "document"])
    data_count = len([item for item in inventory if item.get("kind") == "data"])
    if progress:
        progress.finish_step("success", f"材料盘点完成：{document_count} 个文档，{data_count} 个数据附件，共 {len(inventory)} 个文件。")
        progress.start_step("extract_documents", "抽取题面与规则文本", "正在从 PDF、Word、Markdown、文本文件中提取可供分析的内容。")

    def on_document(event: dict) -> None:
        if not progress:
            return
        if event.get("phase") == "finish":
            progress.update(f"已抽取 {event.get('index')}/{event.get('total')}：{event.get('path')}，约 {event.get('chars', 0)} 字。")
        else:
            progress.update(f"正在抽取 {event.get('index')}/{event.get('total')}：{event.get('path')}")

    docs = extract_all_document_text(raw_dir, on_document=on_document)
    if progress:
        total_chars = sum(len(doc.get("text", "")) for doc in docs)
        progress.finish_step("success", f"文本抽取完成：{len(docs)} 个文档，约 {total_chars} 字。")
        progress.start_step("build_analysis", "识别赛题并评估选题", "正在识别 A/B/C 等候选题、匹配附件、评估建模难度与论文可写性。")

    analysis = build_analysis(inventory, docs)
    analysis["project"] = {k: v for k, v in meta.items() if k != "root"}
    analysis["inventory"] = inventory
    attach_artifacts_safely(meta, write_material_passport(root, analysis, docs, inventory))
    if progress:
        recommended = analysis.get("recommended_problem", {}) or {}
        progress.finish_step(
            "success",
            f"识别到 {len(analysis.get('problems', []))} 个候选题；当前推荐 {recommended.get('id', '-')} 题：{recommended.get('title', '')}",
        )

    llm_configured = bool(get_llm_settings().get("configured"))
    if llm_configured:
        if progress:
            progress.start_step(
                "llm_structure_analysis",
                "LLM 读取题面与附件",
                "正在让大模型读取题面文本、附件路径、数据表字段和样例，补全子问题与附件映射。",
            )
        try:
            with bind_llm_stream(root, "upload_analysis", "上传后赛题结构识别大模型直播", "正在读取题面和附件结构，修正选题分析。"):
                analysis, structure_artifacts, structure_payload = run_problem_structure_enhancement(root, analysis, docs, inventory)
            analysis["project"] = {k: v for k, v in meta.items() if k != "root"}
            analysis["inventory"] = inventory
            attach_artifacts_safely(meta, write_material_passport(root, analysis, docs, inventory))
            attach_artifacts_safely(meta, structure_artifacts)
            meta["llm_structure_status"] = "success" if structure_payload.get("success") else "warning"
            if progress:
                recommended = analysis.get("recommended_problem", {}) or {}
                detail = (
                    f"LLM 已增强赛题结构：识别 {len(analysis.get('problems', []))} 个候选题，"
                    f"推荐 {recommended.get('id', '-')} 题；子问题与附件映射已写回 analysis.json。"
                    if structure_payload.get("success")
                    else f"LLM 结构增强未完成，已保留规则解析：{structure_payload.get('error', '')}"
                )
                progress.finish_step("success" if structure_payload.get("success") else "warning", detail)
        except Exception as exc:
            meta["llm_structure_status"] = "failed"
            meta["llm_structure_error"] = f"{type(exc).__name__}: {exc}"
            if progress:
                progress.finish_step("warning", f"LLM 结构增强失败，已保留规则解析：{meta['llm_structure_error']}")
    else:
        meta["llm_structure_status"] = "requires_api_key"
        if progress:
            progress.start_step("llm_structure_analysis", "LLM 读取题面与附件", "未配置 API Key，跳过 LLM 结构增强。")
            progress.finish_step("warning", "未配置 API Key，子问题与附件映射暂使用本地规则解析。")

    if progress:
        progress.start_step("write_artifacts", "生成分析报告与论文骨架", "正在写入 analysis.json、分析报告、论文提纲、模型方案和 LaTeX 骨架。")

    artifacts = write_artifacts(root, analysis)
    save_json(root / "artifacts" / "analysis.json", analysis)
    if progress:
        progress.finish_step("success", "分析报告、论文提纲、模型方案和 LaTeX 骨架已生成。")

    if llm_configured:
        if progress:
            progress.start_step("llm_problem_analysis", "LLM 补充赛题分析", "正在调用大模型复盘选题、建模路线和风险点。")
        try:
            with bind_llm_stream(root, "upload_analysis", "上传后赛题分析大模型直播", "正在补充生成赛题理解、选题理由和建模建议。"):
                attach_artifacts_safely(meta, run_problem_llm_analysis(root, analysis))
            meta["llm_analysis_status"] = "success"
            if progress:
                progress.finish_step("success", "LLM 赛题分析报告已生成。")
        except Exception as exc:
            meta["llm_analysis_status"] = "failed"
            meta["llm_analysis_error"] = f"{type(exc).__name__}: {exc}"
            if progress:
                progress.finish_step("warning", f"LLM 补充分析失败，但本地赛题分析已完成：{meta['llm_analysis_error']}")
    else:
        meta["llm_analysis_status"] = "requires_api_key"
        if progress:
            progress.start_step("llm_problem_analysis", "LLM 补充赛题分析", "未配置 API Key，跳过大模型补充分析。")
            progress.finish_step("warning", "未配置 API Key，已跳过 LLM 补充分析；本地赛题分析可正常使用。")
    meta["analysis_summary"] = summarize_analysis_for_metadata(analysis)
    meta["status"] = "analyzed"
    attach_artifacts_safely(meta, artifacts)
    save_json(root / "metadata.json", meta)
    if progress:
        progress.finish("success", "赛题分析完成。")


@app.get("/api/projects/{project_id}")
def project_detail(project_id: str) -> dict:
    try:
        root = project_root(project_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="项目不存在") from exc
    try:
        meta = load_json(root / "metadata.json")
        if not isinstance(meta, dict):
            raise ValueError("metadata.json must contain a JSON object")
    except Exception as exc:
        meta = project_metadata_error_stub(root, exc)
    meta = attach_project_runtime_fields(meta, root)
    analysis_path = root / "artifacts" / "analysis.json"
    analysis = None
    if analysis_path.exists() and not meta.get("metadata_error"):
        try:
            analysis = load_json(analysis_path)
        except Exception as exc:
            meta["analysis_error"] = f"{type(exc).__name__}: {exc}"
    if analysis and not isinstance(meta.get("analysis_summary"), dict):
        meta["analysis_summary"] = summarize_analysis_for_metadata(analysis)
        save_json(root / "metadata.json", meta)
    repair_path = root / REPAIR_BRIEFING_JSON_RELATIVE
    repair = load_optional_project_json(root, repair_path, meta, "修复报告")
    delivery_path = root / DELIVERY_READINESS_JSON_RELATIVE
    delivery = load_optional_project_json(root, delivery_path, meta, "交付检查")
    package_path = root / DELIVERY_PACKAGE_MANIFEST_JSON_RELATIVE
    package = load_optional_project_json(root, package_path, meta, "交付包清单")
    meta = attach_project_artifact_fields(meta, root)
    readiness = build_project_readiness(
        root,
        meta,
        analysis,
        llm_settings=get_llm_settings(),
        repair=repair,
        delivery=delivery,
        package=package,
    )
    meta = attach_project_readiness_fields(meta, readiness)
    return {
        "metadata": {k: v for k, v in meta.items() if k != "root"},
        "analysis": analysis,
        "repair": repair,
        "delivery": delivery,
        "package": package,
        "readiness": readiness,
    }


def load_optional_project_json(root: Path, path: Path, meta: dict, label: str) -> dict | None:
    if not path.exists():
        return None
    try:
        payload = load_json(path)
        return payload if isinstance(payload, dict) else {"value": payload}
    except Exception as exc:
        try:
            relative = path.relative_to(root).as_posix()
        except ValueError:
            relative = str(path)
        meta.setdefault("artifact_load_errors", []).append(
            {
                "label": label,
                "path": relative,
                "error": f"{type(exc).__name__}: {exc}",
            }
        )
        return None


@app.post("/api/projects/{project_id}/analyze")
async def reanalyze_project(project_id: str) -> dict:
    try:
        root = project_root(project_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="项目不存在。") from exc
    raw_dir = root / "raw"
    if not raw_dir.exists() or count_files(raw_dir) == 0:
        raise HTTPException(status_code=400, detail="项目缺少原始赛题材料，请重新上传后再分析。")
    meta = load_json(root / "metadata.json")
    try:
        await asyncio.to_thread(analyze_project_materials, root, meta, None)
        meta = load_json(root / "metadata.json")
        attach_artifacts_safely(meta, write_delivery_readiness_report(root, meta))
    except Exception as exc:
        meta["status"] = "failed"
        meta["analysis_error"] = f"{type(exc).__name__}: {exc}"
        save_json(root / "metadata.json", meta)
        raise HTTPException(status_code=500, detail=meta["analysis_error"]) from exc
    save_json(root / "metadata.json", meta)
    return {"project": project_detail(project_id)}


@app.put("/api/projects/{project_id}/paper/options")
def update_paper_options(project_id: str, payload: PaperOptionsPayload) -> dict:
    try:
        root = project_root(project_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="项目不存在。") from exc
    try:
        template_id = validate_template_id(payload.template_id or DEFAULT_TEMPLATE_ID)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    target_pages = payload.target_body_pages
    if target_pages is not None and not (1 <= target_pages <= 100):
        raise HTTPException(status_code=400, detail="正文目标页数需在 1 到 100 之间。")
    meta = load_json(root / "metadata.json")
    meta["paper_options"] = {
        "template_id": template_id,
        "target_body_pages": target_pages,
    }
    save_json(root / "metadata.json", meta)
    return {"paper_options": meta["paper_options"], "project": project_detail(project_id)}


@app.put("/api/projects/{project_id}/problem/selection")
def select_project_problem(project_id: str, payload: ProblemSelectionPayload) -> dict:
    try:
        root = project_root(project_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="项目不存在。") from exc
    analysis_path = root / "artifacts" / "analysis.json"
    if not analysis_path.exists():
        raise HTTPException(status_code=400, detail="项目尚未完成赛题分析。")
    analysis = load_json(analysis_path)
    try:
        selected = apply_problem_selection(analysis, payload.problem_id, source="user")
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    meta = load_json(root / "metadata.json")
    final_problem = {
        "id": selected.get("id", ""),
        "title": selected.get("title", ""),
        "reason": "用户手动确认选题，后续自动解题与论文生成以该题为准。",
        "source": "user",
    }
    meta["final_problem"] = final_problem
    meta["problem_selection_status"] = "user_selected"
    save_json(analysis_path, analysis)
    artifacts = write_artifacts_without_latex(root, analysis)
    attach_artifacts_safely(meta, artifacts)
    save_json(root / "metadata.json", meta)
    return {"selected_problem": final_problem, "project": project_detail(project_id)}


def write_artifacts_without_latex(root: Path, analysis: dict) -> dict[str, str]:
    from app.services.paper import render_model_plan, render_outline, render_report

    artifacts = root / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    (artifacts / "analysis_report.md").write_text(render_report(analysis), encoding="utf-8")
    (artifacts / "outline.md").write_text(render_outline(analysis), encoding="utf-8")
    (artifacts / "model_plan.md").write_text(render_model_plan(analysis), encoding="utf-8")
    return {
        "analysis_report": "artifacts/analysis_report.md",
        "outline": "artifacts/outline.md",
        "model_plan": "artifacts/model_plan.md",
    }


@app.post("/api/projects/{project_id}/compile")
def compile_project(project_id: str) -> dict:
    try:
        root = project_root(project_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="项目不存在") from exc
    meta = load_json(root / "metadata.json")
    try:
        result = compile_latex(root)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"{type(exc).__name__}: {exc}") from exc
    meta.setdefault("artifacts", {})
    meta["artifacts"]["latex_log"] = result["log"]
    if result["pdf"]:
        meta["artifacts"]["paper_pdf"] = result["pdf"]
    if result.get("docx"):
        meta["artifacts"]["paper_docx"] = result["docx"]
    if result.get("word_log"):
        meta["artifacts"]["word_export_log"] = result["word_log"]
    meta["compile_status"] = "success" if result["success"] else "failed"
    attach_artifacts_safely(meta, write_delivery_readiness_report(root, meta))
    save_json(root / "metadata.json", meta)
    return {"compile": result, "project": project_detail(project_id)}


@app.post("/api/projects/{project_id}/model/generate")
def generate_model(project_id: str) -> dict:
    try:
        root = project_root(project_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="项目不存在") from exc
    analysis_path = root / "artifacts" / "analysis.json"
    if not analysis_path.exists():
        raise HTTPException(status_code=400, detail="项目尚未完成赛题分析")
    meta = load_json(root / "metadata.json")
    analysis = load_json(analysis_path)
    artifacts = generate_modeling_script(root, analysis)
    meta.setdefault("artifacts", {}).update(artifacts)
    meta["modeling_status"] = "script_generated"
    save_json(root / "metadata.json", meta)
    return {"artifacts": artifacts, "project": project_detail(project_id)}


@app.post("/api/projects/{project_id}/model/run")
def run_model(project_id: str) -> dict:
    try:
        root = project_root(project_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="项目不存在") from exc
    analysis_path = root / "artifacts" / "analysis.json"
    if not analysis_path.exists():
        raise HTTPException(status_code=400, detail="项目尚未完成赛题分析")
    meta = load_json(root / "metadata.json")
    analysis = load_json(analysis_path)
    if not (root / "code" / "run_baseline_analysis.py").exists():
        meta.setdefault("artifacts", {}).update(generate_modeling_script(root, analysis))
    try:
        result = run_modeling_script(root)
        attach_artifacts_safely(meta, run_baseline_llm_review(root, analysis, result))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"{type(exc).__name__}: {exc}") from exc
    meta.setdefault("artifacts", {})
    meta["artifacts"]["modeling_script"] = "code/run_baseline_analysis.py"
    meta["artifacts"]["modeling_log"] = result["log"]
    if result.get("manifest"):
        meta["artifacts"]["modeling_manifest"] = result["manifest"]
    if result.get("outputs", {}).get("summary_markdown"):
        meta["artifacts"]["baseline_summary"] = result["outputs"]["summary_markdown"]
    meta["modeling_status"] = "success" if result["success"] else "failed"
    save_json(root / "metadata.json", meta)
    return {"modeling": result, "project": project_detail(project_id)}


@app.post("/api/projects/{project_id}/specialized/generate")
def generate_specialized(project_id: str) -> dict:
    try:
        root = project_root(project_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="项目不存在") from exc
    analysis_path = root / "artifacts" / "analysis.json"
    if not analysis_path.exists():
        raise HTTPException(status_code=400, detail="项目尚未完成赛题分析")
    meta = load_json(root / "metadata.json")
    analysis = load_json(analysis_path)
    artifacts = generate_specialized_script(root, analysis)
    meta.setdefault("artifacts", {}).update(artifacts)
    meta["specialized_status"] = "script_generated"
    save_json(root / "metadata.json", meta)
    return {"artifacts": artifacts, "project": project_detail(project_id)}


@app.post("/api/projects/{project_id}/specialized/run")
def run_specialized(project_id: str) -> dict:
    try:
        root = project_root(project_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="项目不存在") from exc
    analysis_path = root / "artifacts" / "analysis.json"
    if not analysis_path.exists():
        raise HTTPException(status_code=400, detail="项目尚未完成赛题分析")
    meta = load_json(root / "metadata.json")
    analysis = load_json(analysis_path)
    if not (root / "code" / "run_specialized_model.py").exists():
        meta.setdefault("artifacts", {}).update(generate_specialized_script(root, analysis))
    try:
        result = run_specialized_script(root)
        attach_artifacts_safely(meta, run_specialized_llm_review(root, analysis, result))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"{type(exc).__name__}: {exc}") from exc
    meta.setdefault("artifacts", {})
    meta["artifacts"]["specialized_script"] = "code/run_specialized_model.py"
    meta["artifacts"]["specialized_log"] = result["log"]
    if result.get("manifest"):
        meta["artifacts"]["specialized_manifest"] = result["manifest"]
    if result.get("outputs", {}).get("summary_markdown"):
        meta["artifacts"]["specialized_summary"] = result["outputs"]["summary_markdown"]
    meta["specialized_status"] = "success" if result["success"] else "failed"
    save_json(root / "metadata.json", meta)
    return {"specialized": result, "project": project_detail(project_id)}


@app.post("/api/projects/{project_id}/paper/fill")
def fill_paper(project_id: str) -> dict:
    try:
        root = project_root(project_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="项目不存在") from exc
    meta = load_json(root / "metadata.json")
    try:
        artifacts = fill_paper_with_results(root)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"{type(exc).__name__}: {exc}") from exc
    meta.setdefault("artifacts", {}).update(artifacts)
    meta["paper_fill_status"] = "success"
    attach_artifacts_safely(meta, write_delivery_readiness_report(root, meta))
    save_json(root / "metadata.json", meta)
    return {"artifacts": artifacts, "project": project_detail(project_id)}


@app.post("/api/projects/{project_id}/computed/run")
def run_project_computed_solution(project_id: str) -> dict:
    try:
        root = project_root(project_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="项目不存在。") from exc
    analysis_path = root / "artifacts" / "analysis.json"
    if not analysis_path.exists():
        raise HTTPException(status_code=400, detail="项目尚未完成赛题分析")
    meta = load_json(root / "metadata.json")
    analysis = load_json(analysis_path)
    paper_options = meta.get("paper_options", {}) if isinstance(meta, dict) else {}
    try:
        artifacts = run_code_result_pipeline(root, analysis, paper_options)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"{type(exc).__name__}: {exc}") from exc
    attach_artifacts_safely(meta, artifacts)
    meta["computed_solution_status"] = "success"
    meta["paper_fill_status"] = "success"
    attach_artifacts_safely(meta, write_performance_health_report(root, meta))
    attach_artifacts_safely(meta, write_delivery_readiness_report(root, meta))
    save_json(root / "metadata.json", meta)
    return {"artifacts": artifacts, "project": project_detail(project_id)}


@app.post("/api/projects/{project_id}/paper/review")
def review_project_paper(project_id: str) -> dict:
    try:
        root = project_root(project_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="项目不存在") from exc
    meta = load_json(root / "metadata.json")
    try:
        artifacts = review_paper(root)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"{type(exc).__name__}: {exc}") from exc
    meta.setdefault("artifacts", {}).update(artifacts)
    meta["paper_review_status"] = "success"
    attach_artifacts_safely(meta, write_delivery_readiness_report(root, meta))
    save_json(root / "metadata.json", meta)
    return {"artifacts": artifacts, "project": project_detail(project_id)}


@app.post("/api/projects/{project_id}/diagnostics/refresh")
def refresh_project_diagnostics(project_id: str, force: bool = True) -> dict:
    try:
        root = project_root(project_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="项目不存在。") from exc
    analysis_path = root / "artifacts" / "analysis.json"
    if not analysis_path.exists():
        raise HTTPException(status_code=400, detail="项目尚未完成赛题分析。")
    meta = load_json(root / "metadata.json")
    analysis = load_json(analysis_path)
    settings = get_llm_settings()
    strategy = meta.get("workflow_strategy") or settings.get("workflow_strategy")
    try:
        diagnostics = refresh_diagnostic_assets(
            root,
            meta,
            analysis,
            workflow_strategy=strategy,
            force_attachment=force,
        )
    except ValueError as exc:
        meta["diagnostics_refresh_status"] = "failed"
        meta["diagnostics_refresh_error"] = str(exc)
        save_json(root / "metadata.json", meta)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        meta["diagnostics_refresh_status"] = "failed"
        meta["diagnostics_refresh_error"] = f"{type(exc).__name__}: {exc}"
        save_json(root / "metadata.json", meta)
        raise HTTPException(status_code=500, detail=meta["diagnostics_refresh_error"]) from exc
    save_json(root / "metadata.json", meta)
    return {"diagnostics": diagnostics, "project": project_detail(project_id)}


@app.post("/api/projects/{project_id}/repair/briefing")
def refresh_project_repair_briefing(project_id: str) -> dict:
    try:
        root = project_root(project_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="项目不存在。") from exc
    meta = load_json(root / "metadata.json")
    try:
        artifacts = write_repair_briefing(root, meta)
        repair = load_json(root / REPAIR_BRIEFING_JSON_RELATIVE)
    except Exception as exc:
        meta["repair_center_status"] = "failed"
        meta["repair_center_summary"] = f"{type(exc).__name__}: {exc}"
        save_json(root / "metadata.json", meta)
        raise HTTPException(status_code=500, detail=meta["repair_center_summary"]) from exc
    save_json(root / "metadata.json", meta)
    return {"repair": repair, "artifacts": artifacts, "project": project_detail(project_id)}


@app.post("/api/projects/{project_id}/delivery/readiness")
def refresh_project_delivery_readiness(project_id: str) -> dict:
    try:
        root = project_root(project_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="项目不存在。") from exc
    meta = load_json(root / "metadata.json")
    try:
        artifacts = write_delivery_readiness_report(root, meta)
        delivery = load_json(root / DELIVERY_READINESS_JSON_RELATIVE)
    except Exception as exc:
        meta["delivery_readiness_status"] = "failed"
        meta["delivery_readiness_summary"] = f"{type(exc).__name__}: {exc}"
        save_json(root / "metadata.json", meta)
        raise HTTPException(status_code=500, detail=meta["delivery_readiness_summary"]) from exc
    save_json(root / "metadata.json", meta)
    return {"delivery": delivery, "artifacts": artifacts, "project": project_detail(project_id)}


@app.post("/api/projects/{project_id}/delivery/package")
def build_project_delivery_package(project_id: str) -> dict:
    try:
        root = project_root(project_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="项目不存在。") from exc
    meta = load_json(root / "metadata.json")
    try:
        artifacts = write_delivery_package(root, meta)
        package = load_json(root / DELIVERY_PACKAGE_MANIFEST_JSON_RELATIVE)
    except Exception as exc:
        meta["delivery_package_status"] = "failed"
        meta["delivery_package_summary"] = f"{type(exc).__name__}: {exc}"
        save_json(root / "metadata.json", meta)
        raise HTTPException(status_code=500, detail=meta["delivery_package_summary"]) from exc
    attach_artifacts_safely(meta, artifacts)
    save_json(root / "metadata.json", meta)
    return {"package": package, "artifacts": artifacts, "project": project_detail(project_id)}


@app.post("/api/projects/{project_id}/auto/run")
def run_project_auto_workflow(project_id: str) -> dict:
    try:
        root = project_root(project_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="项目不存在。") from exc
    meta = load_json(root / "metadata.json")
    try:
        report = run_auto_workflow(root, meta)
    except ValueError as exc:
        meta["auto_workflow_status"] = "requires_api_key"
        meta["auto_workflow_error"] = str(exc)
        save_json(root / "metadata.json", meta)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        meta["auto_workflow_status"] = "failed"
        meta["auto_workflow_error"] = f"{type(exc).__name__}: {exc}"
        save_json(root / "metadata.json", meta)
        raise HTTPException(status_code=500, detail=meta["auto_workflow_error"]) from exc
    return {"auto_workflow": report, "project": project_detail(project_id)}


@app.post("/api/projects/{project_id}/auto/start")
def start_project_auto_workflow(project_id: str) -> dict:
    try:
        root = project_root(project_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="项目不存在。") from exc
    job = start_auto_workflow_job(project_id, root, resume=False)
    return {"auto_job": job, "project": project_detail(project_id)}


@app.post("/api/projects/{project_id}/auto/resume")
def resume_project_auto_workflow(project_id: str) -> dict:
    try:
        root = project_root(project_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="项目不存在。") from exc
    meta = load_json(root / "metadata.json")
    try:
        report = run_auto_workflow(root, meta, resume=True)
    except ValueError as exc:
        meta["auto_workflow_status"] = "requires_api_key"
        meta["auto_workflow_error"] = str(exc)
        save_json(root / "metadata.json", meta)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        meta["auto_workflow_status"] = "failed"
        meta["auto_workflow_error"] = f"{type(exc).__name__}: {exc}"
        save_json(root / "metadata.json", meta)
        raise HTTPException(status_code=500, detail=meta["auto_workflow_error"]) from exc
    return {"auto_workflow": report, "project": project_detail(project_id)}


@app.post("/api/projects/{project_id}/auto/resume/start")
def start_project_auto_workflow_resume(project_id: str) -> dict:
    try:
        root = project_root(project_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="项目不存在。") from exc
    job = start_auto_workflow_job(project_id, root, resume=True)
    return {"auto_job": job, "project": project_detail(project_id)}


@app.post("/api/projects/{project_id}/auto/cancel")
def cancel_project_auto_workflow(project_id: str) -> dict:
    try:
        root = project_root(project_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="项目不存在。") from exc
    queued = cancel_queued_auto_workflow_job(project_id)
    if queued.get("cancelled"):
        return {"cancel": queued, "project": project_detail(project_id)}
    meta = load_json(root / "metadata.json")
    control = request_auto_workflow_cancel(root, meta)
    return {"cancel": {**control, "queued_job": queued}, "project": project_detail(project_id)}


@app.get("/api/projects/{project_id}/auto/job")
def project_auto_workflow_job(project_id: str) -> dict:
    try:
        project_root(project_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="项目不存在。") from exc
    return {"auto_job": get_project_auto_workflow_job(project_id)}


@app.get("/api/projects/{project_id}/auto/status")
def project_auto_workflow_status(project_id: str) -> dict:
    payload = project_progress(project_id)
    progress = payload.get("progress", {}) if isinstance(payload.get("progress"), dict) else {}
    auto_job = progress.get("auto_job") if isinstance(progress.get("auto_job"), dict) else get_project_auto_workflow_job(project_id)
    return {
        **payload,
        "auto_job": auto_job or {},
        "auto_workflow": progress,
    }


@app.get("/api/auto/jobs")
def auto_workflow_jobs() -> dict:
    return {
        "auto_jobs": list_auto_workflow_jobs(),
        "delivery_batch_jobs": list_delivery_batch_jobs(),
        "capacity_settings": load_capacity_settings(),
        "capacity_autotune": list_capacity_autotune_events(),
    }


@app.post("/api/auto/batch/start")
def start_auto_workflow_batch(payload: BatchAutoWorkflowPayload) -> dict:
    project_ids = dedupe_project_ids(payload.project_ids)
    if not project_ids:
        raise HTTPException(status_code=400, detail="请选择至少一个项目。")
    if len(project_ids) > 40:
        raise HTTPException(status_code=400, detail="单次最多批量提交 40 个项目。")
    mode = normalize_batch_mode(payload.mode)
    submitted: list[dict] = []
    skipped: list[dict] = []
    for project_id in project_ids:
        try:
            root = project_root(project_id)
        except FileNotFoundError:
            skipped.append({"project_id": project_id, "reason": "项目不存在。"})
            continue
        analysis_path = root / "artifacts" / "analysis.json"
        if not analysis_path.exists():
            skipped.append({"project_id": project_id, "reason": "项目尚未完成赛题分析。"})
            continue
        meta = load_json(root / "metadata.json")
        resume = should_resume_batch_project(meta, mode)
        try:
            job = start_auto_workflow_job(project_id, root, resume=resume)
        except Exception as exc:
            skipped.append({"project_id": project_id, "reason": f"{type(exc).__name__}: {exc}"})
            continue
        submitted.append(job)
    return {
        "batch": {
            "requested_count": len(project_ids),
            "submitted_count": len(submitted),
            "skipped_count": len(skipped),
            "mode": mode,
            "submitted": submitted,
            "skipped": skipped,
        },
        "auto_jobs": list_auto_workflow_jobs(),
    }


def dedupe_project_ids(project_ids: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for raw in project_ids or []:
        project_id = str(raw or "").strip()
        if not project_id or project_id in seen:
            continue
        seen.add(project_id)
        result.append(project_id)
    return result


def normalize_batch_mode(value: str | None) -> str:
    mode = str(value or "auto").strip().lower()
    if mode in {"auto", "start", "resume"}:
        return mode
    raise HTTPException(status_code=400, detail="批量模式只能是 auto、start 或 resume。")


def should_resume_batch_project(meta: dict, mode: str) -> bool:
    if mode == "resume":
        return True
    if mode == "start":
        return False
    status = str(meta.get("auto_workflow_status") or "")
    progress = meta.get("auto_workflow_progress", {}) if isinstance(meta.get("auto_workflow_progress"), dict) else {}
    return bool(
        status in {"failed", "cancelled", "completed_with_warnings", "interrupted"}
        or progress.get("can_resume")
        or meta.get("last_failure_diagnosis")
    )


@app.get("/api/auto/jobs/{job_id}")
def auto_workflow_job(job_id: str) -> dict:
    job = get_auto_workflow_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="自动流程任务不存在或已被清理。")
    return {"auto_job": job}


@app.get("/api/projects/{project_id}/progress")
def project_progress(project_id: str) -> dict:
    try:
        root = project_root(project_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="项目不存在。") from exc
    meta = load_json(root / "metadata.json")
    progress_path = root / "artifacts" / "auto_workflow_progress.json"
    progress_error = ""
    try:
        progress = load_json(progress_path) if progress_path.exists() else meta.get("auto_workflow_progress", {})
    except Exception as exc:
        progress = {}
        progress_error = f"{type(exc).__name__}: {exc}"
    active_job = get_project_auto_workflow_job(project_id)
    response_status = meta.get("auto_workflow_status") or "idle"
    if active_job.get("status") in {"queued", "running"}:
        response_status = str(active_job.get("status") or response_status)
    if not isinstance(progress, dict):
        progress = {}
    progress = dict(progress)
    status = response_status or progress.get("status") or "idle"
    stale_running = (
        status in {"queued", "running", "between_steps", "cancel_requested"}
        and not active_job
        and auto_progress_is_missing_or_stale(progress)
    )
    progress["can_resume"] = bool(
        progress.get("can_resume")
        or status in {"failed", "cancelled", "completed_with_warnings", "cancel_requested"}
        or stale_running
    )
    progress["last_failure_diagnosis"] = progress.get("last_failure_diagnosis") or meta.get("last_failure_diagnosis", {})
    progress["resume_hint"] = progress.get("resume_hint") or meta.get("auto_workflow_repair_hint", "")
    if active_job:
        progress["auto_job"] = active_job
    progress["can_cancel"] = (
        not stale_running
        and (
            status in {"queued", "running", "cancel_requested"}
            or progress.get("status") in {"queued", "running", "between_steps"}
        )
    )
    if stale_running:
        progress["status"] = "interrupted"
        progress["stale"] = True
        progress["detail"] = "检测到上次自动流程没有可用后台任务，可点击继续生成。"
        progress["resume_hint"] = progress.get("resume_hint") or "系统会从上次成功阶段继续。"
        response_status = "interrupted"
    if progress_error:
        progress["progress_error"] = progress_error
        if active_job.get("status") in {"queued", "running"}:
            progress["status"] = response_status
            progress["detail"] = "进度文件暂时读取失败，后台任务仍在运行，稍后会自动刷新。"
        else:
            progress["status"] = "interrupted"
            progress["can_resume"] = True
            progress["detail"] = "自动流程进度文件读取失败，已切换为可继续状态。"
            progress["resume_hint"] = progress.get("resume_hint") or "点击继续生成，系统会重新读取项目上下文。"
            response_status = "interrupted"
    live_stream = load_llm_live_stream(root)
    if live_stream.get("channel") == "auto_workflow":
        progress["live_stream"] = live_stream
    return {
        "project_id": project_id,
        "status": response_status,
        "progress": progress or {},
        "artifacts": meta.get("artifacts", {}),
        "error": meta.get("auto_workflow_error", ""),
    }


def auto_progress_is_stale(progress: dict, seconds: int = 180) -> bool:
    updated_at = str(progress.get("updated_at") or "")
    if not updated_at:
        return False
    try:
        updated = datetime.fromisoformat(updated_at)
    except ValueError:
        return True
    return (datetime.now() - updated).total_seconds() > seconds


def auto_progress_is_missing_or_stale(progress: object, seconds: int = 180) -> bool:
    if not isinstance(progress, dict):
        return True
    if not str(progress.get("updated_at") or "").strip():
        return True
    return auto_progress_is_stale(progress, seconds)


@app.get("/api/projects/{project_id}/llm/model-assistant/progress")
def project_model_assistant_progress(project_id: str) -> dict:
    try:
        root = project_root(project_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="项目不存在。") from exc
    meta = load_json(root / "metadata.json")
    progress_path = root / MODEL_ASSISTANT_PROGRESS_RELATIVE
    progress_error = ""
    try:
        progress = load_json(progress_path) if progress_path.exists() else {}
    except Exception as exc:
        progress = {}
        progress_error = f"{type(exc).__name__}: {exc}"
    if not isinstance(progress, dict):
        progress = {}
    progress = dict(progress)
    if progress_error:
        progress["status"] = meta.get("model_assistant_status") or "warning"
        progress["progress_error"] = progress_error
        progress["detail"] = "模型辅助进度文件暂时读取失败，稍后会自动刷新。"
    live_stream = load_llm_live_stream(root)
    if live_stream.get("channel") == "model_assistant":
        progress["live_stream"] = live_stream
    return {
        "project_id": project_id,
        "status": meta.get("model_assistant_status") or progress.get("status") or "idle",
        "progress": progress or {},
        "artifacts": meta.get("artifacts", {}),
        "error": meta.get("model_assistant_error", ""),
    }


@app.post("/api/projects/{project_id}/llm/analyze")
def run_project_llm_analysis(project_id: str) -> dict:
    try:
        root = project_root(project_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="项目不存在") from exc
    meta = load_json(root / "metadata.json")
    try:
        with bind_llm_stream(root, "llm_analysis", "LLM 分析大模型直播", "正在刷新赛题分析、基线复盘和专项复盘。") as live_stream:
            artifacts = run_full_llm_refresh(root)
            live_stream.finish("success", "LLM 分析报告刷新完成。")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"{type(exc).__name__}: {exc}") from exc
    attach_artifacts_safely(meta, artifacts)
    meta["llm_analysis_status"] = "success"
    save_json(root / "metadata.json", meta)
    return {"artifacts": artifacts, "project": project_detail(project_id)}


@app.post("/api/projects/{project_id}/llm/model-assistant")
def run_project_model_assistant(project_id: str, payload: ModelAssistantPayload) -> dict:
    try:
        root = project_root(project_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="项目不存在。") from exc
    if not payload.problem_ref.strip():
        raise HTTPException(status_code=400, detail="请指定要辅助求解的问题。")
    if not payload.model_name.strip():
        raise HTTPException(status_code=400, detail="请填写模型或算法名称。")
    meta = load_json(root / "metadata.json")
    meta["model_assistant_status"] = "running"
    meta.pop("model_assistant_error", None)
    save_json(root / "metadata.json", meta)
    try:
        artifacts = run_custom_model_assistance(
            root=root,
            problem_ref=payload.problem_ref.strip(),
            model_name=payload.model_name.strip(),
            user_goal=(payload.user_goal or "").strip(),
        )
    except ValueError as exc:
        meta["model_assistant_status"] = "failed"
        meta["model_assistant_error"] = str(exc)
        save_json(root / "metadata.json", meta)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        meta["model_assistant_status"] = "failed"
        meta["model_assistant_error"] = f"{type(exc).__name__}: {exc}"
        save_json(root / "metadata.json", meta)
        raise HTTPException(status_code=500, detail=f"{type(exc).__name__}: {exc}") from exc
    attach_artifacts_safely(meta, artifacts)
    progress_path = root / MODEL_ASSISTANT_PROGRESS_RELATIVE
    progress = load_json(progress_path) if progress_path.exists() else {}
    meta["model_assistant_status"] = progress.get("status") or "success"
    meta["model_assistant_progress"] = progress
    save_json(root / "metadata.json", meta)
    return {"artifacts": artifacts, "project": project_detail(project_id)}


@app.get("/api/projects/{project_id}/download/{relative_path:path}")
def download(project_id: str, relative_path: str) -> FileResponse:
    root, target = resolve_project_target(project_id, relative_path, create_support_zip=True)
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")
    return FileResponse(target, filename=target.name)


@app.get("/download/{relative_path:path}")
def download_from_recent_project(relative_path: str) -> FileResponse:
    projects = list_projects()
    if not projects:
        raise HTTPException(status_code=404, detail="No project is available for this legacy download link.")
    project_id = str(projects[0].get("id") or "")
    if not project_id:
        raise HTTPException(status_code=404, detail="No project is available for this legacy download link.")
    return download(project_id, relative_path)


@app.post("/api/projects/{project_id}/open-location/{relative_path:path}")
def open_location(project_id: str, relative_path: str) -> dict:
    root, target = resolve_project_target(project_id, relative_path, create_support_zip=True)
    if not target.exists():
        raise HTTPException(status_code=404, detail="文件或文件夹不存在")
    try:
        open_in_file_manager(target)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"无法打开文件位置：{type(exc).__name__}: {exc}") from exc
    try:
        display_path = target.relative_to(root).as_posix()
    except ValueError:
        display_path = str(target)
    return {"success": True, "path": display_path}


@app.post("/api/projects/{project_id}/open-root")
def open_project_root(project_id: str) -> dict:
    try:
        root = project_root(project_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="项目不存在") from exc
    try:
        open_in_file_manager(root)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"无法打开项目文件夹：{type(exc).__name__}: {exc}") from exc
    return {"success": True, "path": str(root)}


def resolve_project_target(project_id: str, relative_path: str, create_support_zip: bool = False) -> tuple[Path, Path]:
    try:
        root = project_root(project_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="项目不存在") from exc
    if relative_path == "support.zip":
        target = make_support_zip(root) if create_support_zip else root / "artifacts" / "support_materials.zip"
    else:
        target = (root / relative_path).resolve()
        if root.resolve() not in target.parents and target != root.resolve():
            raise HTTPException(status_code=400, detail="非法路径")
    return root, target


def open_in_file_manager(target: Path) -> None:
    system = platform.system().lower()
    if system == "windows":
        if target.is_dir():
            subprocess.Popen(["explorer.exe", str(target)])
        else:
            subprocess.Popen(["explorer.exe", f"/select,{target}"])
        return
    if system == "darwin":
        subprocess.Popen(["open", str(target)] if target.is_dir() else ["open", "-R", str(target)])
        return
    folder = target if target.is_dir() else target.parent
    subprocess.Popen(["xdg-open", str(folder)])
