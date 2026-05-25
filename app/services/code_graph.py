from __future__ import annotations

import ast
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from app.services.store import save_json


CODE_GRAPH_REPORT_RELATIVE = "artifacts/code_graph_report.md"
CODE_GRAPH_JSON_RELATIVE = "artifacts/code_graph.json"

CODE_SUFFIXES = {
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".java",
    ".go",
    ".rs",
    ".c",
    ".cc",
    ".cpp",
    ".h",
    ".hpp",
    ".cs",
    ".php",
    ".rb",
    ".swift",
    ".kt",
    ".dart",
    ".lua",
}
PYTHON_SUFFIXES = {".py"}
EXCLUDED_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".codegraph",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    "node_modules",
    "dist",
    "build",
    "release",
    "support_materials",
}
MAX_FILES = 240
MAX_FILE_BYTES = 900_000


def write_code_graph_report(root: Path) -> dict[str, str]:
    payload = build_code_graph(root)
    save_json(root / CODE_GRAPH_JSON_RELATIVE, payload)
    (root / CODE_GRAPH_REPORT_RELATIVE).write_text(render_code_graph_report(payload), encoding="utf-8")
    return {
        "code_graph_report": CODE_GRAPH_REPORT_RELATIVE,
        "code_graph_json": CODE_GRAPH_JSON_RELATIVE,
    }


def build_code_graph(root: Path) -> dict[str, Any]:
    code_files = discover_code_files(root)
    files: list[dict[str, Any]] = []
    symbols: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    parse_errors: list[dict[str, str]] = []

    for path in code_files:
        relative = path.relative_to(root).as_posix()
        file_info = {
            "path": relative,
            "suffix": path.suffix.lower(),
            "size": path.stat().st_size,
            "language": language_for_suffix(path.suffix.lower()),
            "line_count": 0,
            "parsed": False,
        }
        try:
            source = path.read_text(encoding="utf-8-sig", errors="replace")
        except OSError as exc:
            parse_errors.append({"path": relative, "error": f"{type(exc).__name__}: {exc}"})
            files.append(file_info)
            continue
        file_info["line_count"] = source.count("\n") + (1 if source else 0)
        if path.suffix.lower() in PYTHON_SUFFIXES:
            parsed = parse_python_source(relative, source)
            file_info["parsed"] = parsed["parsed"]
            symbols.extend(parsed["symbols"])
            edges.extend(parsed["edges"])
            parse_errors.extend(parsed["errors"])
        files.append(file_info)

    symbols, edges = resolve_edges(symbols, edges)
    stats = summarize_graph(files, symbols, edges, parse_errors)
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_policy": "Inspired by colbymchenry/codegraph concepts; this workbench integration is a lightweight local Python AST graph and does not vendor the Node/Tree-sitter package.",
        "upstream": {
            "source": "colbymchenry/codegraph",
            "source_url": "https://github.com/colbymchenry/codegraph",
            "license": "MIT",
            "learned_patterns": [
                "local-first deterministic AST extraction",
                "symbol nodes and typed edges such as contains/imports/calls/references",
                "entry-point context before broad file reads",
                "impact analysis from callers and callees",
                "generated graph context for AI/code review",
            ],
        },
        "stats": stats,
        "files": files,
        "symbols": symbols,
        "edges": edges,
        "entry_points": find_entry_points(files, symbols, edges),
        "hotspots": find_hotspots(symbols, edges),
        "mermaid": render_mermaid(symbols, edges),
        "parse_errors": parse_errors,
    }


def discover_code_files(root: Path) -> list[Path]:
    scan_roots = [root / name for name in ["code", "app", "scripts", "src"] if (root / name).exists()]
    if not scan_roots:
        scan_roots = [root]
    seen: set[Path] = set()
    files: list[Path] = []
    for scan_root in scan_roots:
        for path in scan_root.rglob("*"):
            if len(files) >= MAX_FILES:
                return files
            if not path.is_file():
                continue
            if any(part in EXCLUDED_DIRS for part in path.relative_to(root).parts):
                continue
            if path.suffix.lower() not in CODE_SUFFIXES:
                continue
            try:
                if path.stat().st_size > MAX_FILE_BYTES:
                    continue
            except OSError:
                continue
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            files.append(path)
    return sorted(files, key=lambda item: item.relative_to(root).as_posix())


def parse_python_source(relative: str, source: str) -> dict[str, Any]:
    try:
        tree = ast.parse(source, filename=relative)
    except SyntaxError as exc:
        return {
            "parsed": False,
            "symbols": [],
            "edges": [],
            "errors": [{"path": relative, "error": f"SyntaxError line {exc.lineno}: {exc.msg}"}],
        }
    visitor = PythonCodeGraphVisitor(relative, source)
    visitor.visit(tree)
    return {"parsed": True, "symbols": visitor.symbols, "edges": visitor.edges, "errors": []}


class PythonCodeGraphVisitor(ast.NodeVisitor):
    def __init__(self, relative_path: str, source: str):
        self.relative_path = relative_path
        self.source = source
        self.symbols: list[dict[str, Any]] = []
        self.edges: list[dict[str, Any]] = []
        self.scope: list[dict[str, Any]] = []
        self.file_id = f"file:{relative_path}"

    def visit_Import(self, node: ast.Import) -> Any:
        for alias in node.names:
            self.add_edge(self.current_id() or self.file_id, "imports", target_name=alias.name, line=node.lineno)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> Any:
        module = "." * int(node.level or 0) + (node.module or "")
        for alias in node.names:
            target = f"{module}.{alias.name}" if module else alias.name
            self.add_edge(self.current_id() or self.file_id, "imports", target_name=target, line=node.lineno)
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> Any:
        symbol = self.add_symbol(node, "class")
        self.add_contains_edge(symbol)
        for base in node.bases:
            base_name = expr_name(base)
            if base_name:
                self.add_edge(symbol["id"], "extends", target_name=base_name, line=node.lineno)
        self.add_decorator_edges(symbol, node.decorator_list)
        self.scope.append(symbol)
        self.generic_visit(node)
        self.scope.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> Any:
        self.visit_function(node, "function")

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> Any:
        self.visit_function(node, "function")

    def visit_function(self, node: ast.AST, default_kind: str) -> None:
        parent = self.scope[-1] if self.scope else None
        kind = "method" if parent and parent.get("kind") == "class" else default_kind
        symbol = self.add_symbol(node, kind)
        self.add_contains_edge(symbol)
        self.add_decorator_edges(symbol, getattr(node, "decorator_list", []))
        if getattr(node, "name", "") == "main":
            symbol["entrypoint_reason"] = "main function"
        self.scope.append(symbol)
        self.generic_visit(node)
        self.scope.pop()

    def visit_Call(self, node: ast.Call) -> Any:
        name = expr_name(node.func)
        current = self.current_id()
        if name and current:
            self.add_edge(current, "calls", target_name=name, line=getattr(node, "lineno", 0))
        self.generic_visit(node)

    def visit_If(self, node: ast.If) -> Any:
        if is_main_guard(node):
            current = self.current_id() or self.file_id
            self.add_edge(current, "references", target_name="__main__", line=getattr(node, "lineno", 0))
        self.generic_visit(node)

    def add_symbol(self, node: ast.AST, kind: str) -> dict[str, Any]:
        name = getattr(node, "name", "<anonymous>")
        qualified = ".".join([item["name"] for item in self.scope] + [name])
        symbol_id = make_symbol_id(self.relative_path, qualified, kind, getattr(node, "lineno", 0))
        symbol = {
            "id": symbol_id,
            "kind": kind,
            "name": name,
            "qualified_name": qualified,
            "file": self.relative_path,
            "line_start": getattr(node, "lineno", 0),
            "line_end": getattr(node, "end_lineno", getattr(node, "lineno", 0)),
            "parent_id": self.current_id(),
            "doc": ast.get_docstring(node) or "",
        }
        self.symbols.append(symbol)
        return symbol

    def add_contains_edge(self, symbol: dict[str, Any]) -> None:
        source = self.current_id() or self.file_id
        self.add_edge(source, "contains", target_id=symbol["id"], target_name=symbol["qualified_name"], line=symbol["line_start"])

    def add_decorator_edges(self, symbol: dict[str, Any], decorators: list[ast.AST]) -> None:
        for decorator in decorators:
            name = expr_name(decorator.func if isinstance(decorator, ast.Call) else decorator)
            if name:
                self.add_edge(symbol["id"], "decorates", target_name=name, line=getattr(decorator, "lineno", symbol["line_start"]))
            route = route_from_decorator(decorator)
            if route:
                route_id = f"route:{self.relative_path}:{route['method']}:{route['path']}:{symbol['line_start']}"
                self.symbols.append(
                    {
                        "id": route_id,
                        "kind": "route",
                        "name": f"{route['method']} {route['path']}",
                        "qualified_name": f"{route['method']} {route['path']}",
                        "file": self.relative_path,
                        "line_start": getattr(decorator, "lineno", symbol["line_start"]),
                        "line_end": getattr(decorator, "lineno", symbol["line_start"]),
                        "parent_id": self.file_id,
                        "doc": "",
                    }
                )
                self.add_edge(route_id, "references", target_id=symbol["id"], target_name=symbol["qualified_name"], line=symbol["line_start"])

    def add_edge(
        self,
        source_id: str,
        kind: str,
        target_id: str | None = None,
        target_name: str | None = None,
        line: int = 0,
    ) -> None:
        self.edges.append(
            {
                "source_id": source_id,
                "target_id": target_id or "",
                "target_name": target_name or "",
                "kind": kind,
                "file": self.relative_path,
                "line": line,
            }
        )

    def current_id(self) -> str:
        return self.scope[-1]["id"] if self.scope else ""


def expr_name(node: ast.AST | None) -> str:
    if node is None:
        return ""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = expr_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    if isinstance(node, ast.Call):
        return expr_name(node.func)
    if isinstance(node, ast.Subscript):
        return expr_name(node.value)
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return ""


def route_from_decorator(decorator: ast.AST) -> dict[str, str] | None:
    if not isinstance(decorator, ast.Call):
        return None
    name = expr_name(decorator.func).lower()
    method = ""
    for candidate in ["get", "post", "put", "patch", "delete", "options", "head", "route"]:
        if name.endswith(f".{candidate}") or name == candidate:
            method = "ANY" if candidate == "route" else candidate.upper()
            break
    if not method:
        return None
    route_path = ""
    if decorator.args:
        first = decorator.args[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            route_path = first.value
    if not route_path:
        for keyword in decorator.keywords:
            if keyword.arg in {"path", "rule"} and isinstance(keyword.value, ast.Constant) and isinstance(keyword.value.value, str):
                route_path = keyword.value.value
                break
    if not route_path:
        return None
    if method == "ANY":
        for keyword in decorator.keywords:
            if keyword.arg == "methods" and isinstance(keyword.value, (ast.List, ast.Tuple)):
                values = [item.value for item in keyword.value.elts if isinstance(item, ast.Constant) and isinstance(item.value, str)]
                if values:
                    method = ",".join(item.upper() for item in values)
    return {"method": method, "path": route_path}


def is_main_guard(node: ast.If) -> bool:
    test = node.test
    if not isinstance(test, ast.Compare):
        return False
    left = expr_name(test.left)
    if left != "__name__" or not test.comparators:
        return False
    comparator = test.comparators[0]
    return isinstance(comparator, ast.Constant) and comparator.value == "__main__"


def make_symbol_id(file_path: str, qualified_name: str, kind: str, line: int) -> str:
    raw = f"{file_path}:{kind}:{qualified_name}:{line}"
    return "symbol:" + re.sub(r"[^A-Za-z0-9_.:/-]+", "_", raw)


def resolve_edges(symbols: list[dict[str, Any]], edges: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    by_qualified: dict[str, list[str]] = defaultdict(list)
    by_simple: dict[str, list[str]] = defaultdict(list)
    for symbol in symbols:
        by_qualified[symbol["qualified_name"].lower()].append(symbol["id"])
        by_simple[symbol["name"].lower()].append(symbol["id"])

    resolved_edges: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for edge in edges:
        if not edge.get("target_id"):
            target_name = str(edge.get("target_name") or "")
            target_id = resolve_target_name(target_name, by_qualified, by_simple)
            if target_id:
                edge = {**edge, "target_id": target_id}
        key = (edge.get("source_id", ""), edge.get("target_id", ""), edge.get("target_name", ""), edge.get("kind", ""))
        if key in seen:
            continue
        seen.add(key)
        resolved_edges.append(edge)
    return symbols, resolved_edges


def resolve_target_name(target_name: str, by_qualified: dict[str, list[str]], by_simple: dict[str, list[str]]) -> str:
    if not target_name:
        return ""
    lowered = target_name.lower()
    for candidate in [lowered, lowered.split("(")[0]]:
        matches = by_qualified.get(candidate)
        if matches:
            return matches[0]
    simple = lowered.rsplit(".", 1)[-1]
    matches = by_simple.get(simple)
    return matches[0] if matches else ""


def summarize_graph(
    files: list[dict[str, Any]],
    symbols: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    parse_errors: list[dict[str, str]],
) -> dict[str, Any]:
    return {
        "file_count": len(files),
        "parsed_file_count": sum(1 for item in files if item.get("parsed")),
        "symbol_count": len(symbols),
        "edge_count": len(edges),
        "parse_error_count": len(parse_errors),
        "symbols_by_kind": dict(Counter(item["kind"] for item in symbols)),
        "edges_by_kind": dict(Counter(item["kind"] for item in edges)),
        "languages": dict(Counter(item["language"] for item in files)),
    }


def find_entry_points(files: list[dict[str, Any]], symbols: list[dict[str, Any]], edges: list[dict[str, Any]]) -> list[dict[str, Any]]:
    route_targets = {edge["target_id"] for edge in edges if edge["kind"] == "references" and edge["source_id"].startswith("route:")}
    entry_points = []
    for symbol in symbols:
        reason = symbol.get("entrypoint_reason") or ""
        if symbol["id"] in route_targets:
            reason = "web route handler"
        if symbol["name"] in {"main", "run", "solve"} and symbol["kind"] in {"function", "method"}:
            reason = reason or f"{symbol['name']} entry-like function"
        if reason:
            entry_points.append({**compact_symbol(symbol), "reason": reason})
    executable_patterns = ("run_", "main", "solve", "computed_solution")
    known_files = {item.get("file") for item in entry_points}
    for item in files:
        path = str(item.get("path") or "")
        name = Path(path).stem.lower()
        if not path.endswith(".py") or path in known_files:
            continue
        if name.startswith(executable_patterns) or "run_computed_solution" in path:
            entry_points.append(
                {
                    "kind": "file",
                    "name": Path(path).name,
                    "qualified_name": path,
                    "file": path,
                    "line_start": 1,
                    "line_end": item.get("line_count") or 1,
                    "reason": "executable solver script",
                }
            )
    return entry_points[:30]


def find_hotspots(symbols: list[dict[str, Any]], edges: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    symbols_by_id = {symbol["id"]: symbol for symbol in symbols}
    incoming = Counter(edge["target_id"] for edge in edges if edge["kind"] == "calls" and edge.get("target_id"))
    outgoing = Counter(edge["source_id"] for edge in edges if edge["kind"] == "calls")
    imports = Counter(edge["target_name"].split(".")[0] for edge in edges if edge["kind"] == "imports" and edge.get("target_name"))
    callers = [
        {**compact_symbol(symbols_by_id[symbol_id]), "incoming_calls": count}
        for symbol_id, count in incoming.most_common(12)
        if symbol_id in symbols_by_id
    ]
    callees = [
        {**compact_symbol(symbols_by_id[symbol_id]), "outgoing_calls": count}
        for symbol_id, count in outgoing.most_common(12)
        if symbol_id in symbols_by_id
    ]
    return {
        "most_called": callers,
        "most_active_callers": callees,
        "top_imports": [{"module": name, "count": count} for name, count in imports.most_common(20) if name],
    }


def compact_symbol(symbol: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": symbol.get("kind"),
        "name": symbol.get("name"),
        "qualified_name": symbol.get("qualified_name"),
        "file": symbol.get("file"),
        "line_start": symbol.get("line_start"),
        "line_end": symbol.get("line_end"),
    }


def render_mermaid(symbols: list[dict[str, Any]], edges: list[dict[str, Any]]) -> str:
    symbols_by_id = {symbol["id"]: symbol for symbol in symbols}
    resolved_calls = [edge for edge in edges if edge["kind"] in {"calls", "references"} and edge.get("target_id") in symbols_by_id and edge.get("source_id") in symbols_by_id]
    selected_ids: set[str] = set()
    for edge in resolved_calls[:40]:
        selected_ids.add(edge["source_id"])
        selected_ids.add(edge["target_id"])
        if len(selected_ids) >= 18:
            break
    if not selected_ids:
        for symbol in symbols[:14]:
            selected_ids.add(symbol["id"])
    if not selected_ids:
        return "flowchart LR\n  empty[\"未检测到可绘制的代码符号\"]"

    node_ids = {symbol_id: f"n{index}" for index, symbol_id in enumerate(sorted(selected_ids), 1)}
    lines = ["flowchart LR"]
    for symbol_id in sorted(selected_ids):
        symbol = symbols_by_id.get(symbol_id, {})
        label = mermaid_label(f"{symbol.get('kind', '')}: {symbol.get('qualified_name') or symbol.get('name')}")
        lines.append(f"  {node_ids[symbol_id]}[\"{label}\"]")
    emitted = 0
    for edge in resolved_calls:
        source = edge.get("source_id")
        target = edge.get("target_id")
        if source not in node_ids or target not in node_ids:
            continue
        label = "ref" if edge["kind"] == "references" else "calls"
        lines.append(f"  {node_ids[source]} -- {label} --> {node_ids[target]}")
        emitted += 1
        if emitted >= 28:
            break
    return "\n".join(lines)


def render_code_graph_report(payload: dict[str, Any]) -> str:
    stats = payload.get("stats", {})
    lines = [
        "# 代码图谱报告",
        "",
        f"- 生成时间：{payload.get('generated_at')}",
        "- 来源方法：学习 `colbymchenry/codegraph` 的本地 AST 图谱、符号关系、影响分析和 AI 上下文思想；当前工作台内置的是轻量 Python AST 适配，不复制上游 Node/Tree-sitter 实现。",
        f"- 扫描文件：{stats.get('file_count', 0)} 个，成功解析：{stats.get('parsed_file_count', 0)} 个，符号：{stats.get('symbol_count', 0)} 个，关系：{stats.get('edge_count', 0)} 条。",
        "",
        "## 图谱概览",
        "",
        "```mermaid",
        payload.get("mermaid") or "flowchart LR",
        "```",
        "",
        "## 入口点",
    ]
    entry_points = payload.get("entry_points") or []
    if entry_points:
        for item in entry_points:
            lines.append(f"- `{item.get('qualified_name')}` ({item.get('file')}:{item.get('line_start')})：{item.get('reason')}")
    else:
        lines.append("- 未识别到 main/run/solve 函数或 Web 路由入口。")
    lines.extend(["", "## 重要符号"])
    hotspots = payload.get("hotspots") or {}
    most_called = hotspots.get("most_called") or []
    active_callers = hotspots.get("most_active_callers") or []
    if most_called:
        lines.append("### 被调用较多")
        for item in most_called:
            lines.append(f"- `{item.get('qualified_name')}`：{item.get('incoming_calls')} 次入边，{item.get('file')}:{item.get('line_start')}")
    if active_callers:
        lines.append("### 调用较多")
        for item in active_callers:
            lines.append(f"- `{item.get('qualified_name')}`：{item.get('outgoing_calls')} 次出边，{item.get('file')}:{item.get('line_start')}")
    if not most_called and not active_callers:
        lines.append("- 暂无足够的已解析调用关系。")

    lines.extend(["", "## 依赖导入"])
    imports = hotspots.get("top_imports") or []
    if imports:
        for item in imports:
            lines.append(f"- `{item.get('module')}`：{item.get('count')} 处")
    else:
        lines.append("- 未检测到导入依赖。")

    lines.extend(["", "## 文件清单"])
    for item in payload.get("files", [])[:80]:
        parsed = "已解析" if item.get("parsed") else "未解析/文本记录"
        lines.append(f"- `{item.get('path')}`：{item.get('language')}，{item.get('line_count')} 行，{parsed}")
    if len(payload.get("files", [])) > 80:
        lines.append("- ... 文件较多，完整列表见 JSON。")

    parse_errors = payload.get("parse_errors") or []
    lines.extend(["", "## 解析提示"])
    if parse_errors:
        for item in parse_errors[:20]:
            lines.append(f"- `{item.get('path')}`：{item.get('error')}")
    else:
        lines.append("- 未检测到 Python 语法解析错误。")

    lines.extend(
        [
            "",
            "## 使用建议",
            "- 修改求解脚本前，先看入口点和调用较多的函数，优先评估它们对结果表、图片和 manifest 的影响。",
            "- 如果代码运行失败，优先结合本报告、`computed_solution_run.log` 和求解规范检查字段读取、主流程入口、输出文件写入链路。",
            "- 当前轻量图谱提供代码上下文，不替代运行测试、数据校验或人工业务判断。",
            "",
        ]
    )
    return "\n".join(lines)


def language_for_suffix(suffix: str) -> str:
    return {
        ".py": "Python",
        ".js": "JavaScript",
        ".jsx": "JavaScript JSX",
        ".ts": "TypeScript",
        ".tsx": "TypeScript TSX",
        ".java": "Java",
        ".go": "Go",
        ".rs": "Rust",
        ".c": "C",
        ".cc": "C++",
        ".cpp": "C++",
        ".h": "C/C++ Header",
        ".hpp": "C++ Header",
        ".cs": "C#",
        ".php": "PHP",
        ".rb": "Ruby",
        ".swift": "Swift",
        ".kt": "Kotlin",
        ".dart": "Dart",
        ".lua": "Lua",
    }.get(suffix, suffix.lstrip(".").upper() or "Unknown")


def mermaid_label(value: str) -> str:
    return value.replace("\\", "/").replace('"', "'")[:80]
