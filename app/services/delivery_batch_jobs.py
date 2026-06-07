from __future__ import annotations

import threading
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime
from typing import Any

from app.config import SETTINGS_ROOT
from app.services.capacity_settings import load_capacity_settings, save_capacity_settings
from app.services.delivery_batch import build_batch_delivery_packages
from app.services.store import load_json, save_json


ACTIVE_JOB_STATUSES = {"queued", "running"}
TERMINAL_JOB_STATUSES = {"success", "failed", "cancelled"}
_LOCK = threading.RLock()
_JOBS: dict[str, dict[str, Any]] = {}
_FUTURES: dict[str, Future] = {}
_LEDGER_PATH = SETTINGS_ROOT / "delivery_package_batch_jobs.json"
_LEDGER_LOADED = False


def resolve_worker_count() -> int:
    return int(load_capacity_settings().get("delivery_batch_job_workers") or 1)


_WORKER_COUNT = resolve_worker_count()
_EXECUTOR = ThreadPoolExecutor(max_workers=_WORKER_COUNT, thread_name_prefix="delivery-batch-job")


def configure_delivery_batch_job_capacity(worker_count: int) -> dict[str, Any]:
    global _WORKER_COUNT, _EXECUTOR
    settings = save_capacity_settings({"delivery_batch_job_workers": worker_count})
    requested = int(settings.get("delivery_batch_job_workers") or _WORKER_COUNT)
    with _LOCK:
        changed = requested != _WORKER_COUNT
        old_executor = _EXECUTOR if changed else None
        if changed:
            _WORKER_COUNT = requested
            _EXECUTOR = ThreadPoolExecutor(max_workers=_WORKER_COUNT, thread_name_prefix="delivery-batch-job")
            persist_jobs_locked()
    if old_executor:
        old_executor.shutdown(wait=False, cancel_futures=False)
    return {
        "changed": changed,
        "delivery_batch_jobs": list_delivery_batch_jobs(),
        "capacity_settings": load_capacity_settings(),
    }


def start_delivery_batch_job(
    projects: list[dict[str, Any]],
    *,
    force: bool = False,
    max_workers: int = 4,
) -> dict[str, Any]:
    project_snapshot = [project for project in projects if isinstance(project, dict) and project.get("id")]
    job_id = uuid.uuid4().hex
    job = {
        "id": job_id,
        "kind": "delivery_batch",
        "status": "queued",
        "submitted_at": now_iso(),
        "started_at": "",
        "finished_at": "",
        "error": "",
        "force": bool(force),
        "max_workers": max(1, min(8, int(max_workers or 4))),
        "requested_count": len(project_snapshot),
        "packaged_count": 0,
        "skipped_count": 0,
        "failed_count": 0,
        "total_package_bytes": 0,
        "batch_id": "",
        "summary": "批量交付包任务已入队。",
        "project_ids": [str(project.get("id") or "") for project in project_snapshot],
        "projects": project_snapshot,
    }
    with _LOCK:
        load_job_ledger_locked()
        prune_finished_jobs_locked()
        _JOBS[job_id] = job
        persist_jobs_locked()
        future = _EXECUTOR.submit(run_delivery_batch_job, job_id)
        _FUTURES[job_id] = future
        return public_job(job)


def get_delivery_batch_job(job_id: str) -> dict[str, Any]:
    with _LOCK:
        load_job_ledger_locked()
        job = _JOBS.get(job_id)
        return public_job(job) if job else {}


def list_delivery_batch_jobs(limit: int = 60) -> dict[str, Any]:
    with _LOCK:
        load_job_ledger_locked()
        prune_finished_jobs_locked()
        persist_jobs_locked()
        jobs = sorted(_JOBS.values(), key=lambda item: str(item.get("submitted_at") or ""), reverse=True)
        public_jobs = [public_job(job) for job in jobs[: max(1, min(200, limit))]]
        running_count = sum(1 for job in _JOBS.values() if job.get("status") == "running")
        queued_count = sum(1 for job in _JOBS.values() if job.get("status") == "queued")
        active_count = running_count + queued_count
        finished_count = sum(1 for job in _JOBS.values() if job.get("status") not in ACTIVE_JOB_STATUSES)
        return {
            "generated_at": now_iso(),
            "capacity": _WORKER_COUNT,
            "running_count": running_count,
            "queued_count": queued_count,
            "active_count": active_count,
            "finished_count": finished_count,
            "total_tracked": len(_JOBS),
            "available_slots": max(0, _WORKER_COUNT - running_count),
            "ledger_path": str(_LEDGER_PATH),
            "capacity_settings": load_capacity_settings(),
            "jobs": public_jobs,
        }


def run_delivery_batch_job(job_id: str) -> None:
    with _LOCK:
        job = _JOBS.get(job_id)
        if not job or job.get("status") == "cancelled":
            return
        job["status"] = "running"
        job["started_at"] = now_iso()
        job["summary"] = "批量交付包任务正在运行。"
        persist_jobs_locked()

    try:
        batch = build_batch_delivery_packages(
            list(job.get("projects") or []),
            force=bool(job.get("force")),
            max_workers=int(job.get("max_workers") or 4),
        )
        with _LOCK:
            job = _JOBS.get(job_id)
            if not job:
                return
            job["status"] = "failed" if int(batch.get("failed_count") or 0) else "success"
            job["finished_at"] = now_iso()
            job["batch_id"] = str(batch.get("id") or "")
            job["requested_count"] = int(batch.get("requested_count") or 0)
            job["packaged_count"] = int(batch.get("packaged_count") or 0)
            job["skipped_count"] = int(batch.get("skipped_count") or 0)
            job["failed_count"] = int(batch.get("failed_count") or 0)
            job["total_package_bytes"] = int(batch.get("total_package_bytes") or 0)
            job["summary"] = str(batch.get("summary") or "")
            job["projects"] = []
            persist_jobs_locked()
    except Exception as exc:
        with _LOCK:
            job = _JOBS.get(job_id)
            if not job:
                return
            job["status"] = "failed"
            job["finished_at"] = now_iso()
            job["error"] = f"{type(exc).__name__}: {exc}"
            job["summary"] = job["error"]
            job["projects"] = []
            persist_jobs_locked()


def public_job(job: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(job, dict):
        return {}
    status = str(job.get("status") or "")
    return {
        "id": str(job.get("id") or ""),
        "kind": "delivery_batch",
        "label": "批量交付包",
        "status": status,
        "submitted_at": str(job.get("submitted_at") or ""),
        "started_at": str(job.get("started_at") or ""),
        "finished_at": str(job.get("finished_at") or ""),
        "error": str(job.get("error") or ""),
        "force": bool(job.get("force")),
        "max_workers": int(job.get("max_workers") or 0),
        "requested_count": int(job.get("requested_count") or 0),
        "packaged_count": int(job.get("packaged_count") or 0),
        "skipped_count": int(job.get("skipped_count") or 0),
        "failed_count": int(job.get("failed_count") or 0),
        "total_package_bytes": int(job.get("total_package_bytes") or 0),
        "batch_id": str(job.get("batch_id") or ""),
        "summary": str(job.get("summary") or ""),
        "project_ids": list(job.get("project_ids") or [])[:80],
        "wait_seconds": elapsed_seconds(job.get("submitted_at"), job.get("started_at") if job.get("started_at") else None)
        if status != "queued"
        else elapsed_seconds(job.get("submitted_at"), None),
        "run_seconds": elapsed_seconds(job.get("started_at"), job.get("finished_at") if job.get("finished_at") else None)
        if job.get("started_at")
        else 0,
    }


def load_job_ledger_locked() -> None:
    global _LEDGER_LOADED
    if _LEDGER_LOADED:
        return
    _LEDGER_LOADED = True
    if not _LEDGER_PATH.exists():
        return
    try:
        payload = load_json(_LEDGER_PATH)
    except Exception:
        return
    rows = payload.get("jobs") if isinstance(payload, dict) else []
    if not isinstance(rows, list):
        return
    recovered_at = now_iso()
    for row in rows:
        if not isinstance(row, dict) or not row.get("id"):
            continue
        job = normalize_ledger_job(row)
        if not job:
            continue
        if job.get("status") in ACTIVE_JOB_STATUSES:
            job["status"] = "failed"
            job["finished_at"] = recovered_at
            job["error"] = "服务在批量任务完成前重启。"
            job["summary"] = job["error"]
        _JOBS.setdefault(str(job["id"]), job)
    prune_finished_jobs_locked()
    persist_jobs_locked()


def persist_jobs_locked(limit: int = 220) -> None:
    rows = sorted(_JOBS.values(), key=lambda item: str(item.get("submitted_at") or ""), reverse=True)
    payload = {
        "updated_at": now_iso(),
        "capacity": _WORKER_COUNT,
        "jobs": [serialize_job_for_ledger(job) for job in rows[:limit]],
    }
    try:
        save_json(_LEDGER_PATH, payload)
    except Exception:
        pass


def normalize_ledger_job(row: dict[str, Any]) -> dict[str, Any]:
    job_id = str(row.get("id") or "").strip()
    if not job_id:
        return {}
    return {
        "id": job_id,
        "kind": "delivery_batch",
        "status": str(row.get("status") or ""),
        "submitted_at": str(row.get("submitted_at") or ""),
        "started_at": str(row.get("started_at") or ""),
        "finished_at": str(row.get("finished_at") or ""),
        "error": str(row.get("error") or ""),
        "force": bool(row.get("force")),
        "max_workers": int(row.get("max_workers") or 0),
        "requested_count": int(row.get("requested_count") or 0),
        "packaged_count": int(row.get("packaged_count") or 0),
        "skipped_count": int(row.get("skipped_count") or 0),
        "failed_count": int(row.get("failed_count") or 0),
        "total_package_bytes": int(row.get("total_package_bytes") or 0),
        "batch_id": str(row.get("batch_id") or ""),
        "summary": str(row.get("summary") or ""),
        "project_ids": list(row.get("project_ids") or [])[:80],
        "projects": [],
    }


def serialize_job_for_ledger(job: dict[str, Any]) -> dict[str, Any]:
    payload = normalize_ledger_job(job)
    payload.pop("projects", None)
    return payload


def prune_finished_jobs_locked(limit: int = 160) -> None:
    if len(_JOBS) <= limit:
        return
    finished = [job for job in _JOBS.values() if job.get("status") not in ACTIVE_JOB_STATUSES]
    finished.sort(key=lambda item: str(item.get("finished_at") or item.get("submitted_at") or ""))
    for job in finished[: max(0, len(_JOBS) - limit)]:
        job_id = str(job.get("id") or "")
        if job_id:
            _JOBS.pop(job_id, None)
            _FUTURES.pop(job_id, None)


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def elapsed_seconds(start: Any, end: Any = None) -> int:
    started = parse_time(start)
    if not started:
        return 0
    finished = parse_time(end) if end else datetime.now()
    if not finished:
        return 0
    return max(0, int(round((finished - started).total_seconds())))


def parse_time(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None
