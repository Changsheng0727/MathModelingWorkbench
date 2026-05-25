from __future__ import annotations

import platform
import subprocess
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.services.analyzer import apply_problem_selection, build_analysis
from app.services.auto_workflow import run_auto_workflow
from app.services.backend_skills import (
    list_backend_skills,
    list_model_method_routes,
    list_model_selection_rubric,
    list_standard_paper_checklist,
    list_standard_paper_workflow,
    write_backend_skill_report,
)
from app.services.code_solution import run_code_result_pipeline
from app.services.code_graph import write_code_graph_report
from app.services.executor import detect_environments
from app.services.extractors import save_upload, unpack_upload, validate_upload_name
from app.services.extractors import safe_folder_target
from app.services.llm_assistant import (
    MODEL_ASSISTANT_PROGRESS_RELATIVE,
    run_baseline_llm_review,
    run_full_llm_refresh,
    run_custom_model_assistance,
    run_problem_llm_analysis,
    run_specialized_llm_review,
)
from app.services.llm_stream import bind_llm_stream, load_llm_live_stream
from app.services.llm_settings import clear_llm_settings, get_llm_settings, save_llm_settings
from app.services.modeling import generate_modeling_script, run_modeling_script
from app.services.paper import write_artifacts
from app.services.paper_fill import fill_paper_with_results
from app.services.parsers import extract_all_document_text, inventory_files
from app.services.reviewer import review_paper
from app.services.runner import compile_latex
from app.services.specialized import generate_specialized_script, run_specialized_script
from app.services.store import create_project, list_projects, load_json, make_support_zip, project_root, save_json
from app.services.templates import (
    DEFAULT_TEMPLATE_ID,
    create_template,
    delete_template,
    list_templates,
    validate_template_id,
)


app = FastAPI(title="Math Modeling Workbench", version="0.1.0")
static_dir = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=static_dir), name="static")

MAX_FOLDER_UPLOAD_FILES = 1200
MAX_FOLDER_UPLOAD_BYTES = 500 * 1024 * 1024


class LLMSettingsPayload(BaseModel):
    api_key: str | None = None
    base_url: str | None = None
    model: str | None = None


class PaperOptionsPayload(BaseModel):
    template_id: str | None = None
    target_body_pages: int | None = None


class ModelAssistantPayload(BaseModel):
    problem_ref: str
    model_name: str
    user_goal: str | None = None


class ProblemSelectionPayload(BaseModel):
    problem_id: str


@app.get("/")
def index() -> FileResponse:
    return FileResponse(static_dir / "index.html")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/environments")
def environments() -> dict:
    return detect_environments()


@app.get("/api/skills/backend")
def backend_skills() -> dict:
    return {
        "skills": list_backend_skills(),
        "standard_paper_workflow": list_standard_paper_workflow(),
        "standard_paper_checklist": list_standard_paper_checklist(),
        "model_method_routes": list_model_method_routes(),
        "model_selection_rubric": list_model_selection_rubric(),
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
        return save_llm_settings(payload.api_key, payload.base_url, payload.model)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


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


@app.get("/api/projects")
def projects() -> list[dict]:
    return list_projects()


@app.post("/api/projects")
async def create(file: UploadFile = File(...)) -> dict:
    if not file.filename:
        raise HTTPException(status_code=400, detail="缺少文件名")
    try:
        validate_upload_name(file.filename)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    meta = create_project(file.filename)
    root = Path(meta["root"])
    upload_path = root / "uploads" / Path(file.filename).name
    with upload_path.open("wb") as fh:
        while chunk := await file.read(1024 * 1024):
            fh.write(chunk)

    try:
        unpack_upload(upload_path, root / "raw")
        analyze_project_materials(root, meta)
    except Exception as exc:
        meta["status"] = "failed"
        meta["error"] = f"{type(exc).__name__}: {exc}"
        save_json(root / "metadata.json", meta)
        raise HTTPException(status_code=500, detail=meta["error"]) from exc

    return project_detail(meta["id"])


@app.post("/api/projects/folder")
async def create_from_folder(folder_name: str = Form("赛题文件夹"), files: list[UploadFile] = File(...)) -> dict:
    if not files:
        raise HTTPException(status_code=400, detail="请选择一个包含赛题材料的文件夹。")
    if len(files) > MAX_FOLDER_UPLOAD_FILES:
        raise HTTPException(status_code=400, detail=f"文件夹中文件过多，请控制在 {MAX_FOLDER_UPLOAD_FILES} 个以内。")

    meta = create_project(folder_name or "赛题文件夹")
    root = Path(meta["root"])
    raw_dir = root / "raw"
    upload_manifest = []
    total_bytes = 0

    try:
        for upload in files:
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
        analyze_project_materials(root, meta)
    except Exception as exc:
        meta["status"] = "failed"
        meta["error"] = f"{type(exc).__name__}: {exc}"
        save_json(root / "metadata.json", meta)
        raise HTTPException(status_code=500, detail=meta["error"]) from exc

    return project_detail(meta["id"])


def analyze_project_materials(root: Path, meta: dict) -> None:
    inventory = inventory_files(root / "raw")
    docs = extract_all_document_text(root / "raw")
    analysis = build_analysis(inventory, docs)
    analysis["project"] = {k: v for k, v in meta.items() if k != "root"}
    analysis["inventory"] = inventory
    artifacts = write_artifacts(root, analysis)
    save_json(root / "artifacts" / "analysis.json", analysis)
    if get_llm_settings().get("configured"):
        attach_artifacts_safely(meta, run_problem_llm_analysis(root, analysis))
        meta["llm_analysis_status"] = "success"
    else:
        meta["llm_analysis_status"] = "requires_api_key"
    meta["status"] = "analyzed"
    attach_artifacts_safely(meta, artifacts)
    save_json(root / "metadata.json", meta)


@app.get("/api/projects/{project_id}")
def project_detail(project_id: str) -> dict:
    try:
        root = project_root(project_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="项目不存在") from exc
    meta = load_json(root / "metadata.json")
    analysis_path = root / "artifacts" / "analysis.json"
    analysis = load_json(analysis_path) if analysis_path.exists() else None
    return {"metadata": {k: v for k, v in meta.items() if k != "root"}, "analysis": analysis}


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
    save_json(root / "metadata.json", meta)
    return {"artifacts": artifacts, "project": project_detail(project_id)}


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


@app.get("/api/projects/{project_id}/progress")
def project_progress(project_id: str) -> dict:
    try:
        root = project_root(project_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="项目不存在。") from exc
    meta = load_json(root / "metadata.json")
    progress_path = root / "artifacts" / "auto_workflow_progress.json"
    progress = load_json(progress_path) if progress_path.exists() else meta.get("auto_workflow_progress", {})
    if isinstance(progress, dict):
        progress = dict(progress)
        live_stream = load_llm_live_stream(root)
        if live_stream.get("channel") == "auto_workflow":
            progress["live_stream"] = live_stream
    return {
        "project_id": project_id,
        "status": meta.get("auto_workflow_status") or "idle",
        "progress": progress or {},
        "artifacts": meta.get("artifacts", {}),
        "error": meta.get("auto_workflow_error", ""),
    }


@app.get("/api/projects/{project_id}/llm/model-assistant/progress")
def project_model_assistant_progress(project_id: str) -> dict:
    try:
        root = project_root(project_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="项目不存在。") from exc
    meta = load_json(root / "metadata.json")
    progress_path = root / MODEL_ASSISTANT_PROGRESS_RELATIVE
    progress = load_json(progress_path) if progress_path.exists() else {}
    if isinstance(progress, dict):
        progress = dict(progress)
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
