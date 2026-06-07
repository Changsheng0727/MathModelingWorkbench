from __future__ import annotations

import os
import re
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any

from app.services.parsers import DATA_EXTENSIONS, DOC_EXTENSIONS, compact_text, extract_document_text, parse_data_schema
from app.services.store import load_json, save_json


ATTACHMENT_PROFILE_RELATIVE = "artifacts/attachment_profile.json"
ATTACHMENT_PROFILE_MD_RELATIVE = "artifacts/attachment_profile.md"


def build_attachment_profile(
    root: Path,
    analysis: dict[str, Any] | None = None,
    *,
    force: bool = False,
    max_workers: int | None = None,
) -> dict[str, str]:
    """Build or reuse a concurrent profile of raw attachments.

    The profile is intentionally backend-owned rather than LLM-generated. It
    gives later planning/code prompts a fast, cached view of file schemas and
    document text signals while leaving actual mathematical computation to the
    project solver.
    """
    raw_dir = root / "raw"
    files = [path for path in sorted(raw_dir.rglob("*")) if path.is_file()] if raw_dir.exists() else []
    fingerprint = raw_fingerprint(raw_dir, files)
    profile_path = root / ATTACHMENT_PROFILE_RELATIVE
    if not force and profile_path.exists():
        try:
            existing = load_json(profile_path)
        except Exception:
            existing = {}
        if isinstance(existing, dict) and existing.get("source_fingerprint") == fingerprint:
            ensure_attachment_profile_markdown(root, existing)
            return {
                "attachment_profile": ATTACHMENT_PROFILE_MD_RELATIVE,
                "attachment_profile_json": ATTACHMENT_PROFILE_RELATIVE,
            }

    started = time.perf_counter()
    worker_count = resolve_worker_count(len(files), max_workers)
    records: list[dict[str, Any]] = []
    if files:
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            futures = {executor.submit(profile_one_file, raw_dir, path): path for path in files}
            for future in as_completed(futures):
                try:
                    records.append(future.result())
                except Exception as exc:
                    path = futures[future]
                    records.append(
                        {
                            "path": safe_relative(raw_dir, path),
                            "suffix": path.suffix.lower(),
                            "kind": "unknown",
                            "size": safe_size(path),
                            "status": "error",
                            "error": f"{type(exc).__name__}: {exc}",
                        }
                    )

    records.sort(key=lambda item: str(item.get("path") or ""))
    payload = {
        "stage": "attachment_profile",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "success": True,
        "file_count": len(files),
        "profiled_count": len(records),
        "worker_count": worker_count,
        "duration_seconds": round(time.perf_counter() - started, 3),
        "source_fingerprint": fingerprint,
        "summary": summarize_records(records, analysis or {}),
        "files": records,
    }
    save_json(profile_path, payload)
    ensure_attachment_profile_markdown(root, payload)
    return {
        "attachment_profile": ATTACHMENT_PROFILE_MD_RELATIVE,
        "attachment_profile_json": ATTACHMENT_PROFILE_RELATIVE,
    }


def load_or_build_attachment_profile(root: Path, analysis: dict[str, Any] | None = None) -> dict[str, Any]:
    build_attachment_profile(root, analysis)
    path = root / ATTACHMENT_PROFILE_RELATIVE
    if not path.exists():
        return {}
    try:
        payload = load_json(path)
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def compact_attachment_profile_for_prompt(root: Path, analysis: dict[str, Any] | None = None, max_files: int = 50) -> dict[str, Any]:
    profile = load_or_build_attachment_profile(root, analysis)
    if not profile:
        return {}
    files = []
    for item in (profile.get("files") or [])[:max_files]:
        if not isinstance(item, dict):
            continue
        compact: dict[str, Any] = {
            "path": item.get("path"),
            "kind": item.get("kind"),
            "suffix": item.get("suffix"),
            "size": item.get("size"),
            "status": item.get("status"),
        }
        if item.get("schema"):
            compact["schema"] = compact_schema(item.get("schema"))
        if item.get("text_preview"):
            compact["text_preview"] = item.get("text_preview")
        if item.get("compact_text_preview"):
            compact["compact_text_preview"] = item.get("compact_text_preview")
        if item.get("error"):
            compact["error"] = item.get("error")
        files.append({key: value for key, value in compact.items() if value not in (None, "", [], {})})
    return {
        "generated_at": profile.get("generated_at"),
        "file_count": profile.get("file_count"),
        "profiled_count": profile.get("profiled_count"),
        "worker_count": profile.get("worker_count"),
        "duration_seconds": profile.get("duration_seconds"),
        "summary": profile.get("summary", {}),
        "files": files,
    }


def profile_one_file(raw_dir: Path, path: Path) -> dict[str, Any]:
    started = time.perf_counter()
    suffix = path.suffix.lower()
    record: dict[str, Any] = {
        "path": safe_relative(raw_dir, path),
        "name": path.name,
        "suffix": suffix,
        "size": safe_size(path),
        "kind": file_kind(suffix),
        "status": "ok",
    }
    try:
        if suffix in DATA_EXTENSIONS:
            schema = parse_data_schema(path)
            record["schema"] = schema
            record["column_signals"] = column_signals(schema)
        elif suffix in DOC_EXTENSIONS:
            text = extract_document_text(path)
            record["char_count"] = len(text)
            record["text_preview"] = compact_text(text, 1200)
            record["compact_text_preview"] = compact_no_space(text, 900)
            record["keywords"] = text_keywords(text)
        elif suffix in {".json", ".geojson"} and record["size"] <= 4_000_000:
            text = read_small_text(path, 1600)
            record["text_preview"] = text
            record["keywords"] = text_keywords(text)
        elif suffix in {".txt", ".md"} and record["size"] <= 4_000_000:
            text = read_small_text(path, 2400)
            record["text_preview"] = compact_text(text, 1200)
            record["compact_text_preview"] = compact_no_space(text, 900)
            record["keywords"] = text_keywords(text)
    except Exception as exc:
        record["status"] = "error"
        record["error"] = f"{type(exc).__name__}: {exc}"
    record["duration_seconds"] = round(time.perf_counter() - started, 3)
    return record


def raw_fingerprint(raw_dir: Path, files: list[Path]) -> dict[str, Any]:
    entries = []
    for path in files:
        try:
            stat = path.stat()
        except OSError:
            continue
        entries.append(
            {
                "path": safe_relative(raw_dir, path),
                "size": stat.st_size,
                "mtime_ns": stat.st_mtime_ns,
            }
        )
    return {"raw_dir": str(raw_dir.resolve()), "files": entries}


def resolve_worker_count(file_count: int, requested: int | None = None) -> int:
    if file_count <= 0:
        return 0
    cpu_count = os.cpu_count() or 4
    default = min(8, max(2, cpu_count))
    if requested is not None:
        default = max(1, int(requested))
    return max(1, min(file_count, default))


def summarize_records(records: list[dict[str, Any]], analysis: dict[str, Any]) -> dict[str, Any]:
    kind_counts = Counter(str(item.get("kind") or "unknown") for item in records)
    suffix_counts = Counter(str(item.get("suffix") or "") for item in records)
    status_counts = Counter(str(item.get("status") or "unknown") for item in records)
    columns = Counter()
    keywords = Counter()
    data_files = []
    document_files = []
    for item in records:
        if item.get("kind") == "data":
            data_files.append(
                {
                    "path": item.get("path"),
                    "schema_summary": schema_summary(item.get("schema")),
                    "column_signals": item.get("column_signals", [])[:24],
                }
            )
            for column in item.get("column_signals", []) or []:
                columns[str(column)] += 1
        if item.get("kind") == "document":
            document_files.append(
                {
                    "path": item.get("path"),
                    "char_count": item.get("char_count"),
                    "keywords": item.get("keywords", [])[:16],
                }
            )
            for keyword in item.get("keywords", []) or []:
                keywords[str(keyword)] += 1
    selected = analysis.get("selected_problem") or analysis.get("recommended_problem") or {}
    return {
        "kind_counts": dict(kind_counts),
        "suffix_counts": dict(suffix_counts),
        "status_counts": dict(status_counts),
        "top_columns": [item for item, _count in columns.most_common(40)],
        "top_keywords": [item for item, _count in keywords.most_common(40)],
        "selected_problem": {
            "id": selected.get("id", ""),
            "title": selected.get("title", ""),
        },
        "data_files": data_files[:30],
        "document_files": document_files[:30],
    }


def ensure_attachment_profile_markdown(root: Path, payload: dict[str, Any]) -> None:
    path = root / ATTACHMENT_PROFILE_MD_RELATIVE
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# 并发附件画像",
        "",
        f"- 生成时间：{payload.get('generated_at', '-')}",
        f"- 附件数量：{payload.get('file_count', 0)}",
        f"- 并发线程：{payload.get('worker_count', 0)}",
        f"- 耗时：{payload.get('duration_seconds', 0)} 秒",
        "",
        "## 汇总",
    ]
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    lines.append(f"- 文件类型：{summary.get('kind_counts', {})}")
    lines.append(f"- 解析状态：{summary.get('status_counts', {})}")
    top_columns = summary.get("top_columns", [])[:20] if isinstance(summary.get("top_columns"), list) else []
    top_keywords = summary.get("top_keywords", [])[:20] if isinstance(summary.get("top_keywords"), list) else []
    if top_columns:
        lines.append("- 高频字段：" + "、".join(str(item) for item in top_columns))
    if top_keywords:
        lines.append("- 文档关键词：" + "、".join(str(item) for item in top_keywords))
    lines.extend(["", "## 文件明细", "", "| 文件 | 类型 | 状态 | 摘要 |", "|---|---|---|---|"])
    for item in payload.get("files", []) or []:
        if not isinstance(item, dict):
            continue
        detail = item_detail_summary(item).replace("|", "/")
        lines.append(
            f"| {item.get('path', '-')} | {item.get('kind', '-')} | {item.get('status', '-')} | {detail} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def item_detail_summary(item: dict[str, Any]) -> str:
    if item.get("error"):
        return str(item.get("error"))[:220]
    if item.get("schema"):
        return schema_summary(item.get("schema"))
    if item.get("text_preview"):
        return str(item.get("text_preview", ""))[:220]
    return f"{round((int(item.get('size') or 0)) / 1024, 1)} KB"


def compact_schema(schema: Any) -> Any:
    if not isinstance(schema, dict):
        return schema
    if schema.get("type") == "csv":
        return {
            "type": "csv",
            "encoding": schema.get("encoding"),
            "rows": schema.get("rows"),
            "cols": schema.get("cols"),
            "columns": (schema.get("columns") or [])[:80],
            "sample": (schema.get("sample") or [])[:2],
            "error": schema.get("error", ""),
        }
    if schema.get("type") == "excel":
        sheets = []
        for sheet in schema.get("sheets", [])[:20]:
            if isinstance(sheet, dict):
                sheets.append(
                    {
                        "name": sheet.get("name"),
                        "rows": sheet.get("rows"),
                        "cols": sheet.get("cols"),
                        "columns": (sheet.get("columns") or [])[:80],
                        "sample": (sheet.get("sample") or [])[:2],
                    }
                )
        return {"type": "excel", "sheets": sheets, "error": schema.get("error", "")}
    return schema


def schema_summary(schema: Any) -> str:
    if not isinstance(schema, dict):
        return "未识别结构"
    if schema.get("error"):
        return str(schema.get("error"))[:220]
    if schema.get("type") == "csv":
        columns = schema.get("columns") or []
        return f"CSV：{schema.get('rows', '-')} 行，{schema.get('cols', '-')} 列；字段 {', '.join(str(c) for c in columns[:8])}"
    if schema.get("type") == "excel":
        sheets = schema.get("sheets") or []
        names = [str(sheet.get("name")) for sheet in sheets[:8] if isinstance(sheet, dict)]
        return f"Excel：{len(sheets)} 个工作表；{', '.join(names)}"
    return str(schema.get("type") or "已解析")


def column_signals(schema: Any) -> list[str]:
    signals: list[str] = []
    if not isinstance(schema, dict):
        return signals
    if schema.get("type") == "csv":
        signals.extend(str(column) for column in schema.get("columns", []) if str(column).strip())
    elif schema.get("type") == "excel":
        for sheet in schema.get("sheets", []) or []:
            if not isinstance(sheet, dict):
                continue
            signals.extend(str(column) for column in sheet.get("columns", []) if str(column).strip())
    clean = []
    seen = set()
    for signal in signals:
        value = normalize_signal(signal)
        if not value or value in seen:
            continue
        seen.add(value)
        clean.append(value)
    return clean[:120]


def text_keywords(text: str, limit: int = 60) -> list[str]:
    words = re.findall(r"[\u4e00-\u9fff]{2,12}|[A-Za-z][A-Za-z0-9_]{2,30}", text or "")
    stop = {"the", "and", "for", "with", "this", "that", "from", "data", "file"}
    counter = Counter()
    for word in words:
        value = normalize_signal(word)
        if len(value) < 2 or value.lower() in stop:
            continue
        counter[value] += 1
    return [word for word, _count in counter.most_common(limit)]


def normalize_signal(value: Any) -> str:
    text = str(value or "").strip()
    text = re.sub(r"\s+", "", text)
    return text[:80]


def compact_no_space(text: str, limit: int) -> str:
    text = re.sub(r"\s+", "", text or "")
    return text[:limit]


def read_small_text(path: Path, limit: int) -> str:
    for encoding in ["utf-8-sig", "utf-8", "gbk"]:
        try:
            return path.read_text(encoding=encoding, errors="strict")[:limit]
        except UnicodeError:
            continue
    return path.read_text(encoding="utf-8", errors="replace")[:limit]


def file_kind(suffix: str) -> str:
    if suffix in DATA_EXTENSIONS:
        return "data"
    if suffix in DOC_EXTENSIONS:
        return "document"
    return "other"


def safe_relative(raw_dir: Path, path: Path) -> str:
    try:
        return path.relative_to(raw_dir).as_posix()
    except ValueError:
        return path.name


def safe_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0
