from __future__ import annotations

import asyncio
import platform
import subprocess
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.services.analyzer import apply_problem_selection, build_analysis
from app.services.analysis_progress import AnalysisProgress, load_analysis_progress
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
    return list_projects()


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
    if progress:
        recommended = analysis.get("recommended_problem", {}) or {}
        progress.finish_step(
            "success",
            f"识别到 {len(analysis.get('problems', []))} 个候选题；当前推荐 {recommended.get('id', '-')} 题：{recommended.get('title', '')}",
        )
        progress.start_step("write_artifacts", "生成分析报告与论文骨架", "正在写入 analysis.json、分析报告、论文提纲、模型方案和 LaTeX 骨架。")

    artifacts = write_artifacts(root, analysis)
    save_json(root / "artifacts" / "analysis.json", analysis)
    if progress:
        progress.finish_step("success", "分析报告、论文提纲、模型方案和 LaTeX 骨架已生成。")

    if get_llm_settings().get("configured"):
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
