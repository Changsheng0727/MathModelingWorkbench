from __future__ import annotations

import hashlib
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

from app.services.delivery_readiness import DELIVERY_READINESS_JSON_RELATIVE, write_delivery_readiness_report
from app.services.store import load_json, save_json


DELIVERY_PACKAGE_RELATIVE = "artifacts/delivery_package.zip"
DELIVERY_PACKAGE_MANIFEST_RELATIVE = "artifacts/delivery_package_manifest.md"
DELIVERY_PACKAGE_MANIFEST_JSON_RELATIVE = "artifacts/delivery_package_manifest.json"

PACKAGE_EXCLUDED_NAMES = {
    "delivery_package.zip",
    "delivery_package_manifest.md",
    "delivery_package_manifest.json",
    "support_materials.zip",
}


def write_delivery_package(root: Path, meta: dict[str, Any] | None = None) -> dict[str, str]:
    metadata = meta if isinstance(meta, dict) else load_json(root / "metadata.json")
    write_delivery_readiness_report(root, metadata)
    readiness = load_json_if_exists(root / DELIVERY_READINESS_JSON_RELATIVE)
    files = collect_delivery_files(root)
    manifest = build_package_manifest(root, metadata, readiness, files)

    save_json(root / DELIVERY_PACKAGE_MANIFEST_JSON_RELATIVE, manifest)
    (root / DELIVERY_PACKAGE_MANIFEST_RELATIVE).write_text(render_package_manifest(manifest), encoding="utf-8")

    package_path = root / DELIVERY_PACKAGE_RELATIVE
    package_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(package_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("DELIVERY_README.md", render_package_readme(manifest))
        archive.write(root / DELIVERY_PACKAGE_MANIFEST_JSON_RELATIVE, "DELIVERY_MANIFEST.json")
        archive.write(root / DELIVERY_PACKAGE_MANIFEST_RELATIVE, "DELIVERY_MANIFEST.md")
        for item in files:
            relative = item.get("path", "")
            if not relative:
                continue
            source = root / relative
            if source.exists() and source.is_file():
                archive.write(source, package_arcname(relative))

    package_size = package_path.stat().st_size
    package_sha = sha256_file(package_path)
    manifest["package"] = {
        "path": DELIVERY_PACKAGE_RELATIVE,
        "size_bytes": package_size,
        "sha256": package_sha,
    }
    save_json(root / DELIVERY_PACKAGE_MANIFEST_JSON_RELATIVE, manifest)
    (root / DELIVERY_PACKAGE_MANIFEST_RELATIVE).write_text(render_package_manifest(manifest), encoding="utf-8")

    if isinstance(meta, dict):
        meta["delivery_package_status"] = "success"
        meta["delivery_package_generated_at"] = manifest["generated_at"]
        meta["delivery_package_file_count"] = len(files)
        meta["delivery_package_size_bytes"] = package_size
        meta["delivery_package_sha256"] = package_sha
        meta["delivery_package_summary"] = (
            f"交付包已生成：{len(files)} 个文件，{format_bytes(package_size)}，SHA256 {package_sha[:12]}..."
        )
        meta.setdefault("artifacts", {}).update(delivery_package_artifacts())

    return delivery_package_artifacts()


def delivery_package_artifacts() -> dict[str, str]:
    return {
        "delivery_package": DELIVERY_PACKAGE_RELATIVE,
        "delivery_package_manifest": DELIVERY_PACKAGE_MANIFEST_RELATIVE,
        "delivery_package_manifest_json": DELIVERY_PACKAGE_MANIFEST_JSON_RELATIVE,
    }


def build_package_manifest(
    root: Path,
    metadata: dict[str, Any],
    readiness: dict[str, Any],
    files: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "stage": "delivery_package",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "project": {
            "id": metadata.get("id", ""),
            "name": metadata.get("name", ""),
            "original_name": metadata.get("original_name", ""),
            "created_at": metadata.get("created_at", ""),
        },
        "readiness": {
            "status": readiness.get("status") or metadata.get("delivery_readiness_status", ""),
            "label": readiness.get("label") or metadata.get("delivery_readiness_label", ""),
            "score": readiness.get("score") or metadata.get("delivery_readiness_score", 0),
            "summary": readiness.get("summary") or metadata.get("delivery_readiness_summary", ""),
            "can_submit": readiness.get("can_submit", metadata.get("delivery_readiness_can_submit", False)),
            "warning_count": readiness.get("warning_count", 0),
            "required_missing_count": len(readiness.get("required_missing") or []),
        },
        "file_count": len(files),
        "total_source_bytes": sum(int(item.get("size_bytes") or 0) for item in files),
        "files": files,
        "package": {},
        "notes": [
            "该交付包由系统自动生成，包含论文、结果、代码、报告和审计清单。",
            "manifest 中的 SHA256 可用于核验交付文件未被修改。",
        ],
    }


def collect_delivery_files(root: Path) -> list[dict[str, Any]]:
    candidates: dict[str, Path] = {}
    for folder in ["paper", "results", "code", "artifacts"]:
        base = root / folder
        if not base.exists():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file() or is_excluded(path):
                continue
            relative = path.relative_to(root).as_posix()
            candidates[relative] = path

    files = [describe_file(root, path) for _, path in sorted(candidates.items())]
    return [item for item in files if item]


def is_excluded(path: Path) -> bool:
    parts = set(path.parts)
    if "support_materials" in parts:
        return True
    if path.name in PACKAGE_EXCLUDED_NAMES:
        return True
    return path.suffix.lower() == ".zip"


def describe_file(root: Path, path: Path) -> dict[str, Any]:
    stat = path.stat()
    relative = path.relative_to(root).as_posix()
    return {
        "path": relative,
        "package_path": package_arcname(relative),
        "size_bytes": stat.st_size,
        "sha256": sha256_file(path),
        "category": file_category(relative),
        "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
    }


def package_arcname(relative: str) -> str:
    category = file_category(relative)
    folder = {
        "paper": "01_paper",
        "results": "02_results",
        "code": "03_code",
        "reports": "04_reports",
        "logs": "05_logs",
    }.get(category, "06_support")
    return f"{folder}/{relative}"


def file_category(relative: str) -> str:
    lower = relative.lower()
    if lower.startswith("paper/") or lower.endswith((".pdf", ".docx", ".tex")):
        return "paper"
    if lower.startswith("results/") or lower.endswith((".csv", ".xlsx", ".xls", ".json")) and "manifest" in lower:
        return "results"
    if lower.startswith("code/") or lower.endswith((".py", ".ipynb", ".r", ".m")):
        return "code"
    if lower.endswith((".log", ".out", ".err")):
        return "logs"
    if lower.startswith("artifacts/"):
        return "reports"
    return "support"


def render_package_manifest(manifest: dict[str, Any]) -> str:
    readiness = manifest.get("readiness", {})
    package = manifest.get("package", {})
    lines = [
        "# 正式交付包清单",
        "",
        f"- 生成时间：{manifest.get('generated_at', '-')}",
        f"- 项目：{manifest.get('project', {}).get('name') or manifest.get('project', {}).get('id') or '-'}",
        f"- 交付状态：{readiness.get('label', '-')}",
        f"- 交付分：{readiness.get('score', '-')}",
        f"- 可提交：{readiness.get('can_submit')}",
        f"- 文件数：{manifest.get('file_count', 0)}",
        f"- 源文件总量：{format_bytes(manifest.get('total_source_bytes', 0))}",
    ]
    if package:
        lines.extend(
            [
                f"- 压缩包：`{package.get('path', '-')}`",
                f"- 压缩包大小：{format_bytes(package.get('size_bytes', 0))}",
                f"- 压缩包 SHA256：`{package.get('sha256', '-')}`",
            ]
        )
    lines.extend(["", "## 交付摘要", "", readiness.get("summary") or "暂无交付摘要。", "", "## 文件清单"])
    for item in manifest.get("files", []):
        lines.append(
            f"- `{item.get('path')}` -> `{item.get('package_path')}` "
            f"({format_bytes(item.get('size_bytes', 0))}, {item.get('sha256', '')[:12]}...)"
        )
    return "\n".join(lines) + "\n"


def render_package_readme(manifest: dict[str, Any]) -> str:
    readiness = manifest.get("readiness", {})
    return "\n".join(
        [
            "# ModelArk 交付包",
            "",
            f"项目：{manifest.get('project', {}).get('name') or manifest.get('project', {}).get('id') or '-'}",
            f"生成时间：{manifest.get('generated_at', '-')}",
            f"交付状态：{readiness.get('label', '-')}",
            f"交付分：{readiness.get('score', '-')}",
            "",
            "目录说明：",
            "- `01_paper/`：论文 PDF、Word、LaTeX 源文件。",
            "- `02_results/`：结果表、图和计算 manifest。",
            "- `03_code/`：可复现求解代码。",
            "- `04_reports/`：分析、审查、修复、性能和交付报告。",
            "- `05_logs/`：编译和运行日志。",
            "",
            "请使用 `DELIVERY_MANIFEST.json` 或 `DELIVERY_MANIFEST.md` 核对文件清单与哈希。",
            "",
        ]
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def format_bytes(value: Any) -> str:
    try:
        size = float(value)
    except (TypeError, ValueError):
        size = 0
    units = ["B", "KB", "MB", "GB"]
    for unit in units:
        if size < 1024 or unit == units[-1]:
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024
    return f"{size:.1f} GB"


def load_json_if_exists(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = load_json(path)
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}
