from __future__ import annotations

import json
import re
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from app.config import PROJECTS_ROOT


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
    matches = sorted(PROJECTS_ROOT.glob(f"{project_id}-*"))
    if not matches:
        raise FileNotFoundError(project_id)
    return matches[0]


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


def project_metadata_error_stub(root: Path, exc: Exception) -> dict[str, Any]:
    project_id, name = project_identity_from_folder(root.name)
    try:
        created_at = datetime.fromtimestamp(root.stat().st_mtime).isoformat(timespec="seconds")
    except OSError:
        created_at = ""
    return {
        "id": project_id,
        "name": name,
        "original_name": root.name,
        "created_at": created_at,
        "root": str(root),
        "status": "metadata_error",
        "metadata_error": f"{type(exc).__name__}: {exc}",
    }


def project_identity_from_folder(folder_name: str) -> tuple[str, str]:
    match = re.match(r"^(\d{8}-\d{6}-[0-9a-fA-F]{8})(?:-(.*))?$", folder_name)
    if match:
        return match.group(1), match.group(2) or folder_name
    return folder_name, folder_name


def list_projects() -> list[dict[str, Any]]:
    projects = []
    for root in sorted(PROJECTS_ROOT.glob("*"), reverse=True):
        meta_path = root / "metadata.json"
        if meta_path.exists():
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
            projects.append(meta)
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
