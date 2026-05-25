from __future__ import annotations

import json
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from app.config import TEMPLATES_ROOT
from app.services.parsers import extract_document_text


DEFAULT_TEMPLATE_ID = "builtin-default"
INDEX_PATH = TEMPLATES_ROOT / "index.json"
MAX_TEMPLATE_BYTES = 10 * 1024 * 1024
LATEX_TEMPLATE_EXTENSIONS = {".tex"}
RULE_DOCUMENT_EXTENSIONS = {".docx", ".pdf", ".txt", ".md"}
SUPPORTED_TEMPLATE_EXTENSIONS = LATEX_TEMPLATE_EXTENSIONS | RULE_DOCUMENT_EXTENSIONS
EXTRACTED_TEXT_SUFFIX = ".extracted.txt"

BODY_PLACEHOLDER = "__BODY__"
GRANULAR_PLACEHOLDERS = {
    "__RESTATEMENT__",
    "__PROBLEM_ANALYSIS__",
    "__SOLVING__",
    "__VALIDATION__",
    "__APPENDIX__",
}
BOUNDARY_PLACEHOLDERS = {"__BODY_START__", "__APPENDIX_START__"}


def list_templates() -> list[dict[str, Any]]:
    templates = [
        {
            "id": DEFAULT_TEMPLATE_ID,
            "name": "内置 LaTeX 模板",
            "filename": "",
            "suffix": "",
            "mode": "builtin",
            "kind": "latex",
            "is_builtin": True,
            "created_at": "",
            "placeholders": [],
            "rule_summary": "",
            "extracted_chars": 0,
        }
    ]
    templates.extend(_normalize_record(item) for item in _load_index())
    return templates


def get_template(template_id: str | None) -> dict[str, Any] | None:
    if not template_id or template_id == DEFAULT_TEMPLATE_ID:
        return None
    for item in (_normalize_record(item) for item in _load_index()):
        if item.get("id") == template_id:
            path = _record_path(item)
            if not path or not path.exists():
                raise FileNotFoundError(f"模板文件不存在：{template_id}")
            text = _read_record_text(item, path)
            return {**item, "path": str(path), "text": text}
    raise FileNotFoundError(f"模板不存在：{template_id}")


def create_template(name: str | None, filename: str, content: bytes) -> dict[str, Any]:
    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED_TEMPLATE_EXTENSIONS:
        raise ValueError("当前版本支持上传 .tex 模板，或 .docx/.pdf/.txt/.md 格式说明文档。")
    if not content:
        raise ValueError("模板文件为空。")
    if len(content) > MAX_TEMPLATE_BYTES:
        raise ValueError("模板文件过大，请控制在 10 MB 以内。")

    template_id = f"{_slugify(name or Path(filename).stem)}-{uuid.uuid4().hex[:8]}"
    path = _template_path(template_id, suffix)
    path.parent.mkdir(parents=True, exist_ok=True)

    if suffix in LATEX_TEMPLATE_EXTENSIONS:
        text = _decode_template(content)
        validation = validate_template_text(text)
        path.write_text(text, encoding="utf-8")
        mode = validation["mode"]
        placeholders = validation["placeholders"]
        rule_summary = ""
        extracted_chars = len(text)
        template_kind = "latex"
    else:
        path.write_bytes(content)
        text = extract_document_text(path)
        (_extracted_text_path(template_id)).write_text(text, encoding="utf-8")
        mode = "rules"
        placeholders = []
        rule_items = extract_rule_items(text)
        rule_summary = summarize_rule_text(text, rule_items)
        extracted_chars = len(text)
        template_kind = "format_rules"
    if suffix in LATEX_TEMPLATE_EXTENSIONS:
        rule_items = []

    record = {
        "id": template_id,
        "name": (name or Path(filename).stem).strip()[:80] or "未命名模板",
        "filename": filename,
        "suffix": suffix,
        "mode": mode,
        "kind": template_kind,
        "is_builtin": False,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "placeholders": placeholders,
        "rule_items": rule_items,
        "rule_summary": rule_summary,
        "extracted_chars": extracted_chars,
    }
    index = [item for item in _load_index() if item.get("id") != template_id]
    index.append(record)
    _save_index(index)
    return record


def delete_template(template_id: str) -> dict[str, Any]:
    if template_id == DEFAULT_TEMPLATE_ID:
        raise ValueError("内置模板不能删除。")
    index = _load_index()
    kept = [item for item in index if item.get("id") != template_id]
    if len(kept) == len(index):
        raise FileNotFoundError(f"模板不存在：{template_id}")
    for path in TEMPLATES_ROOT.glob(f"{template_id}.*"):
        if path.is_file():
            path.unlink()
    _save_index(kept)
    return {"deleted": template_id}


def validate_template_id(template_id: str | None) -> str:
    if not template_id:
        return DEFAULT_TEMPLATE_ID
    if template_id == DEFAULT_TEMPLATE_ID:
        return DEFAULT_TEMPLATE_ID
    get_template(template_id)
    return template_id


def validate_template_text(text: str) -> dict[str, Any]:
    placeholders = sorted(set(re.findall(r"__[A-Z0-9_]+__", text)))
    if BODY_PLACEHOLDER in placeholders:
        return {"mode": "body", "placeholders": placeholders}
    missing_granular = sorted(GRANULAR_PLACEHOLDERS - set(placeholders))
    missing_boundaries = sorted(BOUNDARY_PLACEHOLDERS - set(placeholders))
    if not missing_granular and not missing_boundaries:
        return {"mode": "granular", "placeholders": placeholders}
    required = "__BODY__；或同时包含 __BODY_START__、__APPENDIX_START__、__RESTATEMENT__、__PROBLEM_ANALYSIS__、__SOLVING__、__VALIDATION__、__APPENDIX__"
    raise ValueError(f"模板缺少可回填占位符。请至少提供 {required}。")


def summarize_rule_text(text: str, rule_items: list[dict[str, str]] | None = None) -> str:
    compact = " ".join(str(text).split())
    if not compact:
        return "未能从文档中提取到可读文字，请人工核对原始模板。"
    rule_items = rule_items if rule_items is not None else extract_rule_items(text)
    if rule_items:
        structured = "；".join(f"{item['label']}：{item['value']}" for item in rule_items)
        return structured[:1200]
    keywords = [
        "摘要",
        "目录",
        "正文",
        "页边距",
        "页码",
        "字体",
        "字号",
        "行距",
        "标题",
        "参考文献",
        "附录",
        "匿名",
        "承诺书",
        "A4",
        "Word",
        "PDF",
    ]
    snippets = []
    for keyword in keywords:
        index = compact.find(keyword)
        if index >= 0:
            start = max(0, index - 35)
            end = min(len(compact), index + 90)
            snippets.append(compact[start:end])
    if not snippets:
        snippets = [compact[:500]]
    summary = "；".join(dict.fromkeys(snippets))
    return summary[:1200]


def extract_rule_items(text: str) -> list[dict[str, str]]:
    compact = " ".join(str(text).split())
    if not compact:
        return []
    groups = [
        ("页面与页边距", ["A4", "页面", "纸张", "页边距", "边距", "版心"]),
        ("字体字号", ["字体", "字号", "宋体", "黑体", "Times New Roman", "小四", "五号"]),
        ("行距与段落", ["行距", "段前", "段后", "首行缩进", "倍行距"]),
        ("标题层级", ["标题", "一级标题", "二级标题", "三级标题", "章标题"]),
        ("摘要关键词", ["摘要", "关键词", "关键字"]),
        ("正文页数", ["正文", "页数", "不少于", "不超过", "篇幅"]),
        ("图表公式", ["图", "表", "公式", "编号", "图题", "表题"]),
        ("参考文献", ["参考文献", "GB/T", "7714", "引用"]),
        ("附录", ["附录", "程序", "代码", "数据"]),
        ("匿名与提交", ["匿名", "队号", "学校", "姓名", "提交", "命名"]),
        ("承诺书", ["承诺书", "诚信", "签字"]),
    ]
    items: list[dict[str, str]] = []
    for label, keywords in groups:
        snippets = collect_rule_snippets(compact, keywords)
        if snippets:
            items.append({"label": label, "value": "；".join(snippets)[:260]})
    return items[:12]


def collect_rule_snippets(compact: str, keywords: list[str]) -> list[str]:
    snippets = []
    seen = set()
    for keyword in keywords:
        start_at = 0
        for _ in range(2):
            index = compact.find(keyword, start_at)
            if index < 0:
                break
            start = max(0, index - 28)
            end = min(len(compact), index + 88)
            snippet = compact[start:end].strip(" ，。；;")
            start_at = index + len(keyword)
            if snippet and snippet not in seen:
                snippets.append(snippet)
                seen.add(snippet)
            if len(snippets) >= 3:
                return snippets
    return snippets


def _load_index() -> list[dict[str, Any]]:
    if not INDEX_PATH.exists():
        return []
    try:
        payload = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    if not isinstance(payload, list):
        return []
    return [item for item in payload if isinstance(item, dict)]


def _normalize_record(item: dict[str, Any]) -> dict[str, Any]:
    record = {**item}
    mode = record.get("mode") or "body"
    record["mode"] = mode
    record.setdefault("kind", "format_rules" if mode == "rules" else "latex")
    record.setdefault("suffix", Path(str(record.get("filename", ""))).suffix.lower())
    record.setdefault("is_builtin", False)
    record.setdefault("placeholders", [])
    record.setdefault("rule_items", [])
    record.setdefault("rule_summary", "")
    record.setdefault("extracted_chars", 0)
    return record


def _save_index(index: list[dict[str, Any]]) -> None:
    INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    INDEX_PATH.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")


def _template_path(template_id: str, suffix: str = ".tex") -> Path:
    return TEMPLATES_ROOT / f"{template_id}{suffix}"


def _extracted_text_path(template_id: str) -> Path:
    return TEMPLATES_ROOT / f"{template_id}{EXTRACTED_TEXT_SUFFIX}"


def _legacy_text_path(template_id: str) -> Path:
    return TEMPLATES_ROOT / f"{template_id}.txt"


def _record_path(record: dict[str, Any]) -> Path | None:
    suffix = record.get("suffix") or ".tex"
    path = _template_path(str(record.get("id")), suffix)
    if path.exists():
        return path
    matches = sorted(
        path
        for path in TEMPLATES_ROOT.glob(f"{record.get('id')}.*")
        if not path.name.endswith(EXTRACTED_TEXT_SUFFIX)
    )
    return matches[0] if matches else None


def _read_record_text(record: dict[str, Any], path: Path) -> str:
    mode = record.get("mode")
    if mode == "rules":
        extracted_path = _extracted_text_path(str(record.get("id")))
        if extracted_path.exists():
            return extracted_path.read_text(encoding="utf-8", errors="replace")
        legacy_path = _legacy_text_path(str(record.get("id")))
        if legacy_path.exists() and legacy_path != path:
            return legacy_path.read_text(encoding="utf-8", errors="replace")
        return extract_document_text(path)
    if mode in {"body", "granular"}:
        return path.read_text(encoding="utf-8", errors="replace")
    return ""


def _decode_template(content: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8", errors="replace")


def _slugify(text: str) -> str:
    slug = re.sub(r"[^\w\-\u4e00-\u9fff]+", "-", text, flags=re.UNICODE).strip("-")
    return slug[:48] or "template"
