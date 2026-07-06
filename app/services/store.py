from __future__ import annotations

import json
import re
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from app.config import PROJECTS_ROOT


PRIMARY_OUTPUT_KEYS = [
    "delivery_package",
    "paper_pdf",
    "paper_docx",
    "paper_llm",
    "paper_autofilled",
    "paper_result_filled",
    "computed_summary",
    "computed_manifest",
    "auto_workflow_report",
    "analysis_report",
]


def slugify(text: str) -> str:
    text = re.sub(r"[^\w\-\u4e00-\u9fff]+", "-", text, flags=re.UNICODE).strip("-")
    return text[:48] or "project"


def create_project(original_name: str) -> dict[str, Any]:
    project_id = f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"
    name = slugify(Path(original_name).stem)
    root = PROJECTS_ROOT / f"{project_id}-{name}"
    for child in ["uploads", "raw", "artifacts", "paper", "code", "results"]:
        (root / child).mkdir(parents=True, exist_ok=True)
    metadata = {
        "id": project_id,
        "name": name,
        "original_name": original_name,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "root": str(root),
        "status": "created",
        "paper_options": {
            "template_id": "builtin-default",
            "target_body_pages": None,
        },
    }
    save_json(root / "metadata.json", metadata)
    return metadata


def project_root(project_id: str) -> Path:
    name = str(project_id or "").strip()
    if not is_safe_project_lookup_name(name):
        raise FileNotFoundError(project_id)
    for root in sorted(PROJECTS_ROOT.iterdir()):
        if root.is_dir() and (root.name == name or root.name.startswith(f"{name}-")):
            return root
    raise FileNotFoundError(project_id)


def is_safe_project_lookup_name(name: str) -> bool:
    if not name or name in {".", ".."}:
        return False
    path = Path(name)
    return not path.is_absolute() and path.name == name


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        text = path.read_text(encoding="utf-8-sig")
        if text.startswith("\ufeff") or "UTF-8 BOM" in str(exc):
            return json.loads(text.lstrip("\ufeff"))
        raise


def attach_project_runtime_fields(meta: dict[str, Any], root: Path, meta_path: Path | None = None) -> dict[str, Any]:
    meta = dict(meta)
    stored_root = str(meta.get("root") or "")
    if stored_root and not same_path(Path(stored_root), root):
        meta["root_was_repaired"] = True
        meta["root_repair_notice"] = "项目路径已按当前目录自动校正。"
    meta["root"] = str(root)
    meta["project_updated_at"] = project_timestamp(meta_path or root / "metadata.json", root) or meta.get("created_at", "")
    return meta


def attach_project_artifact_fields(meta: dict[str, Any], root: Path, include_status: bool = True) -> dict[str, Any]:
    artifact_status = build_artifact_status(root, meta.get("artifacts"))
    artifact_summary = summarize_artifact_status(artifact_status)
    if include_status:
        meta["artifact_status"] = artifact_status
    meta["artifact_summary"] = artifact_summary
    meta["primary_output_path"] = primary_output_path(artifact_status)
    meta.update(describe_artifact_health(artifact_summary))
    return meta


def build_artifact_status(root: Path, artifacts: object) -> dict[str, dict[str, object]]:
    statuses: dict[str, dict[str, object]] = {}
    entries = artifacts if isinstance(artifacts, dict) else {}
    for key, value in entries.items():
        if isinstance(key, str) and isinstance(value, str) and value:
            statuses[key] = inspect_project_artifact(root, value)
    statuses["support_zip"] = {
        "path": "support.zip",
        "exists": True,
        "is_file": True,
        "generated_on_demand": True,
        "missing_reason": "",
    }
    return statuses


def summarize_artifact_status(statuses: dict[str, dict[str, object]]) -> dict[str, object]:
    total = len(statuses)
    available = sum(1 for item in statuses.values() if item.get("exists") is not False and item.get("is_file") is not False)
    unsafe = sum(1 for item in statuses.values() if item.get("unsafe_path"))
    size_bytes = sum(int(item.get("size_bytes") or 0) for item in statuses.values())
    modified = [
        (str(item.get("modified_at")), key, str(item.get("path") or ""))
        for key, item in statuses.items()
        if is_available_artifact(item) and item.get("modified_at")
    ]
    latest = max(modified) if modified else ("", "", "")
    return {
        "total": total,
        "available": available,
        "missing": total - available,
        "unsafe": unsafe,
        "size_bytes": size_bytes,
        "latest_modified_at": latest[0],
        "latest_key": latest[1],
        "latest_path": latest[2],
    }


def is_available_artifact(item: dict[str, object]) -> bool:
    return (
        item.get("exists") is not False
        and item.get("is_file") is not False
        and not item.get("unsafe_path")
        and not item.get("generated_on_demand")
    )


def primary_output_path(statuses: dict[str, dict[str, object]]) -> str:
    for key in PRIMARY_OUTPUT_KEYS:
        item = statuses.get(key) or {}
        if is_available_artifact(item):
            return str(item.get("path") or "")
    summary = summarize_artifact_status(statuses)
    return str(summary.get("latest_path") or "")


def format_artifact_size(size_bytes: object) -> str:
    try:
        size = float(size_bytes or 0)
    except (TypeError, ValueError):
        return ""
    if size <= 0:
        return ""
    for unit in ["B", "KB", "MB", "GB"]:
        if size < 1024 or unit == "GB":
            return f"{int(size)} B" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return ""


def artifact_summary_detail(summary: dict[str, object]) -> str:
    parts = []
    size = format_artifact_size(summary.get("size_bytes"))
    if size:
        parts.append(f"总大小 {size}")
    latest = str(summary.get("latest_modified_at") or "").replace("T", " ")[:16]
    if latest:
        parts.append(f"最近更新 {latest}")
    return "，".join(parts)


def describe_artifact_health(summary: dict[str, object]) -> dict[str, str]:
    total = int(summary.get("total") or 0)
    available = int(summary.get("available") or 0)
    missing = int(summary.get("missing") or 0)
    unsafe = int(summary.get("unsafe") or 0)
    detail = artifact_summary_detail(summary)
    detail_sentence = f"{detail}。" if detail else ""
    if unsafe:
        return {
            "artifact_health_status": "error",
            "artifact_health_label": f"路径异常 {unsafe}",
            "artifact_health_summary": f"可打开 {available}/{total} 个生成文件，{unsafe} 个路径不在项目目录内。{detail_sentence}",
        }
    if missing:
        return {
            "artifact_health_status": "warning",
            "artifact_health_label": f"文件缺失 {missing}",
            "artifact_health_summary": f"可打开 {available}/{total} 个生成文件，{missing} 个文件尚未生成或已移动。{detail_sentence}",
        }
    if total > 1:
        return {
            "artifact_health_status": "success",
            "artifact_health_label": f"文件 {available}/{total}",
            "artifact_health_summary": f"生成文件均可打开：{available}/{total}。{detail_sentence}",
        }
    return {
        "artifact_health_status": "pending",
        "artifact_health_label": "暂无生成文件",
        "artifact_health_summary": "项目还没有生成论文、结果或报告文件。",
    }


def inspect_project_artifact(root: Path, relative_path: str) -> dict[str, object]:
    status: dict[str, object] = {
        "path": relative_path,
        "exists": False,
        "is_file": False,
        "missing_reason": "文件尚未生成或已被移动",
    }
    try:
        resolved_root = root.resolve()
        target = (root / relative_path).resolve()
    except OSError as exc:
        status["missing_reason"] = f"路径无法读取：{type(exc).__name__}"
        return status
    if target != resolved_root and resolved_root not in target.parents:
        status["missing_reason"] = "路径不在当前项目目录内"
        status["unsafe_path"] = True
        return status
    if not target.exists():
        return status
    status["exists"] = True
    status["is_file"] = target.is_file()
    status["missing_reason"] = "" if target.is_file() else "目标不是文件"
    try:
        stat = target.stat()
        status["size_bytes"] = stat.st_size
        status["modified_at"] = datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds")
    except OSError:
        pass
    return status


def same_path(left: Path, right: Path) -> bool:
    try:
        return left.resolve() == right.resolve()
    except OSError:
        return left.absolute() == right.absolute()


def project_timestamp(path: Path, fallback: Path) -> str:
    for target in [path, fallback]:
        try:
            return datetime.fromtimestamp(target.stat().st_mtime).isoformat(timespec="seconds")
        except OSError:
            continue
    return ""


def project_metadata_error_stub(root: Path, exc: Exception) -> dict[str, Any]:
    project_id, name = project_identity_from_folder(root.name)
    updated_at = project_timestamp(root / "metadata.json", root)
    error = f"{type(exc).__name__}: {exc}"
    return {
        "id": project_id,
        "name": name,
        "original_name": root.name,
        "created_at": updated_at,
        "project_updated_at": updated_at,
        "root": str(root),
        "status": "metadata_error",
        "metadata_error": error,
        "artifact_summary": {
            "total": 0,
            "available": 0,
            "missing": 0,
            "unsafe": 0,
            "size_bytes": 0,
            "latest_modified_at": "",
            "latest_key": "",
            "latest_path": "",
        },
        "primary_output_path": "",
        "artifact_health_status": "error",
        "artifact_health_label": "元数据异常",
        "artifact_health_summary": f"metadata.json 无法读取：{error}",
    }


def project_identity_from_folder(folder_name: str) -> tuple[str, str]:
    match = re.match(r"^(\d{8}-\d{6}-[0-9a-fA-F]{8})(?:-(.*))?$", folder_name)
    if match:
        return match.group(1), match.group(2) or folder_name
    return folder_name, folder_name


def list_projects() -> list[dict[str, Any]]:
    projects = []
    for root in sorted(PROJECTS_ROOT.glob("*"), reverse=True):
        if not root.is_dir():
            continue
        meta_path = root / "metadata.json"
        if not meta_path.exists():
            projects.append(project_metadata_error_stub(root, FileNotFoundError("metadata.json is missing")))
            continue
        try:
            meta = load_json(meta_path)
            if not isinstance(meta, dict):
                raise ValueError("metadata.json must contain a JSON object")
        except Exception as exc:
            projects.append(project_metadata_error_stub(root, exc))
            continue
        analysis_path = root / "artifacts" / "analysis.json"
        if analysis_path.exists():
            meta["analysis_available"] = True
        meta = attach_project_runtime_fields(meta, root, meta_path)
        projects.append(attach_project_artifact_fields(meta, root, include_status=False))
    projects.sort(key=lambda item: item.get("project_updated_at") or item.get("created_at") or "", reverse=True)
    return projects


def make_support_zip(root: Path) -> Path:
    target = root / "artifacts" / "support_materials"
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True, exist_ok=True)
    for folder_name in ["artifacts", "paper", "code", "results"]:
        source = root / folder_name
        if not source.exists():
            continue
        dest = target / folder_name
        shutil.copytree(source, dest, ignore=shutil.ignore_patterns("support_materials", "*.zip"))
    zip_base = root / "artifacts" / "support_materials"
    archive = shutil.make_archive(str(zip_base), "zip", target)
    return Path(archive)
