from __future__ import annotations

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any

from app.config import SETTINGS_ROOT
from app.services.delivery_package import DELIVERY_PACKAGE_RELATIVE, write_delivery_package
from app.services.delivery_readiness import DELIVERY_READINESS_JSON_RELATIVE, write_delivery_readiness_report
from app.services.store import load_json, save_json


DEFAULT_BATCH_WORKERS = 4
_LEDGER_PATH = SETTINGS_ROOT / "delivery_package_batches.json"
_LEDGER_LOCK = threading.RLock()


def build_batch_delivery_packages(
    projects: list[dict[str, Any]],
    *,
    force: bool = False,
    max_workers: int = DEFAULT_BATCH_WORKERS,
) -> dict[str, Any]:
    started_at = datetime.now()
    candidates = [project for project in projects if isinstance(project, dict) and project.get("id")]
    workers = max(1, min(8, int(max_workers or DEFAULT_BATCH_WORKERS), max(1, len(candidates) or 1)))
    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="delivery-package") as executor:
        futures = {executor.submit(package_project, project, force): project for project in candidates}
        for future in as_completed(futures):
            try:
                results.append(future.result())
            except Exception as exc:
                project = futures[future]
                results.append(
                    {
                        "project_id": project.get("id", ""),
                        "project_name": project.get("name", ""),
                        "status": "failed",
                        "reason": f"{type(exc).__name__}: {exc}",
                    }
                )
    results.sort(key=lambda item: (status_order(item.get("status")), str(item.get("project_name") or item.get("project_id") or "")))
    packaged = [item for item in results if item.get("status") == "packaged"]
    skipped = [item for item in results if item.get("status") == "skipped"]
    failed = [item for item in results if item.get("status") == "failed"]
    finished_at = datetime.now()
    batch = {
        "id": uuid.uuid4().hex,
        "stage": "batch_delivery_package",
        "generated_at": finished_at.isoformat(timespec="seconds"),
        "started_at": started_at.isoformat(timespec="seconds"),
        "duration_seconds": max(0, int(round((finished_at - started_at).total_seconds()))),
        "force": bool(force),
        "max_workers": workers,
        "requested_count": len(candidates),
        "packaged_count": len(packaged),
        "skipped_count": len(skipped),
        "failed_count": len(failed),
        "total_package_bytes": sum(int(item.get("package_size_bytes") or 0) for item in packaged),
        "summary": batch_summary(len(candidates), len(packaged), len(skipped), len(failed), workers),
        "results": results,
    }
    record_delivery_batch(batch)
    return batch


def list_delivery_package_batches(limit: int = 20) -> dict[str, Any]:
    limit = max(1, min(100, int(limit or 20)))
    with _LEDGER_LOCK:
        ledger = load_delivery_batch_ledger()
        batches = ledger.get("batches", [])
        public_batches = [normalize_delivery_batch(row, include_results=True) for row in batches[:limit] if isinstance(row, dict)]
        return {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "ledger_path": str(_LEDGER_PATH),
            "total_tracked": len(batches),
            "latest": public_batches[0] if public_batches else {},
            "batches": public_batches,
        }


def record_delivery_batch(batch: dict[str, Any], limit: int = 120) -> None:
    compact = normalize_delivery_batch(batch, include_results=True)
    if not compact.get("id"):
        return
    with _LEDGER_LOCK:
        ledger = load_delivery_batch_ledger()
        existing = ledger.get("batches", [])
        rows = [compact]
        rows.extend(row for row in existing if isinstance(row, dict) and row.get("id") != compact.get("id"))
        payload = {
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "batches": rows[: max(1, min(500, int(limit or 120)))],
        }
        try:
            save_json(_LEDGER_PATH, payload)
        except Exception:
            pass


def load_delivery_batch_ledger() -> dict[str, Any]:
    if not _LEDGER_PATH.exists():
        return {"updated_at": "", "batches": []}
    try:
        payload = load_json(_LEDGER_PATH)
    except Exception:
        return {"updated_at": "", "batches": []}
    rows = payload.get("batches") if isinstance(payload, dict) else []
    if not isinstance(rows, list):
        rows = []
    normalized = [normalize_delivery_batch(row, include_results=True) for row in rows if isinstance(row, dict)]
    normalized.sort(key=lambda item: str(item.get("generated_at") or item.get("started_at") or ""), reverse=True)
    return {
        "updated_at": str(payload.get("updated_at") or "") if isinstance(payload, dict) else "",
        "batches": normalized,
    }


def normalize_delivery_batch(batch: dict[str, Any], *, include_results: bool = False) -> dict[str, Any]:
    results = batch.get("results") if isinstance(batch.get("results"), list) else []
    public = {
        "id": str(batch.get("id") or ""),
        "stage": str(batch.get("stage") or "batch_delivery_package"),
        "generated_at": str(batch.get("generated_at") or ""),
        "started_at": str(batch.get("started_at") or ""),
        "duration_seconds": int(batch.get("duration_seconds") or 0),
        "force": bool(batch.get("force")),
        "max_workers": int(batch.get("max_workers") or 0),
        "requested_count": int(batch.get("requested_count") or 0),
        "packaged_count": int(batch.get("packaged_count") or 0),
        "skipped_count": int(batch.get("skipped_count") or 0),
        "failed_count": int(batch.get("failed_count") or 0),
        "total_package_bytes": int(batch.get("total_package_bytes") or 0),
        "summary": str(batch.get("summary") or ""),
    }
    if include_results:
        public["results"] = [compact_delivery_batch_result(item) for item in results[:80] if isinstance(item, dict)]
    return public


def compact_delivery_batch_result(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "project_id": str(item.get("project_id") or ""),
        "project_name": str(item.get("project_name") or ""),
        "status": str(item.get("status") or ""),
        "reason": str(item.get("reason") or ""),
        "detail": str(item.get("detail") or ""),
        "readiness_status": str(item.get("readiness_status") or ""),
        "delivery_score": item.get("delivery_score", 0),
        "package_path": str(item.get("package_path") or ""),
        "package_size_bytes": int(item.get("package_size_bytes") or 0),
    }


def package_project(project: dict[str, Any], force: bool) -> dict[str, Any]:
    project_id = str(project.get("id") or "")
    project_name = str(project.get("name") or project.get("original_name") or project_id)
    root_value = project.get("root")
    if not root_value:
        return skipped(project_id, project_name, "missing_root", "项目元数据缺少 root，无法定位项目目录。")
    root = Path(str(root_value))
    metadata_path = root / "metadata.json"
    if not metadata_path.exists():
        return skipped(project_id, project_name, "missing_metadata", "项目缺少 metadata.json。")

    meta = load_json(metadata_path)
    write_delivery_readiness_report(root, meta)
    readiness = load_json(root / DELIVERY_READINESS_JSON_RELATIVE)
    if not readiness.get("can_submit"):
        meta["delivery_batch_package_status"] = "skipped"
        meta["delivery_batch_package_reason"] = readiness.get("summary") or "交付就绪未通过。"
        save_json(metadata_path, meta)
        return skipped(project_id, project_name, "not_deliverable", meta["delivery_batch_package_reason"], readiness)

    package_path = root / DELIVERY_PACKAGE_RELATIVE
    if package_path.exists() and meta.get("delivery_package_status") == "success" and not force:
        meta["delivery_batch_package_status"] = "skipped"
        meta["delivery_batch_package_reason"] = "already_packaged"
        meta["delivery_batch_package_checked_at"] = datetime.now().isoformat(timespec="seconds")
        save_json(metadata_path, meta)
        return {
            "project_id": project_id,
            "project_name": project_name,
            "status": "skipped",
            "reason": "already_packaged",
            "detail": "正式交付包已存在。",
            "readiness_status": readiness.get("status", ""),
            "delivery_score": readiness.get("score", 0),
            "package_path": DELIVERY_PACKAGE_RELATIVE,
            "package_size_bytes": package_path.stat().st_size,
            "package_sha256": meta.get("delivery_package_sha256", ""),
        }

    artifacts = write_delivery_package(root, meta)
    meta["delivery_batch_package_status"] = "success"
    meta["delivery_batch_package_generated_at"] = datetime.now().isoformat(timespec="seconds")
    save_json(metadata_path, meta)
    return {
        "project_id": project_id,
        "project_name": project_name,
        "status": "packaged",
        "reason": "generated",
        "detail": meta.get("delivery_package_summary", "正式交付包已生成。"),
        "readiness_status": readiness.get("status", ""),
        "delivery_score": readiness.get("score", 0),
        "artifacts": artifacts,
        "package_path": artifacts.get("delivery_package", DELIVERY_PACKAGE_RELATIVE),
        "package_size_bytes": meta.get("delivery_package_size_bytes", 0),
        "package_sha256": meta.get("delivery_package_sha256", ""),
    }


def skipped(project_id: str, project_name: str, reason: str, detail: str, readiness: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = {
        "project_id": project_id,
        "project_name": project_name,
        "status": "skipped",
        "reason": reason,
        "detail": detail,
    }
    if readiness:
        payload["readiness_status"] = readiness.get("status", "")
        payload["delivery_score"] = readiness.get("score", 0)
    return payload


def batch_summary(requested: int, packaged: int, skipped_count: int, failed: int, workers: int) -> str:
    return f"并发 {workers} 线程处理 {requested} 个项目：生成 {packaged} 个，跳过 {skipped_count} 个，失败 {failed} 个。"


def status_order(status: Any) -> int:
    return {"packaged": 0, "failed": 1, "skipped": 2}.get(str(status), 9)
