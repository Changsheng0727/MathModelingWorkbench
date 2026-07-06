from __future__ import annotations

import re
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from app.config import DATA_ROOT
from app.services.store import save_json


ANALYSIS_PROGRESS_RELATIVE = "artifacts/analysis_progress.json"
GLOBAL_ANALYSIS_PROGRESS_ROOT = DATA_ROOT / "client" / "analysis_progress"
FILE_ANALYSIS_STEPS = 8
FOLDER_ANALYSIS_STEPS = 7
TOTAL_ANALYSIS_STEPS = FILE_ANALYSIS_STEPS


class AnalysisProgress:
    def __init__(self, root: Path, meta: dict[str, Any], progress_id: str | None = None, total_steps: int = TOTAL_ANALYSIS_STEPS) -> None:
        self.root = root
        self.meta = meta
        self.progress_id = safe_progress_id(progress_id)
        self.total_steps = total_steps
        self.started_at = datetime.now().isoformat(timespec="seconds")
        self.steps: list[dict[str, Any]] = []
        self.current_step: dict[str, Any] | None = None
        self.status = "running"
        self.last_write = 0.0
        self.write(force=True)

    def start_step(self, step_id: str, title: str, detail: str = "") -> None:
        self.current_step = {
            "id": step_id,
            "title": title,
            "detail": detail,
            "status": "running",
            "started_at": datetime.now().isoformat(timespec="seconds"),
            "_started_monotonic": time.monotonic(),
        }
        self.status = "running"
        self.write(force=True)

    def update(self, detail: str, force: bool = False, **extra: Any) -> None:
        if not self.current_step:
            return
        self.current_step["detail"] = detail
        self.current_step.update({key: value for key, value in extra.items() if value is not None})
        self.write(force=force)

    def finish_step(self, status: str = "success", detail: str = "", **extra: Any) -> None:
        if not self.current_step:
            return
        item = dict(self.current_step)
        item.pop("_started_monotonic", None)
        item["status"] = status
        if detail:
            item["detail"] = detail
        item.update({key: value for key, value in extra.items() if value is not None})
        started = self.current_step.get("_started_monotonic")
        if started:
            item["duration_seconds"] = round(time.monotonic() - float(started), 2)
        item["finished_at"] = datetime.now().isoformat(timespec="seconds")
        self.steps.append(item)
        self.current_step = None
        if status == "failed":
            self.status = "failed"
        self.write(force=True)

    def finish(self, status: str = "success", detail: str = "") -> None:
        if self.current_step:
            self.finish_step(status="success" if status == "success" else status, detail=detail)
        if status == "success" and any(step.get("status") == "warning" for step in self.steps):
            status = "completed_with_warnings"
        self.status = status
        self.write(force=True, final_detail=detail)

    def fail(self, detail: str, error_log: str = "") -> None:
        if self.current_step:
            self.finish_step(status="failed", detail=detail, error_log=error_log)
        self.status = "failed"
        self.write(force=True, final_detail=detail)

    def write(self, force: bool = False, final_detail: str = "") -> None:
        now = time.monotonic()
        if not force and now - self.last_write < 0.35:
            return
        self.last_write = now
        progress = self.payload(final_detail=final_detail)
        self.meta["analysis_progress_id"] = self.progress_id
        self.meta["analysis_progress"] = progress
        save_json(self.root / ANALYSIS_PROGRESS_RELATIVE, progress)
        save_json(global_progress_path(self.progress_id), progress)
        save_json(self.root / "metadata.json", self.meta)

    def payload(self, final_detail: str = "") -> dict[str, Any]:
        completed = len(self.steps)
        current_weight = 0.4 if self.current_step and self.status == "running" else 0
        percent = 100 if self.status in {"success", "failed", "completed_with_warnings"} else round((completed + current_weight) / self.total_steps * 100)
        payload = {
            "id": self.progress_id,
            "project_id": self.meta.get("id", ""),
            "status": self.status,
            "started_at": self.started_at,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "current_step": compact_step(self.current_step),
            "steps": [compact_step(step) for step in self.steps],
            "completed_steps": completed,
            "total_steps": self.total_steps,
            "percent": max(0, min(100, percent)),
        }
        if final_detail:
            payload["detail"] = final_detail
        return payload


def safe_progress_id(value: str | None) -> str:
    text = str(value or "").strip()
    if re.fullmatch(r"[A-Za-z0-9_-]{8,80}", text):
        return text
    return uuid.uuid4().hex


def global_progress_path(progress_id: str) -> Path:
    return GLOBAL_ANALYSIS_PROGRESS_ROOT / f"{safe_progress_id(progress_id)}.json"


def load_analysis_progress(progress_id: str) -> dict[str, Any]:
    path = global_progress_path(progress_id)
    if not path.exists():
        return {}
    try:
        import json

        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        return {
            "id": safe_progress_id(progress_id),
            "status": "warning",
            "progress_error": error,
            "detail": "赛题分析进度文件暂时读取失败，稍后会自动刷新。",
        }


def compact_step(step: dict[str, Any] | None) -> dict[str, Any] | None:
    if not step:
        return None
    return {
        "id": step.get("id"),
        "title": step.get("title"),
        "status": step.get("status"),
        "detail": step.get("detail", ""),
        "started_at": step.get("started_at"),
        "finished_at": step.get("finished_at"),
        "duration_seconds": step.get("duration_seconds"),
        "error_log": step.get("error_log", ""),
    }
