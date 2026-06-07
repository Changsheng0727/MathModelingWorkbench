from __future__ import annotations

import threading
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime
from math import ceil
from pathlib import Path
from typing import Any

from app.config import SETTINGS_ROOT
from app.services.auto_workflow import AUTO_WORKFLOW_TOTAL_STEPS, run_auto_workflow
from app.services.capacity_settings import load_capacity_settings, save_capacity_settings
from app.services.store import load_json, save_json


ACTIVE_JOB_STATUSES = {"queued", "running"}
TERMINAL_JOB_STATUSES = {"success", "failed", "cancelled", "requires_api_key", "completed_with_warnings"}
_LOCK = threading.RLock()
_JOBS: dict[str, dict[str, Any]] = {}
_FUTURES: dict[str, Future] = {}
_PROJECT_JOBS: dict[str, str] = {}
_LEDGER_PATH = SETTINGS_ROOT / "auto_workflow_jobs.json"
_LEDGER_LOADED = False


def resolve_worker_count() -> int:
    return int(load_capacity_settings().get("auto_workflow_workers") or 2)


_WORKER_COUNT = resolve_worker_count()
_EXECUTOR = ThreadPoolExecutor(max_workers=_WORKER_COUNT, thread_name_prefix="auto-workflow")


def configure_auto_workflow_capacity(worker_count: int) -> dict[str, Any]:
    global _WORKER_COUNT, _EXECUTOR
    settings = save_capacity_settings({"auto_workflow_workers": worker_count})
    requested = int(settings.get("auto_workflow_workers") or _WORKER_COUNT)
    with _LOCK:
        changed = requested != _WORKER_COUNT
        old_executor = _EXECUTOR if changed else None
        if changed:
            _WORKER_COUNT = requested
            _EXECUTOR = ThreadPoolExecutor(max_workers=_WORKER_COUNT, thread_name_prefix="auto-workflow")
            persist_jobs_locked()
    if old_executor:
        old_executor.shutdown(wait=False, cancel_futures=False)
    return {
        "changed": changed,
        "auto_jobs": list_auto_workflow_jobs(),
        "capacity_settings": load_capacity_settings(),
    }


def start_auto_workflow_job(project_id: str, root: Path, *, resume: bool = False) -> dict[str, Any]:
    root = root.resolve()
    meta = load_json(root / "metadata.json") if (root / "metadata.json").exists() else {}
    with _LOCK:
        load_job_ledger_locked()
        prune_finished_jobs_locked()
        active_id = _PROJECT_JOBS.get(project_id)
        active = _JOBS.get(active_id or "")
        if active and active.get("status") in ACTIVE_JOB_STATUSES:
            return public_job(active, existing=True)

        job_id = uuid.uuid4().hex
        job = {
            "id": job_id,
            "project_id": project_id,
            "project_name": meta.get("name", "") if isinstance(meta, dict) else "",
            "root": str(root),
            "resume": bool(resume),
            "status": "queued",
            "submitted_at": now_iso(),
            "started_at": "",
            "finished_at": "",
            "error": "",
            "overall_status": "",
        }
        _JOBS[job_id] = job
        _PROJECT_JOBS[project_id] = job_id
        persist_jobs_locked()
        write_job_progress(root, job, "queued")
        future = _EXECUTOR.submit(run_job, job_id)
        _FUTURES[job_id] = future
        return public_job(job)


def get_auto_workflow_job(job_id: str) -> dict[str, Any]:
    with _LOCK:
        load_job_ledger_locked()
        job = _JOBS.get(job_id)
        return public_job(job) if job else {}


def get_project_auto_workflow_job(project_id: str) -> dict[str, Any]:
    with _LOCK:
        load_job_ledger_locked()
        job_id = _PROJECT_JOBS.get(project_id)
        job = _JOBS.get(job_id or "")
        if job and job.get("status") in ACTIVE_JOB_STATUSES:
            return public_job(job)
        return {}


def list_auto_workflow_jobs(limit: int = 60) -> dict[str, Any]:
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
        capacity = _WORKER_COUNT
        throughput = build_throughput_summary(public_jobs, running_count, queued_count, capacity)
        capacity_settings = load_capacity_settings()
        return {
            "generated_at": now_iso(),
            "capacity": capacity,
            "running_count": running_count,
            "queued_count": queued_count,
            "active_count": active_count,
            "finished_count": finished_count,
            "total_tracked": len(_JOBS),
            "available_slots": max(0, capacity - running_count),
            "ledger_path": str(_LEDGER_PATH),
            "capacity_settings": capacity_settings,
            "throughput": throughput,
            "jobs": public_jobs,
        }


def cancel_queued_auto_workflow_job(project_id: str) -> dict[str, Any]:
    with _LOCK:
        load_job_ledger_locked()
        job_id = _PROJECT_JOBS.get(project_id)
        job = _JOBS.get(job_id or "")
        if not job or job.get("status") not in ACTIVE_JOB_STATUSES:
            return {"cancelled": False, "reason": "no_active_job"}
        if job.get("status") != "queued":
            return {"cancelled": False, "reason": "already_running", "job": public_job(job)}

        future = _FUTURES.get(str(job.get("id")))
        if future and not future.cancel():
            return {"cancelled": False, "reason": "already_running", "job": public_job(job)}
        job["status"] = "cancelled"
        job["finished_at"] = now_iso()
        job["error"] = "用户在后台任务开始前取消。"
        _PROJECT_JOBS.pop(project_id, None)
        public = public_job(job)
        persist_jobs_locked()

    write_job_progress(Path(str(job["root"])), job, "cancelled")
    return {"cancelled": True, "job": public}


def run_job(job_id: str) -> None:
    with _LOCK:
        job = _JOBS.get(job_id)
        if not job or job.get("status") == "cancelled":
            return
        job["status"] = "running"
        job["started_at"] = now_iso()
        public = public_job(job)
        persist_jobs_locked()

    root = Path(str(job["root"]))
    update_job_metadata(root, public)
    try:
        meta = load_json(root / "metadata.json")
        report = run_auto_workflow(root, meta, resume=bool(job.get("resume")))
        overall = str(report.get("overall_status") or "success")
        with _LOCK:
            job["status"] = overall if overall in TERMINAL_JOB_STATUSES else "success"
            job["overall_status"] = overall
            job["finished_at"] = now_iso()
            _PROJECT_JOBS.pop(str(job.get("project_id")), None)
            public = public_job(job)
            persist_jobs_locked()
        update_job_metadata(root, public)
    except ValueError as exc:
        finish_failed_job(job, "requires_api_key", str(exc))
    except Exception as exc:
        finish_failed_job(job, "failed", f"{type(exc).__name__}: {exc}")


def finish_failed_job(job: dict[str, Any], status: str, error: str) -> None:
    root = Path(str(job["root"]))
    with _LOCK:
        job["status"] = status
        job["overall_status"] = status
        job["finished_at"] = now_iso()
        job["error"] = error
        _PROJECT_JOBS.pop(str(job.get("project_id")), None)
        public = public_job(job)
        persist_jobs_locked()

    meta = load_json(root / "metadata.json") if (root / "metadata.json").exists() else {}
    meta["auto_workflow_status"] = status
    meta["auto_workflow_error"] = error
    meta["auto_workflow_job"] = public
    progress = meta.get("auto_workflow_progress", {}) if isinstance(meta.get("auto_workflow_progress"), dict) else {}
    progress.update(
        {
            "status": status,
            "updated_at": now_iso(),
            "current_step": None,
            "detail": error,
            "cancel_requested": False,
            "can_resume": status == "failed",
        }
    )
    meta["auto_workflow_progress"] = progress
    save_json(root / "artifacts" / "auto_workflow_progress.json", progress)
    save_json(root / "metadata.json", meta)


def update_job_metadata(root: Path, public: dict[str, Any]) -> None:
    meta = load_json(root / "metadata.json") if (root / "metadata.json").exists() else {}
    meta["auto_workflow_job"] = public
    save_json(root / "metadata.json", meta)


def write_job_progress(root: Path, job: dict[str, Any], status: str) -> None:
    meta = load_json(root / "metadata.json") if (root / "metadata.json").exists() else {}
    public = public_job(job)
    title = "后台任务排队中" if status == "queued" else "后台任务已取消"
    detail = "自动流程已提交到高并发任务池，稍后会开始执行。" if status == "queued" else public.get("error", "")
    progress = {
        "status": status,
        "started_at": job.get("submitted_at"),
        "updated_at": now_iso(),
        "current_step": None
        if status == "cancelled"
        else {
            "id": "auto_workflow_queue",
            "title": title,
            "status": "running",
            "detail": detail,
            "required": False,
        },
        "steps": [],
        "completed_steps": 0,
        "total_steps": AUTO_WORKFLOW_TOTAL_STEPS,
        "percent": 2 if status == "queued" else 0,
        "cancel_requested": status == "cancelled",
        "can_resume": status == "cancelled",
        "auto_job": public,
    }
    meta["auto_workflow_status"] = status
    meta["auto_workflow_job"] = public
    meta["auto_workflow_progress"] = progress
    save_json(root / "artifacts" / "auto_workflow_progress.json", progress)
    save_json(root / "metadata.json", meta)


def public_job(job: dict[str, Any] | None, *, existing: bool = False) -> dict[str, Any]:
    if not isinstance(job, dict):
        return {}
    status = str(job.get("status") or "")
    return {
        "id": job.get("id", ""),
        "project_id": job.get("project_id", ""),
        "project_name": job.get("project_name", ""),
        "resume": bool(job.get("resume")),
        "status": status,
        "submitted_at": job.get("submitted_at", ""),
        "started_at": job.get("started_at", ""),
        "finished_at": job.get("finished_at", ""),
        "error": job.get("error", ""),
        "overall_status": job.get("overall_status", ""),
        "existing": existing,
        "max_workers": _WORKER_COUNT,
        "wait_seconds": elapsed_seconds(job.get("submitted_at"), job.get("started_at") if job.get("started_at") else None)
        if status != "queued"
        else elapsed_seconds(job.get("submitted_at"), None),
        "run_seconds": elapsed_seconds(job.get("started_at"), job.get("finished_at") if job.get("finished_at") else None)
        if job.get("started_at")
        else 0,
    }


def build_throughput_summary(
    jobs: list[dict[str, Any]],
    running_count: int,
    queued_count: int,
    capacity: int,
) -> dict[str, Any]:
    capacity = max(1, int(capacity or 1))
    running = [job for job in jobs if job.get("status") == "running"]
    queued = sorted(
        (job for job in jobs if job.get("status") == "queued"),
        key=lambda item: str(item.get("submitted_at") or ""),
    )
    finished = [job for job in jobs if job.get("status") not in ACTIVE_JOB_STATUSES]
    recent_finished = [job for job in finished if int(job.get("run_seconds") or 0) > 0][:30]
    avg_run_seconds = average_seconds(job.get("run_seconds") for job in recent_finished) or 900
    avg_wait_seconds = average_seconds(job.get("wait_seconds") for job in finished[:30])
    utilization = round(min(1.0, running_count / capacity), 2)
    active_pressure = round((running_count + queued_count) / capacity, 2)
    eta_next_start, eta_queue_clear = estimate_queue_timing(running, queued, capacity, avg_run_seconds)
    recommended_workers = recommend_worker_count(capacity, running_count, queued_count, avg_wait_seconds)
    recent_success_rate = success_rate(finished[:30])
    status, label = throughput_status(running_count, queued_count, capacity, active_pressure)
    scaling_action = scaling_hint(capacity, recommended_workers, queued_count, active_pressure)
    summary = throughput_summary(label, running_count, queued_count, capacity, eta_next_start, eta_queue_clear)
    signals = throughput_signals(
        utilization,
        active_pressure,
        avg_wait_seconds,
        avg_run_seconds,
        recent_success_rate,
        recommended_workers,
        capacity,
    )
    return {
        "status": status,
        "label": label,
        "summary": summary,
        "capacity": capacity,
        "max_configurable_workers": 8,
        "worker_env_var": "MODELARK_AUTO_WORKFLOW_WORKERS",
        "runtime_configurable": True,
        "running_count": running_count,
        "queued_count": queued_count,
        "utilization": utilization,
        "active_pressure": active_pressure,
        "available_slots": max(0, capacity - running_count),
        "recommended_workers": recommended_workers,
        "scaling_action": scaling_action,
        "avg_wait_seconds": avg_wait_seconds,
        "avg_run_seconds": avg_run_seconds,
        "eta_next_start_seconds": eta_next_start,
        "eta_queue_clear_seconds": eta_queue_clear,
        "recent_success_rate": recent_success_rate,
        "recent_finished_count": len(finished[:30]),
        "signals": signals,
    }


def estimate_queue_timing(
    running: list[dict[str, Any]],
    queued: list[dict[str, Any]],
    capacity: int,
    avg_run_seconds: int,
) -> tuple[int, int]:
    if not queued:
        return 0, 0
    slots = [max(30, int(avg_run_seconds) - int(job.get("run_seconds") or 0)) for job in running[:capacity]]
    while len(slots) < capacity:
        slots.append(0)
    next_start = 0
    queue_clear = 0
    for index, _job in enumerate(queued):
        slot_index = min(range(len(slots)), key=lambda idx: slots[idx])
        start_after = int(slots[slot_index])
        if index == 0:
            next_start = start_after
        finish_after = start_after + int(avg_run_seconds)
        slots[slot_index] = finish_after
        queue_clear = max(queue_clear, finish_after)
    return next_start, queue_clear


def recommend_worker_count(capacity: int, running_count: int, queued_count: int, avg_wait_seconds: int) -> int:
    if queued_count <= 0:
        return capacity
    pressure_target = max(capacity + 1, ceil((running_count + queued_count) / 0.85))
    if avg_wait_seconds > 600:
        pressure_target = max(pressure_target, capacity + 2)
    return max(capacity, min(8, pressure_target))


def throughput_status(
    running_count: int,
    queued_count: int,
    capacity: int,
    active_pressure: float,
) -> tuple[str, str]:
    if queued_count > capacity or active_pressure >= 1.75:
        return "saturated", "队列拥堵"
    if queued_count or running_count >= capacity:
        return "busy", "高负载"
    if running_count:
        return "healthy", "稳定运行"
    return "idle", "待命"


def scaling_hint(capacity: int, recommended_workers: int, queued_count: int, active_pressure: float) -> str:
    if recommended_workers > capacity:
        return f"建议在容量设置中将自动流程并发槽调整到 {recommended_workers}。"
        return f"建议将 MODELARK_AUTO_WORKFLOW_WORKERS 调整到 {recommended_workers}，重启服务后生效。"
    if queued_count:
        return "当前并发槽可支撑队列，继续观察平均等待时间。"
    if active_pressure == 0:
        return "当前无后台任务，容量处于待命状态。"
    return "当前容量匹配负载。"


def throughput_summary(
    label: str,
    running_count: int,
    queued_count: int,
    capacity: int,
    eta_next_start: int,
    eta_queue_clear: int,
) -> str:
    parts = [f"{label}：{running_count}/{capacity} 槽运行，{queued_count} 个排队"]
    if queued_count:
        parts.append(f"下一任务预计 {human_duration(eta_next_start)} 后开始")
        parts.append(f"队列预计 {human_duration(eta_queue_clear)} 后清空")
    return "；".join(parts)


def throughput_signals(
    utilization: float,
    active_pressure: float,
    avg_wait_seconds: int,
    avg_run_seconds: int,
    recent_success_rate: int | None,
    recommended_workers: int,
    capacity: int,
) -> list[str]:
    signals = [
        f"槽位利用率 {round(utilization * 100)}%",
        f"活跃压力 {active_pressure}x",
        f"平均运行 {human_duration(avg_run_seconds)}",
    ]
    if avg_wait_seconds:
        signals.append(f"平均等待 {human_duration(avg_wait_seconds)}")
    if recent_success_rate is not None:
        signals.append(f"近期成功率 {recent_success_rate}%")
    if recommended_workers > capacity:
        signals.append(f"推荐并发槽 {recommended_workers}")
    return signals[:6]


def average_seconds(values: Any) -> int:
    rows = [int(value or 0) for value in values if int(value or 0) > 0]
    if not rows:
        return 0
    return int(round(sum(rows) / len(rows)))


def success_rate(jobs: list[dict[str, Any]]) -> int | None:
    terminal = [job for job in jobs if job.get("status") not in ACTIVE_JOB_STATUSES]
    if not terminal:
        return None
    success_count = sum(1 for job in terminal if job.get("status") == "success")
    warning_count = sum(1 for job in terminal if job.get("status") == "completed_with_warnings")
    weighted_success = success_count + warning_count * 0.5
    return int(round(weighted_success / len(terminal) * 100))


def human_duration(seconds: int) -> str:
    seconds = max(0, int(seconds or 0))
    if seconds < 60:
        return f"{seconds}s"
    minutes, rest = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m {rest}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes}m"


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
            job["status"] = "interrupted"
            job["overall_status"] = "interrupted"
            job["finished_at"] = recovered_at
            job["error"] = "服务重启后恢复任务台账：该后台任务已不在当前进程中运行，可重新提交或继续生成。"
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
        "project_id": str(row.get("project_id") or ""),
        "project_name": str(row.get("project_name") or ""),
        "root": str(row.get("root") or ""),
        "resume": bool(row.get("resume")),
        "status": str(row.get("status") or ""),
        "submitted_at": str(row.get("submitted_at") or ""),
        "started_at": str(row.get("started_at") or ""),
        "finished_at": str(row.get("finished_at") or ""),
        "error": str(row.get("error") or ""),
        "overall_status": str(row.get("overall_status") or ""),
    }


def serialize_job_for_ledger(job: dict[str, Any]) -> dict[str, Any]:
    return normalize_ledger_job(job)


def prune_finished_jobs_locked(limit: int = 160) -> None:
    if len(_JOBS) <= limit:
        return
    finished = [
        job
        for job in _JOBS.values()
        if job.get("status") not in ACTIVE_JOB_STATUSES
    ]
    finished.sort(key=lambda item: str(item.get("finished_at") or item.get("submitted_at") or ""))
    for job in finished[: max(0, len(_JOBS) - limit)]:
        job_id = str(job.get("id") or "")
        if job_id:
            _JOBS.pop(job_id, None)
            _FUTURES.pop(job_id, None)
