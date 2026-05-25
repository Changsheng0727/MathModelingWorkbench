from __future__ import annotations

import ast
import json
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from app.services.executor import run_python_script
from app.services.backend_skills import render_model_method_routes, render_standard_paper_rules
from app.services.llm_assistant import call_chat_completion, compact_analysis
from app.services.llm_solution import (
    latex_text_preserving_math,
    number_display_equations,
    public_settings,
    require_llm_configured,
)
from app.services.paper import latex_escape
from app.services.store import load_json, save_json


SCRIPT_RELATIVE = "code/run_computed_solution.py"
LOG_RELATIVE = "artifacts/computed_solution_run.log"
SPEC_RELATIVE = "artifacts/computed_solver_spec.json"
SPEC_MD_RELATIVE = "artifacts/computed_solver_spec.md"
STATUS_RELATIVE = "artifacts/computed_solution_status.json"
MANIFEST_RELATIVE = "results/computed_manifest.json"
SUMMARY_RELATIVE = "results/computed_summary.md"
PROSE_RELATIVE = "artifacts/computed_result_prose.json"
PROSE_MD_RELATIVE = "artifacts/computed_result_prose.md"
REPAIR_RELATIVE = "artifacts/computed_solver_repair.json"
REPAIR_MD_RELATIVE = "artifacts/computed_solver_repair.md"


def run_code_result_pipeline(
    root: Path,
    analysis: dict[str, Any],
    paper_options: dict[str, Any] | None = None,
) -> dict[str, str]:
    """Generate a solver plan, run project-local code, and insert computed results."""
    settings = require_llm_configured()
    paper_options = paper_options or {}
    spec = generate_solver_spec(root, analysis, paper_options)
    artifacts = write_computed_solver_script(root, analysis, spec, settings)
    clear_computed_outputs(root)
    run_result = run_computed_solver(root)
    for attempt in range(1, 3):
        if run_result.get("success"):
            break
        repair_artifacts = repair_computed_solver_after_run(root, analysis, spec, settings, run_result, attempt)
        artifacts.update(repair_artifacts)
        clear_computed_outputs(root)
        run_result = run_computed_solver(root)
    artifacts.update(artifacts_from_run_result(run_result))
    if not run_result.get("success"):
        raise RuntimeError(f"求解脚本运行失败，请查看 {run_result.get('log') or LOG_RELATIVE}")

    manifest = load_json(root / MANIFEST_RELATIVE)
    artifacts.update(write_result_integration(root, analysis, spec, manifest, paper_options))
    artifacts.update(
        {
            "computed_manifest": MANIFEST_RELATIVE,
            "computed_summary": SUMMARY_RELATIVE if (root / SUMMARY_RELATIVE).exists() else "",
        }
    )
    return {key: value for key, value in artifacts.items() if value}


def generate_solver_spec(
    root: Path,
    analysis: dict[str, Any],
    paper_options: dict[str, Any],
) -> dict[str, Any]:
    """Ask the LLM for a task-specific computational specification, not executable code."""
    settings = require_llm_configured()
    llm_solution = load_json_if_exists(root / "artifacts" / "llm_full_solution.json")
    context = {
        "analysis": compact_analysis(analysis),
        "inventory": compact_inventory(analysis.get("inventory", [])),
        "llm_solution_selection": (llm_solution.get("sections") or {}).get("selection", {}),
        "llm_solution_model_chain": (llm_solution.get("sections") or {}).get("model", {}),
        "paper_options": paper_options,
        "model_method_routes": render_model_method_routes(max_chars=5000),
        "standard_paper_rules": render_standard_paper_rules(),
    }
    rec = analysis.get("recommended_problem", {}) or {}
    prompt = f"""你是数学建模竞赛自动求解软件中的“代码求解规范设计器”。请根据赛题、附件清单和大模型题解方案，给出一个可由后端安全执行器实现的计算规范。

当前已确认选题为：{rec.get("id", "-")} 题，{rec.get("title", "")}。不得自行改选其他题目。

只输出 JSON，不要 Markdown，不要解释。必须包含字段：
{{
  "final_problem_id": "最终选择的题号，如 C",
  "final_problem_title": "最终选择的题名",
  "attachment_filters": ["用于筛选对应赛题附件的关键词"],
  "global_objective": "本次代码需要实际计算并回填论文的总体目标",
  "per_problem": [
    {{
      "problem_index": 1,
      "goal": "该子问题要由代码计算出的结果",
      "data_keywords": ["文件名、工作表或字段关键词"],
      "target_keywords": ["目标变量关键词"],
      "feature_keywords": ["重要解释变量关键词"],
      "model_family": "建议使用的数学模型或算法",
      "expected_outputs": ["应输出的表格、图片、指标"]
    }}
  ],
  "paper_result_focus": ["论文回填时最应引用的数值或图表"],
  "traceability_rules": ["防止编造数值和结果漂移的规则"]
}}

约束：
1. 不要要求执行网络访问、系统命令、删除文件或读取项目目录外文件。
2. 不要写 Python 代码；只写计算规范。
3. 每个子问题都要说明可计算输出；若某子问题数据不足，应写明需要由代码输出“数据不足说明”。
4. 所有精确数值必须等待程序从附件计算，不得在规范中预设。
5. 选择模型时参考输入中的 model_method_routes：每个子问题都要匹配题型、候选模型、应输出图表和检验方式；若不匹配，说明原因并选择更简单可复现的方法。
6. traceability_rules 必须体现输入中的 standard_paper_rules：主张-证据对齐、数值来源、图表解释、引用真实性、支撑材料和人工复核点。

输入 JSON：
```json
{json.dumps(context, ensure_ascii=False, indent=2)}
```"""
    text = call_chat_completion(prompt, max_tokens=2600, stream_label="生成代码求解规范")
    spec = json.loads(extract_json_object(text))
    spec = normalize_solver_spec(spec, analysis)
    payload = {
        "stage": "computed_solver_spec",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "settings": public_settings(settings),
        "success": True,
        "spec": spec,
    }
    save_json(root / SPEC_RELATIVE, payload)
    (root / SPEC_MD_RELATIVE).write_text(render_spec_markdown(payload), encoding="utf-8")
    return spec


def write_computed_solver_script(
    root: Path,
    analysis: dict[str, Any],
    spec: dict[str, Any],
    settings: dict[str, Any],
) -> dict[str, str]:
    script_path = root / SCRIPT_RELATIVE
    script_path.parent.mkdir(parents=True, exist_ok=True)
    context = build_solver_script_context(root, analysis, spec)
    prompt = build_solver_script_prompt(context)
    script, attempts = generate_validated_solver_script(prompt, label_prefix="生成项目求解脚本")
    script_path.write_text(script, encoding="utf-8")
    payload = {
        "stage": "computed_solver_script",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "settings": public_settings(settings),
        "generation_mode": "llm_generated_per_project",
        "script": SCRIPT_RELATIVE,
        "spec": SPEC_RELATIVE,
        "script_chars": len(script),
        "raw_file_count": len(context.get("raw_files") or []),
        "validation_attempts": attempts,
        "note": "脚本由 LLM 根据当前赛题、附件清单和求解规范当场生成；后端仅做安全校验与执行。",
    }
    save_json(root / "artifacts" / "computed_solver_script.json", payload)
    return {
        "computed_solver_spec": SPEC_MD_RELATIVE,
        "computed_solver_spec_json": SPEC_RELATIVE,
        "computed_solver_script": SCRIPT_RELATIVE,
        "computed_solver_script_json": "artifacts/computed_solver_script.json",
    }


def generate_validated_solver_script(prompt: str, max_attempts: int = 3, label_prefix: str = "生成项目求解脚本") -> tuple[str, list[dict[str, Any]]]:
    attempts: list[dict[str, Any]] = []
    repair_hint = ""
    for attempt in range(1, max_attempts + 1):
        token_budget = 6500 if attempt == 1 else 4800 if attempt == 2 else 3600
        current_prompt = prompt if not repair_hint else f"""{prompt}

The previous generated solver failed local validation. Generate a corrected full script.

Validation failure:
{repair_hint}

Prefer a compact, robust script over a long advanced implementation. Return only executable Python code."""
        try:
            raw_text = call_chat_completion(
                current_prompt,
                max_tokens=token_budget,
                attempts=2,
                stream_label=f"{label_prefix}（第 {attempt} 次）",
            )
        except Exception as exc:
            record = {
                "attempt": attempt,
                "script_chars": 0,
                "status": "api_failed",
                "error": f"{type(exc).__name__}: {exc}",
                "max_tokens": token_budget,
            }
            attempts.append(record)
            repair_hint = (
                "The upstream LLM request failed before returning code. "
                "Generate a shorter script with fewer helper functions, use simple pandas/numpy baselines, "
                "and still write results/computed_manifest.json plus results/computed_summary.md. "
                f"API failure: {record['error']}"
            )
            continue
        script = ensure_solver_chinese_font_setup(extract_python_code(raw_text))
        record = {
            "attempt": attempt,
            "script_chars": len(script),
            "status": "generated",
            "error": "",
            "max_tokens": token_budget,
        }
        try:
            validate_generated_solver_code(script)
        except Exception as exc:
            record["status"] = "validation_failed"
            record["error"] = f"{type(exc).__name__}: {exc}"
            attempts.append(record)
            repair_hint = record["error"]
            continue
        record["status"] = "validated"
        attempts.append(record)
        return script, attempts
    last_error = attempts[-1].get("error") if attempts else "未生成脚本"
    raise ValueError(f"LLM 生成的求解脚本未通过安全/结构校验：{last_error}")


def repair_computed_solver_after_run(
    root: Path,
    analysis: dict[str, Any],
    spec: dict[str, Any],
    settings: dict[str, Any],
    run_result: dict[str, Any],
    attempt: int,
) -> dict[str, str]:
    script_path = root / SCRIPT_RELATIVE
    context = build_solver_script_context(root, analysis, spec)
    current_script = script_path.read_text(encoding="utf-8", errors="replace") if script_path.exists() else ""
    log_text = read_text(root / LOG_RELATIVE, 5000) if (root / LOG_RELATIVE).exists() else ""
    prompt = f"""The project-specific solver script failed when executed.

Repair the full Python script. Return only executable Python code.

Failure status JSON:
```json
{json.dumps(run_result, ensure_ascii=False, indent=2)}
```

Run log tail:
```text
{log_text[-5000:]}
```

Current script:
```python
{current_script[:18000]}
```

Current project context JSON:
```json
{json.dumps(context, ensure_ascii=False, indent=2)}
```

Keep all original security constraints:
- no network, subprocess, shell commands, eval/exec/compile, environment variables, deletion, or project-external reads;
- write results/computed_manifest.json and results/computed_summary.md;
- if data is insufficient, emit a clear limitation instead of failing.
"""
    script, validation_attempts = generate_validated_solver_script(prompt, max_attempts=2, label_prefix=f"修复项目求解脚本（第 {attempt} 轮）")
    script_path.write_text(script, encoding="utf-8")
    latest = {
        "attempt": attempt,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "settings": public_settings(settings),
        "previous_returncode": run_result.get("returncode"),
        "previous_error": run_result.get("error", ""),
        "previous_log": run_result.get("log") or LOG_RELATIVE,
        "validation_attempts": validation_attempts,
        "script_chars": len(script),
    }
    existing = load_json_if_exists(root / REPAIR_RELATIVE)
    history = existing.get("history", []) if isinstance(existing, dict) else []
    history.append(latest)
    save_json(root / REPAIR_RELATIVE, {"stage": "computed_solver_repair", "latest_attempt": latest, "history": history})
    (root / REPAIR_MD_RELATIVE).write_text(render_repair_markdown(history), encoding="utf-8")
    return {
        "computed_solver_repair": REPAIR_MD_RELATIVE,
        "computed_solver_repair_json": REPAIR_RELATIVE,
        "computed_solver_script": SCRIPT_RELATIVE,
    }


def render_repair_markdown(history: list[dict[str, Any]]) -> str:
    lines = ["# 代码求解自动修复记录", ""]
    if not history:
        lines.append("暂无修复记录。")
        return "\n".join(lines)
    for item in history:
        lines.extend(
            [
                f"## 第 {item.get('attempt')} 次运行后修复",
                f"- 时间：{item.get('generated_at')}",
                f"- 上次返回码：{item.get('previous_returncode')}",
                f"- 上次错误：{item.get('previous_error') or '-'}",
                f"- 上次日志：`{item.get('previous_log')}`",
                f"- 新脚本长度：{item.get('script_chars')} 字符",
                "",
                "| 生成尝试 | 状态 | 错误 |",
                "|---:|---|---|",
            ]
        )
        for attempt in item.get("validation_attempts", []) or []:
            lines.append(f"| {attempt.get('attempt')} | {attempt.get('status')} | {str(attempt.get('error') or '-').replace('|', '/')} |")
        lines.append("")
    return "\n".join(lines)


def clear_computed_outputs(root: Path) -> None:
    for relative in [MANIFEST_RELATIVE, SUMMARY_RELATIVE]:
        path = root / relative
        if path.exists() and path.is_file():
            path.unlink()


def build_solver_script_context(root: Path, analysis: dict[str, Any], spec: dict[str, Any]) -> dict[str, Any]:
    llm_solution = load_json_if_exists(root / "artifacts" / "llm_full_solution.json")
    sections = llm_solution.get("sections") if isinstance(llm_solution, dict) else {}
    return {
        "analysis": compact_analysis(analysis),
        "inventory": compact_inventory(analysis.get("inventory", [])),
        "raw_files": compact_raw_files(root),
        "solver_spec": spec,
        "llm_solution_selection": (sections or {}).get("selection", {}),
        "llm_solution_model": (sections or {}).get("model", {}),
        "llm_solution_solving": (sections or {}).get("solving", {}),
        "output_contract": {
            "manifest": MANIFEST_RELATIVE,
            "summary": SUMMARY_RELATIVE,
            "tables_dir": "results/computed/tables",
            "figures_dir": "results/figures",
        },
    }


def build_solver_script_prompt(context: dict[str, Any]) -> str:
    return f"""You are writing the actual Python solver for a mathematical modeling contest project.

This code must be generated specifically for the current problem statement, attachments, and solver spec. Do not output a generic prewritten topic solver.

Return only executable Python code. Do not use Markdown fences or explanations.

Runtime contract:
1. The script will be saved as code/run_computed_solution.py and executed with the project root as cwd.
2. Define ROOT = Path(__file__).resolve().parents[1], RAW_DIR = ROOT / "raw", RESULTS_DIR = ROOT / "results".
3. Read only files under RAW_DIR. Write only under RESULTS_DIR and ROOT / "artifacts".
4. Create results/computed_manifest.json. Also create results/computed_summary.md.
5. Put result tables under results/computed/tables and figures under results/figures.
6. The manifest must be JSON and include at least:
   stage, generated_at, problem_id, problem_title, solver_spec, table_count,
   tables_overview, tables, figures, metrics, per_problem_results,
   narrative_findings, limitations, method_basis, references_used, summary_markdown.
7. Each per_problem_results item must include:
   problem_index, title, metrics, tables, figures, description, analysis,
   conclusion, limitations, method_basis.
8. Each table entry should include path, title, rows, cols, preview_records, problem_index when possible.
9. Each figure entry should include path, title, description, problem_index when possible.
10. If a subproblem cannot be solved from available data, write a clear limitation and still emit a per_problem_results item. Never invent numerical results.

Mandatory figure/font setup:
- If matplotlib is imported, configure Chinese fonts before creating figures. Use font_manager candidates
  Microsoft YaHei, SimHei, SimSun, Noto Sans CJK SC, Source Han Sans SC, Arial Unicode MS, DejaVu Sans,
  and set plt.rcParams["axes.unicode_minus"] = False. All chart titles, axis labels, legends, and annotations
  must render Chinese text correctly.

Modeling guidance:
- Inspect the available files and schemas at runtime. Use the solver spec to choose columns, objectives, and algorithms.
- Do not stop at a single naive rule when the data support validation. Build an interpretable baseline first, then add
  a stronger task-appropriate candidate and select by a documented validation metric or feasibility/cost criterion.
- For time-series forecasting, use time-respecting validation. Compare at least two of seasonal naive, rolling mean,
  exponential smoothing, ARIMA-like statsmodels fallback, regularized lag-feature regression, or guarded sklearn
  tree/boosting models when feasible. Record validation_records, MAE, RMSE, sMAPE/MAPE, selected_model, and
  model_comparison outputs.
- For logistics/network problems, model the route table as a directed path graph. Check uniqueness, path feasibility,
  node capacity, port counts, throughput, utilization, and unmet demand. Prefer a 0-1/IP formulation; if no MILP
  solver is available, implement a deterministic greedy or local-search fallback and explicitly report the
  optimality limitation.
- For equipment/resource allocation, formulate integer capacity expansion, annualized cost, labor supplement, and
  post-expansion feasibility. Use enumeration, dynamic programming, knapsack/set-cover style selection, scipy
  optimization, or deterministic greedy fallback as appropriate; include sensitivity or scenario outputs when cheap.
- Use pandas, numpy, matplotlib, and openpyxl. Optional libraries such as sklearn/scipy must be guarded with try/except and have a fallback.
- Fix random seeds for stochastic code.
- Make the script robust to Chinese column names, mixed encodings, missing sheets, and partially missing data.
- Add method_basis/references_used in the manifest: name the mathematical methods actually used and cite stable
  sources conceptually, e.g. time-series forecasting texts for rolling validation/ETS/ARIMA and operations research
  or integer programming texts for network and resource-allocation models. Do not fabricate page numbers or papers.

Security constraints:
- No network access, no subprocess/process spawning, no shell commands, no eval/exec/compile, no absolute-path reads, no deletion of files or directories.
- Do not read environment variables, credentials, browser downloads, or files outside the project raw directory.

Current project context JSON:
```json
{json.dumps(context, ensure_ascii=False, indent=2)}
```
"""


def compact_raw_files(root: Path, max_files: int = 80, max_preview_chars: int = 1200) -> list[dict[str, Any]]:
    raw_dir = root / "raw"
    if not raw_dir.exists():
        return []
    files: list[dict[str, Any]] = []
    for path in sorted(raw_dir.rglob("*")):
        if not path.is_file():
            continue
        try:
            relative = path.relative_to(root).as_posix()
        except ValueError:
            continue
        item: dict[str, Any] = {
            "path": relative,
            "suffix": path.suffix.lower(),
            "size": path.stat().st_size,
        }
        if path.suffix.lower() in {".csv", ".txt", ".md", ".json"} and path.stat().st_size <= 2_000_000:
            item["preview"] = read_text(path, max_preview_chars)
        files.append(item)
        if len(files) >= max_files:
            break
    return files


def extract_python_code(text: str) -> str:
    fenced = re.search(r"```(?:python|py)?\s*([\s\S]*?)\s*```", text, flags=re.I)
    code = fenced.group(1) if fenced else text
    code = code.strip()
    if code.lower().startswith("python\n"):
        code = code.split("\n", 1)[1].strip()
    if not code:
        raise ValueError("LLM returned an empty solver script")
    return code


def ensure_solver_chinese_font_setup(script: str) -> str:
    """Make generated matplotlib figures render Chinese labels on Windows."""
    if "configure_chinese_fonts" in script or "font.sans-serif" in script:
        return script
    if "import matplotlib.pyplot as plt" not in script:
        return script
    snippet = '''
from matplotlib import font_manager


def configure_chinese_fonts():
    candidates = [
        "Microsoft YaHei",
        "SimHei",
        "SimSun",
        "Noto Sans CJK SC",
        "Source Han Sans SC",
        "Arial Unicode MS",
        "DejaVu Sans",
    ]
    available = {font.name for font in font_manager.fontManager.ttflist}
    for name in candidates:
        if name in available:
            plt.rcParams["font.sans-serif"] = [name, "DejaVu Sans"]
            break
    plt.rcParams["axes.unicode_minus"] = False


configure_chinese_fonts()
'''
    return script.replace("import matplotlib.pyplot as plt", "import matplotlib.pyplot as plt\n" + snippet, 1)


def validate_generated_solver_code(script: str) -> None:
    try:
        tree = ast.parse(script)
    except SyntaxError as exc:
        raise ValueError(f"LLM generated invalid Python syntax: {exc}") from exc

    forbidden_import_roots = {
        "subprocess",
        "socket",
        "requests",
        "urllib",
        "http",
        "ftplib",
        "paramiko",
        "boto3",
        "fabric",
        "shutil",
    }
    forbidden_calls = {
        "eval",
        "exec",
        "compile",
        "__import__",
        "os.system",
        "os.popen",
        "os.remove",
        "os.unlink",
        "os.rmdir",
        "os.removedirs",
        "os.getenv",
        "shutil.rmtree",
        "shutil.move",
        "shutil.copytree",
        "Path.unlink",
        "Path.rmdir",
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = (alias.name or "").split(".", 1)[0]
                if root in forbidden_import_roots:
                    raise ValueError(f"Generated solver imports forbidden module: {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".", 1)[0]
            if root in forbidden_import_roots:
                raise ValueError(f"Generated solver imports forbidden module: {node.module}")
        elif isinstance(node, ast.Call):
            name = ast_call_name(node.func)
            if name in forbidden_calls:
                raise ValueError(f"Generated solver uses forbidden call: {name}")
            if name in {"unlink", "rmdir"} or name.endswith(".unlink") or name.endswith(".rmdir"):
                raise ValueError(f"Generated solver uses forbidden deletion call: {name}")
        elif isinstance(node, ast.Attribute):
            if ast_call_name(node) == "os.environ":
                raise ValueError("Generated solver must not read environment variables")

    literal_path_patterns = [
        r"open\(\s*(?:r|u|b|f|fr|rf)?[\"'][A-Za-z]:[\\/]",
        r"Path\(\s*(?:r|u|b|f|fr|rf)?[\"'][A-Za-z]:[\\/]",
        r"read_(?:csv|excel|json|table)\(\s*(?:r|u|b|f|fr|rf)?[\"'][A-Za-z]:[\\/]",
    ]
    for pattern in literal_path_patterns:
        if re.search(pattern, script):
            raise ValueError("Generated solver contains a literal absolute path read")
    if "computed_manifest.json" not in script:
        raise ValueError("Generated solver must write results/computed_manifest.json")


def ast_call_name(func: ast.AST) -> str:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        base = ast_call_name(func.value)
        if base:
            return f"{base}.{func.attr}"
        return func.attr
    return ""


def run_computed_solver(root: Path, timeout: int = 360) -> dict[str, Any]:
    result = run_python_script(root, SCRIPT_RELATIVE, LOG_RELATIVE, timeout=timeout)
    manifest_path = root / MANIFEST_RELATIVE
    manifest = load_json_if_exists(manifest_path)
    payload = {
        "stage": "computed_solution_run",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "success": bool(result.get("success")) and manifest_path.exists(),
        "returncode": result.get("returncode"),
        "executor": result.get("executor"),
        "log": result.get("log"),
        "manifest": MANIFEST_RELATIVE if manifest_path.exists() else "",
        "summary": SUMMARY_RELATIVE if (root / SUMMARY_RELATIVE).exists() else "",
        "outputs": compact_manifest(manifest),
    }
    if result.get("success") and not manifest_path.exists():
        payload["success"] = False
        payload["error"] = "求解脚本已结束，但未生成 results/computed_manifest.json。"
    save_json(root / STATUS_RELATIVE, payload)
    return payload


def write_result_integration(
    root: Path,
    analysis: dict[str, Any],
    spec: dict[str, Any],
    manifest: dict[str, Any],
    paper_options: dict[str, Any],
) -> dict[str, str]:
    prose = generate_result_prose(root, analysis, spec, manifest, paper_options)
    save_json(root / PROSE_RELATIVE, prose)
    (root / PROSE_MD_RELATIVE).write_text(render_result_prose_markdown(prose), encoding="utf-8")

    tex_path = root / "paper" / "main.tex"
    if not tex_path.exists():
        raise FileNotFoundError("paper/main.tex 不存在，无法回填计算结果")

    original = tex_path.read_text(encoding="utf-8")
    backup = root / "paper" / "main_before_computed_results.tex"
    if not backup.exists():
        shutil.copy2(tex_path, backup)

    updated = strip_auto_blocks(original)
    updated = integrate_abstract_results(updated, manifest, prose)
    updated = prune_extra_problem_sections(updated, manifest)
    updated = ensure_paper_title(updated, manifest)
    updated = ensure_method_references(updated, manifest)
    validation_block = build_computed_validation_tex(manifest, prose)
    updated = insert_computed_results_into_solving(updated, manifest, prose)
    updated = insert_before_section(updated, "模型评价与推广", validation_block)
    updated = clean_final_paper_document(updated)
    updated = number_display_equations(updated)

    filled = root / "paper" / "main_result_filled.tex"
    filled.write_text(updated, encoding="utf-8")
    tex_path.write_text(updated, encoding="utf-8")
    return {
        "computed_result_prose": PROSE_MD_RELATIVE,
        "computed_result_prose_json": PROSE_RELATIVE,
        "paper_result_filled": "paper/main_result_filled.tex",
        "paper_before_result_integration": "paper/main_before_computed_results.tex",
        "paper_main": "paper/main.tex",
    }


def generate_result_prose(
    root: Path,
    analysis: dict[str, Any],
    spec: dict[str, Any],
    manifest: dict[str, Any],
    paper_options: dict[str, Any],
) -> dict[str, Any]:
    settings = require_llm_configured()
    context = {
        "analysis": compact_analysis(analysis),
        "solver_spec": spec,
        "computed_manifest": compact_manifest(manifest),
        "computed_summary": read_text(root / SUMMARY_RELATIVE, max_chars=12000),
        "paper_options": paper_options,
    }
    prompt = f"""你是数学建模竞赛论文模型求解结果写作助手。请只基于输入中的 computed_manifest 和 computed_summary 撰写可直接放入论文“模型求解”部分的结果判读，严禁编造 manifest 以外的精确数值。

只输出 JSON，不要 Markdown，不要解释。字段：
{{
  "abstract_result_sentence": "一到两句可插入摘要的结果补充，只能引用 manifest 中已经出现的关键数字或说明",
  "abstract_problem_results": [
    {{
      "problem_index": 1,
      "result": "可放入摘要固定句式“得到……”后面的简洁结果；必须包含该问题最关键的数值或结论，不要出现具体文件名、Sheet名或题号字母"
    }}
  ],
  "solving_intro": "模型求解结果总述，说明读取了哪些附件、形成了哪些可追溯结果",
  "per_problem_commentary": [
    {{
      "problem_index": 1,
      "paragraph": "对应子问题的一段自然学术表述，同时涵盖图表内容、主要现象、数值含义和该子问题结论",
      "description": "备用字段：自然描述图表包含的变量、指标或输出，不要写字段名或标签",
      "analysis": "备用字段：自然解释趋势、差异、误差或异常，不要写字段名或标签",
      "conclusion": "备用字段：自然说明该结果怎样回答子问题，不要写字段名或标签"
    }}
  ],
  "validation_commentary": "结果可追溯性、稳定性和局限性检验说明",
  "limitations": ["仍需人工复核或进一步建模的事项"]
}}

硬性要求：
1. 每个子问题尽量输出一段自然论文段落，在同一段内完成图表内容交代、结果判读和结论落点；没有数据时必须说明“未检测到可用数据或目标字段”，不能补造结果。
2. 不要使用旧流程名、后台身份名或把软件操作写进论文，统一称为“模型求解结果”“计算结果”或“由附件数据得到的结果”。
3. 摘要中不能出现“A题/B题/C题”等题号字母，不能出现具体文件名、路径、工作表名或类似“会员信息数据.xlsx::Sheet1”的来源标识；摘要只能写问题主题、模型、算法和关键结果。
4. 若引用表格、图片或指标，必须来自 computed_manifest 中的路径、标题、指标名和数值。
5. 不要在正文段落中出现带冒号的模板化图表解读标签；如果需要表达这些内容，用连续自然段完成。
6. 所有公式如需出现，使用 $$...$$，不要写未闭合 LaTeX。

输入 JSON：
```json
{json.dumps(context, ensure_ascii=False, indent=2)}
```"""
    try:
        text = call_chat_completion(prompt, max_tokens=3000, stream_label="生成计算结果论文判读")
        prose = json.loads(extract_json_object(text))
    except Exception as exc:
        prose = local_result_prose(manifest, f"{type(exc).__name__}: {exc}")
    prose["stage"] = "computed_result_prose"
    prose["generated_at"] = datetime.now().isoformat(timespec="seconds")
    prose["settings"] = public_settings(settings)
    prose["success"] = True
    return prose


def build_computed_result_tex(manifest: dict[str, Any], prose: dict[str, Any]) -> str:
    lines = [
        "% BEGIN AUTO COMPUTED RESULTS",
        r"\subsection{模型计算结果}",
        latex_paragraph(prose.get("solving_intro") or "本节汇总由附件数据得到的可追溯结果。所有数值均来自项目 results 目录下的结果清单、结果表和图形文件。"),
        "",
    ]
    by_problem = group_problem_results(manifest)
    commentary = {
        safe_int(item.get("problem_index")): item
        for item in prose.get("per_problem_commentary", [])
        if isinstance(item, dict)
    }
    if not by_problem:
        lines.append(latex_paragraph("当前未检测到可用于所选题目的表格数据，因此仅形成数据不足说明。正式提交前需要补充附件或调整字段映射。"))
    for problem_index in sorted(by_problem):
        item = by_problem[problem_index]
        text = commentary.get(problem_index, {})
        lines.append(build_problem_computed_result_tex(manifest, problem_index, item, text, wrapped=False))
    lines.append("% END AUTO COMPUTED RESULTS")
    return "\n".join(lines) + "\n"


def build_problem_computed_result_tex(
    manifest: dict[str, Any],
    problem_index: int,
    item: dict[str, Any],
    text: dict[str, Any],
    *,
    wrapped: bool = True,
) -> str:
    lines: list[str] = []
    if wrapped:
        lines.append("% BEGIN AUTO COMPUTED RESULTS")
    lines.append(rf"\subsubsection{{问题 {problem_index} 模型求解结果}}")
    lines.append(latex_paragraph(problem_result_narrative(problem_index, item, text)))
    metrics = item.get("metrics", {}) if isinstance(item.get("metrics"), dict) else {}
    metrics_table = latex_table_from_metrics(problem_index, metrics)
    if metrics_table:
        lines.append(metrics_table)
        lines.extend(
            latex_paragraph(line)
            for line in table_commentary(
                problem_index,
                "模型求解关键指标",
                "metrics",
                metrics=metrics,
                problem_item=item,
            )
        )
    for table in tables_for_problem_output(item, problem_index):
        snippet = latex_table_from_preview(table, problem_index)
        if snippet:
            lines.append(snippet)
            title = str(table.get("title") or f"问题 {problem_index} 结果表")
            lines.extend(
                latex_paragraph(line)
                for line in table_commentary(
                    problem_index,
                    title,
                    "preview",
                    table=table,
                    problem_item=item,
                    metrics=metrics,
                )
            )
    for figure in figures_for_problem(manifest, item, problem_index):
        snippet = latex_figure(figure, problem_index)
        if snippet:
            lines.append(snippet)
    closing = problem_result_closing(problem_index, item, text)
    if closing:
        lines.append(latex_paragraph(closing))
    if wrapped:
        lines.append("% END AUTO COMPUTED RESULTS")
    return "\n".join(lines) + "\n"


def tables_for_problem_output(item: dict[str, Any], problem_index: int, max_tables: int = 6) -> list[dict[str, Any]]:
    tables = [table for table in item.get("tables", []) or [] if isinstance(table, dict)]
    if not tables:
        return []
    selected: list[dict[str, Any]]
    if problem_index == 1:
        selected = tables
    else:
        result_tables = [table for table in tables if not is_repeated_input_table(table)]
        selected = result_tables or tables
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for table in selected:
        key = str(table.get("path") or table.get("title") or id(table))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(table)
    return deduped[:max_tables]


def is_repeated_input_table(table: dict[str, Any]) -> bool:
    title = str(table.get("title") or "")
    path = str(table.get("path") or "")
    markers = ["车型需求解析", "需求汇总", "属性分布", "demand_records", "demand_summary"]
    return any(marker in title or marker in path for marker in markers)


def insert_computed_results_into_solving(tex: str, manifest: dict[str, Any], prose: dict[str, Any]) -> str:
    by_problem = group_problem_results(manifest)
    if not by_problem:
        return tex
    commentary = {
        safe_int(item.get("problem_index")): item
        for item in prose.get("per_problem_commentary", [])
        if isinstance(item, dict)
    }
    inserted = tex
    for problem_index in sorted(by_problem, reverse=True):
        item = by_problem[problem_index]
        text = commentary.get(problem_index, {})
        block = build_problem_computed_result_tex(manifest, problem_index, item, text, wrapped=True)
        inserted = insert_problem_block(inserted, problem_index, block)
    return inserted


def insert_problem_block(tex: str, problem_index: int, block: str) -> str:
    start = find_problem_solving_subsection(tex, problem_index)
    if start is None:
        return insert_before_section(tex, "模型检验", block)
    next_positions = []
    for next_index in range(problem_index + 1, problem_index + 8):
        pos = find_problem_solving_subsection(tex, next_index, start + 1)
        if pos is not None:
            next_positions.append(pos)
            break
    next_section = re.search(r"\n\\section\{", tex[start + 1 :])
    if next_section:
        next_positions.append(start + 1 + next_section.start())
    end = min(next_positions) if next_positions else len(tex)
    insertion = "\n" + block.strip() + "\n"
    return tex[:end].rstrip() + insertion + "\n" + tex[end:].lstrip()


def find_problem_solving_subsection(tex: str, problem_index: int, offset: int = 0) -> int | None:
    patterns = [
        rf"\\subsection\{{\s*问题\s*{problem_index}\s*模型求解\s*\}}",
        rf"\\subsection\{{[^}}]*{problem_index}[^}}]*模型求解[^}}]*\}}",
    ]
    for pattern in patterns:
        match = re.search(pattern, tex[offset:])
        if match:
            return offset + match.start()
    return None


def table_commentary(
    problem_index: int,
    title: str,
    kind: str,
    *,
    table: dict[str, Any] | None = None,
    metrics: dict[str, Any] | None = None,
    problem_item: dict[str, Any] | None = None,
) -> list[str]:
    if kind == "metrics":
        return [metrics_table_commentary(problem_index, title, metrics or {}, problem_item or {})]
    return [preview_table_commentary(problem_index, title, table or {}, problem_item or {}, metrics or {})]


def eldercare_metrics_commentary(problem_index: int, metrics: dict[str, Any]) -> str:
    keys = set(metrics.keys())
    if {"第5年老人总数", "第5年月有效服务需求"} & keys:
        return (
            f"表中汇总了问题{problem_index}的核心预测量：第5年老人总数为{format_metric(metrics.get('第5年老人总数'))}人，"
            f"月理论服务需求为{format_metric(metrics.get('第5年月理论服务需求'))}次，消费约束后的月有效需求为{format_metric(metrics.get('第5年月有效服务需求'))}次，"
            f"平均折减系数为{format_metric(metrics.get('消费约束平均折减系数'))}。这些数值说明后续选址模型不能只按老人数量配置站点，还必须考虑收入约束对实际服务次数的削减作用。"
        )
    if {"服务站数量", "老人覆盖率", "需求加权满意度"} & keys:
        text = (
            f"表中给出了站点布局的关键约束结果：共设置{format_metric(metrics.get('服务站数量'))}个服务站，"
            f"建设总成本为{format_metric(metrics.get('建设总成本'))}元，老人覆盖率为{format_metric(metrics.get('老人覆盖率'))}，"
            f"需求加权满意度为{format_metric(metrics.get('需求加权满意度'))}。"
        )
        if metrics.get("容量兑现率") is not None:
            text += f"容量兑现率为{format_metric(metrics.get('容量兑现率'))}，表明日容量约束对部分高需求小区产生了预约分流影响。"
        return text
    if {"最优价格系数", "年度政府补贴", "补贴后利润率"} & keys:
        return (
            f"表中反映了定价与补贴共同作用后的运营状态：最优价格系数为{format_metric(metrics.get('最优价格系数'))}，"
            f"年度政府补贴为{format_metric(metrics.get('年度政府补贴'))}元，补贴后年度利润为{format_metric(metrics.get('补贴后年度利润'))}元，"
            f"补贴后利润率为{format_metric(metrics.get('补贴后利润率'))}。该结果说明在价格满意度保持较高水平时，服务站仍可达到保本微利要求。"
        )
    if {"基准覆盖率", "最大满意度变化"} & keys:
        return (
            f"表中概括了灵敏度分析的稳定性结果：基准覆盖率为{format_metric(metrics.get('基准覆盖率'))}，"
            f"基准满意度为{format_metric(metrics.get('基准满意度'))}，扰动后最大覆盖率变化为{format_metric(metrics.get('最大覆盖率变化'))}，"
            f"最大满意度变化为{format_metric(metrics.get('最大满意度变化'))}。变化幅度较小，说明推荐站点组合在主要参数扰动下仍具有可用性。"
        )
    return ""


def eldercare_preview_commentary(problem_index: int, title: str, records: list[dict[str, Any]], rows: int) -> str:
    if not any(token in title for token in ["老人", "服务站", "满意度", "需求", "定价", "补贴", "利润", "可及性", "灵敏度", "建设方案"]):
        return ""
    if "老人结构" in title:
        total = sum(record_num(r, "老人总数") for r in records)
        top = max(records, key=lambda r: record_num(r, "老人总数"))
        return f"{title}列出了各小区第5年末自理、半失能和失能老人规模。预览记录合计老人约{total:.0f}人，其中{top.get('小区')}小区老人数量最高，为{record_num(top, '老人总数'):.0f}人，说明该小区及其邻近区域应在后续站点配置中获得更高服务权重。"
    if "服务需求预测汇总" in title:
        total_effective = sum(record_num(r, "有效月需求") for r in records)
        top = max(records, key=lambda r: record_num(r, "有效月需求"))
        return f"{title}按服务项目汇总理论需求、消费约束后需求、营收和直接支出。预览项目的有效月需求合计约{total_effective:.0f}次，其中{top.get('服务项目')}需求最高，约{record_num(top, '有效月需求'):.0f}次/月，表明高频日常服务是容量配置和运营收支测算的主要驱动项。"
    if "小区有效服务需求" in title:
        top = max(records, key=lambda r: record_num(r, "有效月需求"))
        total = sum(record_num(r, "有效月需求") for r in records)
        return f"{title}把需求落实到小区层面，预览记录的有效月需求合计约{total:.0f}次。{top.get('小区')}小区有效月需求最高，约{record_num(top, '有效月需求'):.0f}次，说明选址模型需要优先降低该类高需求小区的服务距离。"
    if "选址与规模" in title or "建设方案" in title:
        cost = sum(record_num(r, "建设成本万元") for r in records)
        min_fulfill = min((record_num(r, "容量兑现率") for r in records), default=0)
        stations = "、".join(str(r.get("服务站位置")) for r in records if r.get("服务站位置"))
        return f"{title}给出了服务站位置、规模、覆盖小区和容量利用情况。预览方案包含{rows}个站点，位置为{stations}，建设成本合计约{cost:.1f}万元，最低容量兑现率为{min_fulfill:.4f}，说明方案在预算内实现了满覆盖，但个别站点需要通过预约或分时服务消化峰值需求。"
    if "小区分配" in title:
        low = min(records, key=lambda r: record_num(r, "满意度"))
        avg = sum(record_num(r, "满意度") for r in records) / max(1, len(records))
        return f"{title}展示每个小区的归属服务站、距离、有效需求和满意度。预览记录平均满意度约{avg:.4f}，其中{low.get('小区')}小区满意度最低，为{record_num(low, '满意度'):.4f}，其服务距离或容量分配压力应作为后续方案改进的重点。"
    if "定价" in title:
        paid = [r for r in records if record_num(r, "基准价格") > 0]
        factor = record_num(paid[0], "最优价格") / max(1e-9, record_num(paid[0], "基准价格")) if paid else 1.0
        return f"{title}列出各服务项目的基准价格、最优价格、直接支出和补贴标准。付费服务的最优价格约为基准价格的{factor:.2f}倍，紧急救助保持公益免费，说明定价方案主要通过政府补贴和适度让利来同时维持价格满意度与机构微利。"
    if "补贴利润" in title:
        profit = sum(record_num(r, "补贴后利润") for r in records)
        subsidy = sum(record_num(r, "年补贴") for r in records)
        low = min(records, key=lambda r: record_num(r, "补贴后利润"))
        return f"{title}核算各服务站的年服务人次、年营收、政府补贴、总成本和补贴后利润。预览站点补贴后利润合计约{profit:.0f}元，年度补贴合计约{subsidy:.0f}元，其中{low.get('服务站位置')}站利润最低，说明该站受服务量和固定成本影响更大。"
    if "可及性" in title:
        low = min(records, key=lambda r: record_num(r, "综合满意度"))
        return f"{title}比较不同老人类型在经济约束、容量折减和满意度折减后的服务获得情况。{low.get('老人类型')}的综合满意度最低，为{record_num(low, '综合满意度'):.4f}，说明高照护强度群体虽然需求更集中，但对价格、距离和容量变化更敏感。"
    if "灵敏度" in title:
        base = records[0]
        sat_values = [record_num(r, "需求加权满意度") for r in records]
        return f"{title}比较基准方案、老人结构扰动、固定成本上升和预算提高情景。基准覆盖率为{record_num(base, '覆盖率'):.4f}，满意度在{min(sat_values):.4f}至{max(sat_values):.4f}之间变化，说明站点位置总体稳定，运营指标对成本与预算更敏感。"
    return ""


def record_num(record: dict[str, Any], key: str) -> float:
    value = record.get(key)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    match = re.search(r"-?\d+(?:\.\d+)?", str(value or "").replace(",", ""))
    return float(match.group(0)) if match else 0.0


def metrics_table_commentary(problem_index: int, title: str, metrics: dict[str, Any], problem_item: dict[str, Any]) -> str:
    if not metrics:
        return f"表中未形成可引用的数值指标，说明问题{problem_index}当前只能保留数据不足或字段缺失结论，不能在正文中补写未经计算的模型效果。"
    eldercare = eldercare_metrics_commentary(problem_index, metrics)
    if eldercare:
        return eldercare
    if "vehicle_count" in metrics and "config_switches" in metrics:
        color_switches = first_available(metrics.get("color_switches_total"), metrics.get("color_switches"))
        extra = ""
        if "C1_count" in metrics and "C2_count" in metrics:
            extra = f"；C1、C2分别承担{format_metric(metrics.get('C1_count'))}辆和{format_metric(metrics.get('C2_count'))}辆，两线负载差为{format_metric(metrics.get('line_load_gap'))}辆"
        if "objective_value" in metrics:
            extra += f"；综合目标值为{format_metric(metrics.get('objective_value'))}"
        return (
            f"由{title}可知，本问共纳入{format_metric(metrics.get('vehicle_count'))}辆车，"
            f"配置切换{format_metric(metrics.get('config_switches'))}次、颜色切换{format_metric(color_switches)}次，"
            f"最大柴油连续段为{format_metric(metrics.get('max_diesel_run'))}，最大四驱连续段为{format_metric(metrics.get('max_four_drive_run'))}{extra}。"
            f"这些指标共同反映了排产方案在需求守恒、切换代价、负载差异和连续装配风险之间的折中状态。"
        )
    if "demand_unit_total" in metrics:
        return (
            f"由{title}可知，附件计划被解析为{format_metric(metrics.get('demand_record_count'))}个正需求单元，"
            f"累计需求{format_metric(metrics.get('demand_unit_total'))}辆，覆盖{format_metric(metrics.get('brand_count'))}类品牌、"
            f"{format_metric(metrics.get('config_count'))}类配置和{format_metric(metrics.get('color_count'))}类颜色。"
            f"这说明后续优化模型的输入规模、属性差异和维度覆盖已经明确，车辆总量也可作为检验排产结果是否守恒的基准。"
        )
    phrase = metric_phrase(metrics, limit=7)
    judgment = metric_judgment(metrics, problem_item)
    return f"表中给出了问题{problem_index}的核心计算指标，其中{phrase}。这些数值刻画了本问求解结果的规模、误差、切换代价或约束状态；{judgment}"


def preview_table_commentary(
    problem_index: int,
    title: str,
    table: dict[str, Any],
    problem_item: dict[str, Any],
    metrics: dict[str, Any],
) -> str:
    records = table.get("preview_records") or []
    rows = safe_int(table.get("rows"))
    cols = safe_int(table.get("cols"))
    lower_title = title.lower()
    columns = list(records[0].keys()) if records and isinstance(records[0], dict) else []

    if not records:
        return f"{title}未给出可展示的结果记录，说明问题{problem_index}在该项输出上缺少可直接判读的数据，后续应先补充计算结果再写入结论。"

    eldercare = eldercare_preview_commentary(problem_index, title, records, rows)
    if eldercare:
        return eldercare

    if any(token in title for token in ["需求解析", "车型需求"]):
        total = metric_value(metrics, "demand_unit_total") or sum_numeric(records, "count")
        record_count = metric_value(metrics, "demand_record_count") or rows
        attrs = compact_distinct_phrase(records, ["date", "brand", "config", "power", "drive", "color"])
        first = first_record_phrase(records, ["date", "brand", "config", "power", "drive", "color", "count"])
        return (
            f"{title}把生产计划拆解为日期、品牌、配置、动力、驱动、颜色和数量等车辆需求单元，"
            f"{first}。计算结果共得到{format_metric(record_count)}个正需求单元、"
            f"需求总量{format_metric(total)}辆；{attrs}。这说明原始计划已经被转化为可进入排序模型的车辆集合，"
            f"表内属性差异与需求集中趋势决定了后续总装顺序和喷涂分线均应以该需求表为守恒基准。"
        )

    if any(token in title for token in ["需求汇总", "属性分布"]):
        top = top_count_phrase(records, item_col="item", value_col="demand_count")
        total = metric_value(metrics, "demand_unit_total")
        return (
            f"{title}按属性维度汇总需求数量，能够直接反映车辆结构是否集中在少数品牌、配置或颜色上。"
            f"{top}；需求总量为{format_metric(total)}辆。该分布说明排序模型面对的不是均匀随机车辆流，"
            f"而是带有明显属性集中性的装配任务，因此配置连续、颜色切换和动力驱动间隔需要同时纳入目标函数。"
        )

    if "目标函数分解" in title:
        objective = metric_value(metrics, "objective_value")
        values = objective_values_phrase(records)
        return (
            f"{title}给出了最终方案综合代价的分解结果，{values}；合成后的综合目标值为{format_metric(objective)}。"
            f"不同代价项之间的贡献差异说明，颜色切换、配置切换、连续段约束和喷涂线负载共同决定了方案质量，"
            f"其中权重后的高贡献项应作为后续改进排产顺序和喷涂分线的优先方向。"
        )

    if any(token in title for token in ["约束核验", "质量", "目标函数分解"]):
        config_switches = first_available(metric_value(metrics, "config_switches"), metric_from_records(records, "config_switches"))
        if "装配顺序" in title:
            color_switches = first_available(metric_from_records(records, "color_switches"), metric_value(metrics, "color_switches"))
        else:
            color_switches = first_available(
                metric_value(metrics, "color_switches_total"),
                metric_value(metrics, "color_switches"),
                metric_from_records(records, "color_switches"),
            )
        diesel_run = first_available(metric_value(metrics, "max_diesel_run"), metric_from_records(records, "max_diesel_run"))
        four_run = first_available(metric_value(metrics, "max_four_drive_run"), metric_from_records(records, "max_four_drive_run"))
        objective = metric_value(metrics, "objective_value")
        return (
            f"{title}给出了装配方案的约束满足状态和惩罚来源。结果显示配置切换为{format_metric(config_switches)}次、"
            f"颜色切换为{format_metric(color_switches)}次，最大柴油连续段为{format_metric(diesel_run)}，最大四驱连续段为{format_metric(four_run)}；"
            f"若按当前权重合成，综合目标值为{format_metric(objective)}。由此可见，方案在需求守恒基础上仍存在连续段和切换代价，"
            f"切换差异和连续段影响决定了该排序方案应被表述为可追溯的启发式可行方案，而不是未经证明的全局最优方案。"
        )

    if any(token in title for token in ["装配顺序", "排产", "排序"]):
        count = metric_value(metrics, "vehicle_count") or rows
        config_switches = metric_value(metrics, "config_switches")
        color_switches = metric_value(metrics, "color_switches")
        first = first_record_phrase(records, ["position", "brand", "config", "power", "drive", "color"])
        return (
            f"{title}按位置给出了车辆进入总装线的顺序，{first}。该序列共安排{format_metric(count)}辆车，"
            f"配置切换{format_metric(config_switches)}次、颜色切换{format_metric(color_switches)}次。"
            f"切换次数差异表明，当前方案已经形成可执行的逐车排序，但切换次数和连续段长度仍是评价工艺平稳性的关键依据。"
        )

    if any(token in title for token in ["连续批次", "配置连续"]):
        run_count = metric_value(metrics, "config_run_count") or rows
        max_run = metric_value(metrics, "max_config_run")
        switches = metric_value(metrics, "config_switches")
        return (
            f"{title}按照相邻车辆配置是否相同统计连续批次，表内记录给出了每一批次的起止位置和长度。"
            f"计算得到{format_metric(run_count)}个同配置批次，最长连续批次长度为{format_metric(max_run)}，配置切换为{format_metric(switches)}次。"
            f"连续长度差异说明模型在减少配置切换方面形成了较长连续区段，但也需要结合柴油、四驱间隔约束判断连续配置是否造成其他工艺风险。"
        )

    if any(token in title for token in ["敏感性", "权重"]):
        values = objective_values_phrase(records)
        return (
            f"{title}比较了不同权重设置下的目标函数变化，{values}。结果表明，当配置、颜色或负载相关权重提高时，"
            f"综合目标值随之变化，说明方案评价对权重口径具有可观测响应；因此最终推荐方案应同时给出采用的权重假设，"
            f"并在提交前结合企业对切换成本和间隔风险的偏好进行复核。"
        )

    if any(token in title for token in ["喷涂分线", "喷涂线", "分线"]):
        c1 = first_available(metric_value(metrics, "C1_count"), metric_from_records(records, "C1_count"))
        c2 = first_available(metric_value(metrics, "C2_count"), metric_from_records(records, "C2_count"))
        gap = first_available(metric_value(metrics, "line_load_gap"), metric_from_records(records, "line_load_gap"))
        switches = first_available(metric_value(metrics, "color_switches_total"), metric_from_records(records, "color_switches_total"))
        if metric_from_records(records, "C1_count") is not None or metric_from_records(records, "C2_count") is not None:
            c1_switches = metric_from_records(records, "C1_color_switches")
            c2_switches = metric_from_records(records, "C2_color_switches")
            return (
                f"{title}汇总了两条喷涂线的车辆负载和颜色切换代价。表内结果显示C1承担{format_metric(c1)}辆、"
                f"C2承担{format_metric(c2)}辆，C1颜色切换{format_metric(c1_switches)}次、C2颜色切换{format_metric(c2_switches)}次，"
                f"两线负载偏差为{format_metric(gap)}辆，同线颜色切换合计{format_metric(switches)}次。"
                f"负载差异较小说明分线方案较均衡，但颜色切换仍构成喷涂成本的重要来源，应与颜色序列图共同判断分线方案的可执行性。"
            )
        first = first_record_phrase(records, ["position", "brand", "config", "color", "paint_line"])
        return (
            f"{title}给出了车辆在总装顺序基础上的C1、C2分线结果，{first}。统计结果显示C1承担{format_metric(c1)}辆、"
            f"C2承担{format_metric(c2)}辆，两线负载偏差为{format_metric(gap)}辆，同线颜色切换合计{format_metric(switches)}次。"
            f"负载差异较小说明分线方案较均衡，但颜色切换仍构成喷涂成本的重要来源，应与颜色序列图共同判断分线方案的可执行性。"
        )

    if any(token in lower_title for token in ["confusion", "混淆"]):
        accuracy = metric_value(metrics, "accuracy")
        f1 = metric_value(metrics, "macro_f1")
        return (
            f"{title}展示了真实类别与预测类别的对应数量，主对角线反映正确识别样本，非对角线反映误判方向。"
            f"结合指标表可知准确率为{format_metric(accuracy)}、宏平均F1为{format_metric(f1)}，说明分类结果具有一定判别能力，"
            f"但仍存在类别混淆，后续结论应重点说明易混类别和模型适用范围。"
        )

    if any(token in title for token in ["特征重要性", "特征贡献"]):
        top = top_count_phrase(records, item_col="feature", value_col="importance") or top_count_phrase(records, item_col="feature", value_col="coefficient")
        return (
            f"{title}按贡献大小列出了影响模型判断的主要变量，{top}。这些变量代表模型最依赖的信息来源，"
            f"可用于解释预测或分类结果的形成原因；若排名靠前的变量缺乏明确业务含义，则需要回到字段命名和数据预处理环节复核。"
        )

    if any(token in title for token in ["风险评分", "预警等级", "等级分布"]):
        max_score = metric_value(metrics, "risk_score_max")
        iv_count = metric_value(metrics, "level_IV_count")
        top = top_count_phrase(records, item_col="warning_level", value_col="count")
        return (
            f"{title}给出了样本风险评分或各预警等级数量，{top}。指标表显示最大风险评分为{format_metric(max_score)}，"
            f"IV级样本数为{format_metric(iv_count)}。这表明模型能够把样本划分为不同风险层级，但等级阈值和高风险样本仍需结合实际背景复核。"
        )

    if rows and cols:
        first = first_record_phrase(records, columns[:4])
        return (
            f"{title}共包含{rows}行、{cols}列，{first}。"
            f"{record_signal_phrase(records)}这些记录说明该项计算已经形成可直接判读的数值或类别结果，"
            f"其含义应结合本问目标理解为实际状态、主要差异或约束满足程度。"
        )
    return f"{title}给出了问题{problem_index}的计算结果，表中数值应被用于说明本问的实际状态、主要差异和最终判断。"


def metric_phrase(metrics: dict[str, Any], limit: int = 7) -> str:
    selected = select_informative_metrics(metrics, limit)
    if not selected:
        selected = list(metrics.items())[:limit]
    return "、".join(f"{human_metric_name(key)}为{format_metric(value)}" for key, value in selected)


def select_informative_metrics(metrics: dict[str, Any], limit: int) -> list[tuple[str, Any]]:
    priority = [
        "demand_unit_total",
        "demand_record_count",
        "vehicle_count",
        "objective_value",
        "accuracy",
        "macro_f1",
        "mae",
        "rmse",
        "r2",
        "config_switches",
        "color_switches_total",
        "color_switches",
        "line_load_gap",
        "C1_count",
        "C2_count",
        "max_diesel_run",
        "max_four_drive_run",
        "max_config_run",
        "risk_score_max",
        "level_IV_count",
    ]
    selected = []
    for key in priority:
        if key in metrics:
            selected.append((key, metrics[key]))
    for key, value in metrics.items():
        if len(selected) >= limit:
            break
        if key not in dict(selected):
            selected.append((key, value))
    return selected[:limit]


def metric_judgment(metrics: dict[str, Any], problem_item: dict[str, Any]) -> str:
    if "objective_value" in metrics:
        return "综合目标值给出了各类切换和约束惩罚的统一评价口径，可用于比较不同权重或不同排序方案的优劣。"
    if "vehicle_count" in metrics or "demand_unit_total" in metrics:
        count = metric_value(metrics, "vehicle_count") or metric_value(metrics, "demand_unit_total")
        switches = metric_value(metrics, "config_switches")
        if switches is not None:
            return f"车辆总量与切换次数共同说明该方案已经形成完整排产序列，但仍需通过连续段和间隔指标判断工艺平稳性。"
        return f"需求总量和属性覆盖范围说明附件数据已经被转化为后续优化可使用的结构化输入。"
    if "accuracy" in metrics or "macro_f1" in metrics:
        return "准确率和F1值反映模型的分类可靠性，若数值偏低，应把结果作为辅助判别而非绝对结论。"
    if "mae" in metrics or "rmse" in metrics:
        return "误差指标越小表示预测或校正越贴近观测值，需结合基准误差或残差图判断模型是否真正改善结果。"
    return "这些指标应作为正文结论的数值来源，后续解释需围绕数值大小、排序差异和约束含义展开。"


def human_metric_name(key: str) -> str:
    mapping = {
        "demand_unit_total": "需求总量",
        "demand_record_count": "正需求单元数",
        "brand_count": "品牌数",
        "config_count": "配置数",
        "color_count": "颜色数",
        "vehicle_count": "车辆数",
        "brand_switches": "品牌切换次数",
        "config_switches": "配置切换次数",
        "color_switches": "颜色切换次数",
        "power_switches": "动力切换次数",
        "drive_switches": "驱动切换次数",
        "max_config_run": "最大同配置连续长度",
        "max_color_run": "最大同颜色连续长度",
        "max_diesel_run": "最大柴油连续段",
        "max_four_drive_run": "最大四驱连续段",
        "C1_count": "C1车辆数",
        "C2_count": "C2车辆数",
        "line_load_gap": "两线负载偏差",
        "color_switches_total": "同线颜色切换总数",
        "objective_value": "综合目标值",
        "sample_count": "样本数",
        "accuracy": "准确率",
        "macro_f1": "宏平均F1",
        "mae": "MAE",
        "rmse": "RMSE",
        "r2": "R2",
        "risk_score_max": "最大风险评分",
        "level_IV_count": "IV级样本数",
        "validation_records": "滚动验证记录数",
        "MAE": "MAE",
        "RMSE": "RMSE",
        "sMAPE": "sMAPE",
        "forecast_rows": "预测记录数",
        "forecast_flow_count": "预测流向数",
        "forecast_total_7days": "7天预测总量",
        "rule_rows": "集包规则数",
        "unique_origin_destination_rules": "首末流向唯一规则数",
        "inconsistent_route_flow_count": "路由不一致流向数",
        "route_feasible_rows": "路由可行规则数",
        "capacity_checked_sites": "容量核验场地数",
        "port_violation_sites": "格口超限场地数",
        "capacity_violation_sites": "产能超限场地数",
        "purchase_rows": "设备购置记录数",
        "total_devices": "购置设备总数",
        "labor_total_people": "人工补充人数",
        "device_annual_cost": "设备年化成本",
        "labor_annual_cost": "人工年成本",
        "total_model_defined_annual_cost": "模型口径年总成本",
        "post_expansion_port_violation_sites": "扩容后格口违约场地数",
        "post_expansion_capacity_violation_sites": "扩容后产能违约场地数",
        "rules_rows": "规则记录数",
    }
    return mapping.get(str(key), str(key).replace("_", " "))


def format_metric(value: Any) -> str:
    if value is None or value == "":
        return "未给出"
    try:
        number = float(value)
        if not np_is_finite(number):
            return str(value)
        if abs(number - round(number)) < 1e-9:
            return str(int(round(number)))
        return f"{number:.6g}"
    except Exception:
        return str(value)


def np_is_finite(number: float) -> bool:
    return number == number and number not in [float("inf"), float("-inf")]


def metric_value(metrics: dict[str, Any], key: str) -> Any:
    return metrics.get(key) if isinstance(metrics, dict) else None


def first_available(*values: Any) -> Any:
    for value in values:
        if value not in [None, ""]:
            return value
    return None


def metric_from_records(records: list[dict[str, Any]], key: str) -> Any:
    for record in records:
        if isinstance(record, dict) and record.get(key) not in [None, ""]:
            return record.get(key)
    return None


def sum_numeric(records: list[dict[str, Any]], key: str) -> Any:
    total = 0.0
    found = False
    for record in records:
        try:
            value = record.get(key)
            if value is None or value == "":
                continue
            total += float(value)
            found = True
        except Exception:
            continue
    return total if found else None


def compact_distinct_phrase(records: list[dict[str, Any]], keys: list[str]) -> str:
    parts = []
    for key in keys:
        values = [str(record.get(key, "")).strip() for record in records if str(record.get(key, "")).strip()]
        unique = list(dict.fromkeys(values))
        if unique:
            label = {
                "date": "日期",
                "brand": "品牌",
                "config": "配置",
                "power": "动力",
                "drive": "驱动",
                "color": "颜色",
            }.get(key, key)
            preview = "、".join(unique[:3])
            suffix = "等" if len(unique) > 3 else ""
            parts.append(f"{label}包括{preview}{suffix}")
    return "，".join(parts) if parts else "预览记录展示了若干车辆属性组合"


def top_count_phrase(records: list[dict[str, Any]], item_col: str, value_col: str) -> str:
    candidates = []
    for record in records:
        item = record.get(item_col)
        value = record.get(value_col)
        if item is None or value is None:
            continue
        try:
            candidates.append((str(item), float(value)))
        except Exception:
            continue
    if not candidates:
        return ""
    candidates = sorted(candidates, key=lambda item: abs(item[1]), reverse=True)
    item, value = candidates[0]
    return f"当前记录中{item}对应数值最大，为{format_metric(value)}"


def objective_values_phrase(records: list[dict[str, Any]]) -> str:
    values = []
    for record in records[:6]:
        scenario = record.get("weight_scenario") or record.get("objective_item") or record.get("dimension") or record.get("item")
        value = record.get("objective_value") or record.get("weighted_penalty") or record.get("demand_count")
        if scenario is not None and value is not None:
            values.append(f"{scenario}为{format_metric(value)}")
    if values:
        return "、".join(values[:4])
    return record_signal_phrase(records).rstrip("。") or "各项指标尚未形成可比较的目标值"


def record_signal_phrase(records: list[dict[str, Any]]) -> str:
    numeric_candidates: list[tuple[str, float]] = []
    categorical_parts: list[str] = []
    for record in records:
        if not isinstance(record, dict):
            continue
        for key, value in record.items():
            if value in [None, ""]:
                continue
            try:
                numeric_candidates.append((str(key), float(value)))
            except Exception:
                if len(categorical_parts) < 2:
                    categorical_parts.append(f"{key}为{value}")
    if numeric_candidates:
        key, value = max(numeric_candidates, key=lambda item: abs(item[1]))
        return f"表内数值项中{key}的代表性高值为{format_metric(value)}。"
    if categorical_parts:
        return "表内记录显示" + "、".join(categorical_parts) + "。"
    return ""


def first_record_phrase(records: list[dict[str, Any]], keys: list[str]) -> str:
    if not records:
        return "表中未给出预览记录"
    record = records[0]
    parts = []
    label_map = {
        "position": "首个位置",
        "date": "日期",
        "brand": "品牌",
        "config": "配置",
        "power": "动力",
        "drive": "驱动",
        "color": "颜色",
        "paint_line": "喷涂线",
        "count": "数量",
        "start_position": "起始位置",
        "end_position": "结束位置",
        "run_length": "连续长度",
    }
    for key in keys:
        if key in record and record.get(key) not in [None, ""]:
            parts.append(f"{label_map.get(key, key)}为{record.get(key)}")
    return "首条记录中" + "、".join(parts) if parts else "表内保留了可判读的结果项"


def problem_result_narrative(problem_index: int, item: dict[str, Any], text: dict[str, Any]) -> str:
    paragraph = text.get("paragraph") or text.get("result_paragraph")
    if paragraph:
        return str(paragraph)
    parts = [
        text.get("description") or item.get("description") or f"本小节展示问题{problem_index}的结果表和图形。",
        text.get("analysis") or item.get("analysis") or "这些结果用于支撑该子问题的数值判断，详细表格和图像保存在 results 目录，可在附录和支撑材料中复现。",
        text.get("conclusion") or item.get("conclusion") or "该子问题的最终数值结论应以本节表格、图形和结果清单中记录的输出为准。",
    ]
    return " ".join(str(part).strip() for part in parts if str(part or "").strip())


def problem_result_closing(problem_index: int, item: dict[str, Any], text: dict[str, Any]) -> str:
    if text.get("paragraph") or text.get("result_paragraph"):
        conclusion = text.get("conclusion") or item.get("conclusion")
        return str(conclusion or "")
    return ""


def build_computed_validation_tex(manifest: dict[str, Any], prose: dict[str, Any]) -> str:
    limitations = prose.get("limitations") or manifest.get("limitations") or []
    lines = [
        "% BEGIN AUTO COMPUTED VALIDATION",
        r"\subsection{结果可靠性与可复现性检验}",
        latex_paragraph(prose.get("validation_commentary") or "本次求解生成了计算规范、求解脚本、运行日志、结果清单、表格和图形。论文中的新增数值结论均可由这些文件追溯。"),
        "",
        r"\begin{table}[H]",
        r"\centering",
        r"\caption{求解输出文件与复核作用}",
        r"\begin{tabular}{p{0.28\textwidth}p{0.58\textwidth}}",
        r"\toprule",
        r"文件 & 复核作用\\",
        r"\midrule",
        rf"\path{{{MANIFEST_RELATIVE}}} & 记录全部表格、图形、指标和文字结论来源\\",
        rf"\path{{{SUMMARY_RELATIVE}}} & 汇总程序读取的数据、生成的结果和主要发现\\",
        rf"\path{{{LOG_RELATIVE}}} & 记录 Python 解释器、返回码、标准输出和错误输出\\",
        r"\bottomrule",
        r"\end{tabular}",
        r"\end{table}",
        latex_paragraph("表中列出了用于复核的结果清单、摘要文件和运行日志。结果清单用于追踪论文数值来源，摘要文件便于快速阅读计算结论，运行日志用于确认脚本执行状态；当摘要或正文引用精确数值时，应优先检查结果清单与对应结果表，避免出现无来源结论。"),
        "",
    ]
    if limitations:
        lines.append(r"\noindent\textbf{局限性与人工复核事项：}")
        lines.append(r"\begin{itemize}")
        for item in limitations[:8]:
            lines.append(rf"  \item {latex_inline_text(str(item))}")
        lines.append(r"\end{itemize}")
    lines.append("% END AUTO COMPUTED VALIDATION")
    return "\n".join(lines) + "\n"


def group_problem_results(manifest: dict[str, Any]) -> dict[int, dict[str, Any]]:
    grouped: dict[int, dict[str, Any]] = {}
    for item in manifest.get("per_problem_results", []) or []:
        if not isinstance(item, dict):
            continue
        index = safe_int(item.get("problem_index"))
        if not index:
            continue
        grouped[index] = item
    return grouped


def figures_for_problem(manifest: dict[str, Any], item: dict[str, Any], problem_index: int) -> list[dict[str, Any]]:
    """Return all figures that should be placed in a problem subsection.

    Per-problem result figures are generated by the solver, while data-overview
    figures are stored at manifest level. This helper keeps both close to the
    corresponding result text instead of leaving overview images unreferenced.
    """
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(figure: Any) -> None:
        if not isinstance(figure, dict):
            return
        path = str(figure.get("path") or "").strip()
        if not path or path in seen:
            return
        seen.add(path)
        selected.append(figure)

    for figure in manifest.get("figures", []) or []:
        if infer_figure_problem_index(figure) == problem_index and "numeric_distribution" in str(figure.get("path", "")):
            add(figure)
    for figure in item.get("figures", []) or []:
        add(figure)
    for figure in manifest.get("figures", []) or []:
        if infer_figure_problem_index(figure) == problem_index:
            add(figure)
    return selected


def infer_figure_problem_index(figure: dict[str, Any]) -> int | None:
    explicit = safe_int(figure.get("problem_index"))
    if explicit:
        return explicit
    text = " ".join(str(figure.get(key) or "") for key in ["path", "title", "description"])
    patterns = [
        r"problem[_\s-]*(\d+)",
        r"问题\s*(\d+)",
        r"附件\s*(\d+)",
        r"Attachment\s*(\d+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.I)
        if match:
            return safe_int(match.group(1))
    return None


def latex_table_from_metrics(problem_index: int, metrics: dict[str, Any]) -> str:
    if not metrics:
        return ""
    rows = []
    for key, value in list(metrics.items())[:12]:
        if isinstance(value, float):
            value_text = f"{value:.6g}"
        else:
            value_text = str(value)
        rows.append((human_metric_name(str(key)), value_text))
    if not rows:
        return ""
    lines = [
        r"\begin{table}[H]",
        r"\centering",
        rf"\caption{{问题 {problem_index} 模型求解关键指标}}",
        r"\begin{tabular}{p{0.38\textwidth}p{0.42\textwidth}}",
        r"\toprule",
        r"指标 & 数值\\",
        r"\midrule",
    ]
    for key, value in rows:
        lines.append(rf"{latex_escape(key)} & {latex_escape(value)}\\")
    lines.extend([r"\bottomrule", r"\end{tabular}", r"\end{table}"])
    return "\n".join(lines)


def latex_table_from_preview(table: dict[str, Any], problem_index: int) -> str:
    records = table.get("preview_records") or []
    if not records:
        return ""
    columns = list(records[0].keys())[:5]
    if not columns:
        return ""
    widths = " ".join(["p{0.17\\textwidth}" for _ in columns])
    title = table.get("title") or f"问题 {problem_index} 结果表预览"
    lines = [
        r"\begin{table}[H]",
        r"\centering",
        rf"\caption{{{latex_escape(title)}}}",
        rf"\begin{{tabular}}{{{widths}}}",
        r"\toprule",
        " & ".join(latex_escape(str(col)) for col in columns) + r"\\",
        r"\midrule",
    ]
    for record in records[:6]:
        values = [compact_cell(record.get(col, "")) for col in columns]
        lines.append(" & ".join(latex_escape(value) for value in values) + r"\\")
    lines.extend([r"\bottomrule", r"\end{tabular}", r"\end{table}"])
    return "\n".join(lines)


def latex_figure(figure: dict[str, Any], problem_index: int) -> str:
    path = figure.get("path")
    if not path:
        return ""
    title = figure_caption(figure, problem_index)
    latex_path = "../" + str(path).replace("\\", "/")
    figure_block = "\n".join(
        [
            r"\begin{figure}[H]",
            r"\centering",
            rf"\includegraphics[width=0.86\textwidth]{{\detokenize{{{latex_path}}}}}",
            rf"\caption{{{latex_escape(title)}}}",
            r"\end{figure}",
        ]
    )
    comments = figure_commentary(figure, problem_index, title)
    return "\n".join([figure_block, *[latex_paragraph(text) for text in comments if text]])


def figure_caption(figure: dict[str, Any], problem_index: int) -> str:
    title = str(figure.get("title") or "").strip()
    path = str(figure.get("path") or "")
    if "numeric_distribution" in path or title.startswith("数值变量分布"):
        sheet_hint = title.rsplit("::", 1)[-1] if "::" in title else title
        if "实验集" in sheet_hint:
            return f"问题{problem_index}实验集数值变量分布图"
        if "训练集" in sheet_hint:
            return f"问题{problem_index}训练集数值变量分布图"
        return f"问题{problem_index}附件数据数值变量分布图"
    return title or f"问题 {problem_index} 模型结果图"


def figure_commentary(figure: dict[str, Any], problem_index: int, title: str) -> list[str]:
    path = str(figure.get("path") or "")
    raw_description = str(figure.get("description") or "").strip()
    if "numeric_distribution" in path or "数值变量分布" in title:
        return [
            f"{raw_description or '该图展示输入数据中主要数值变量的分布形态、取值范围和集中趋势。'} 数值分布能够揭示变量量纲差异、偏态、长尾和潜在异常值，为后续标准化、稳健估计、特征筛选和阈值设定提供依据；由此可判断问题{problem_index}的建模输入包含可直接用于计算的连续变量，正式求解时应结合缺失概览共同决定是否进行归一化、截尾或异常值标记。"
        ]
    if "calibration" in path or "校正" in title:
        return [
            f"{raw_description or '该图展示源传感器观测值与基准观测值之间的拟合关系。'} 样本点与拟合曲线的贴合程度反映传感器系统偏差能否由线性校正解释，离群点和局部偏离提示残差结构仍需复核；结合误差指标可判断校正模型是否降低两类位移传感器之间的系统差异，并作为问题1校正结果的图形证据。"
        ]
    if "confusion" in path or "混淆矩阵" in title:
        return [
            f"{raw_description or '该图展示真实阶段与预测阶段的对应关系。'} 主对角线数量反映正确分类规模，非对角线区域揭示相邻阶段之间的误判方向和混淆程度；据此可以定位阶段判别模型的薄弱类别，并为后续风险等级继承阶段识别结果提供可靠性依据。"
        ]
    if "stage_segmentation" in path or "阶段" in title:
        return [
            f"{raw_description or '该图展示位移序列、平滑序列以及阶段转换节点的位置。'} 转换线将位移发展过程划分为不同演化区间，区间内斜率变化与阶段统计表中的平均速度相互印证；因此，所选转换节点具有明确的动力学解释，可支撑阶段识别结论。"
        ]
    if "prediction" in path or "预测" in title:
        return [
            f"{raw_description or '该图展示预测值与实际值之间的一致性。'} 样本点越接近对角线，说明模型对目标变量的预测越准确，偏离较大的点通常对应突变、强扰动或局部非线性响应时段；结合误差指标可以评价多源变量模型的趋势跟踪能力，并提示需要重点复核高扰动样本的局部误差。"
        ]
    if "risk_score" in path or "风险" in title:
        return [
            f"{raw_description or '该图展示综合风险评分随样本序号或时间的变化以及预警阈值位置。'} 风险曲线的峰值、持续高位区间和阈值穿越位置反映系统状态由低风险向高风险演化的时间特征；该曲线可作为预警等级判定的直接依据，并与等级分布表共同支撑工程预警结论。"
        ]
    return [
        f"{raw_description or f'该图为问题{problem_index}的模型结果图。'} 该图应与同一小节中的指标表和结果表联合解读，以检查模型输出是否符合数据趋势和问题约束；它支持问题{problem_index}的数值结论，并说明相关结果具有可视化依据。"
    ]


def prune_extra_problem_sections(tex: str, manifest: dict[str, Any]) -> str:
    """Remove meta-task subsections accidentally rendered as extra numbered problems."""
    indices = set(group_problem_results(manifest).keys())
    if not indices:
        return tex

    def repl(match: re.Match[str]) -> str:
        index = safe_int(match.group(1))
        if index and index not in indices:
            return "\n"
        return match.group(0)

    pattern = re.compile(
        r"\n\\subsection\{问题\s*(\d+)\s*模型(?:建立|求解)\}[\s\S]*?"
        r"(?=\n\\subsection\{问题\s*\d+\s*模型(?:建立|求解)\}|\n\\section\{)",
        flags=re.S,
    )
    return pattern.sub(repl, tex)


def ensure_paper_title(tex: str, manifest: dict[str, Any]) -> str:
    title_pattern = re.compile(r"(\\begin\{center\}\s*\n\{\\zihao\{3\}\\heiti\s*)([^{}]+?)(\}\s*\n\\end\{center\})")
    match = title_pattern.search(tex)
    if match and not is_generic_paper_title(match.group(2)):
        return tex
    corpus = json.dumps(manifest, ensure_ascii=False)[:12000]
    if not any(term in corpus for term in ["物流", "分拣", "包裹", "集包", "格口", "产能", "设备"]):
        return tex
    title = "物流网络集包规则与设备配置优化模型"
    return title_pattern.sub(lambda item: item.group(1) + latex_escape(title) + item.group(3), tex, count=1)


def is_generic_paper_title(title: Any) -> bool:
    text = re.sub(r"\\[A-Za-z]+\{?|\}|\s+", "", str(title or ""))
    return text in {
        "",
        "数学建模论文",
        "数学建模问题",
        "所选赛题",
        "正式论文标题",
        "待定论文标题",
    }


def ensure_method_references(tex: str, manifest: dict[str, Any]) -> str:
    """Bind listed references to the methods used in the body with real cite commands."""
    tex, labels = normalize_reference_section(tex)
    if r"\subsection{文献与方法依据}" in tex:
        return tex
    basis = method_reference_basis_latex(manifest, labels)
    if not basis:
        return tex
    return re.sub(r"(\\section\{模型建立\}\s*)", lambda match: match.group(1) + basis + "\n", tex, count=1)


def normalize_reference_section(tex: str) -> tuple[str, dict[str, str]]:
    labels = infer_existing_bib_labels(tex)
    if labels:
        return tex, labels

    pattern = re.compile(
        r"(\\section\{参考文献\}\s*)\\begin\{enumerate\}([\s\S]*?)\\end\{enumerate\}",
        flags=re.S,
    )
    match = pattern.search(tex)
    if not match:
        return tex, {}

    items = [
        item.strip()
        for item in re.split(r"\n\s*\\item\s+", "\n" + match.group(2).strip())
        if item.strip()
    ]
    if not items:
        return tex, {}

    used: set[str] = set()
    bib_lines = [r"\begin{thebibliography}{99}"]
    labels = {}
    for index, item in enumerate(items, 1):
        label = unique_reference_label(reference_label(item, index), used)
        labels.update(reference_hint_labels(item, label))
        bib_lines.append(rf"\bibitem{{{label}}} {item}")
    bib_lines.append(r"\end{thebibliography}")
    replacement = match.group(1) + "\n".join(bib_lines)
    return tex[: match.start()] + replacement + tex[match.end() :], labels


def infer_existing_bib_labels(tex: str) -> dict[str, str]:
    labels: dict[str, str] = {}
    for match in re.finditer(r"\\bibitem\{([^{}]+)\}([^\n]*)", tex):
        label = match.group(1)
        text = match.group(2)
        labels.update(reference_hint_labels(text, label))
    return labels


def reference_label(item: str, index: int) -> str:
    lower = item.lower()
    if "hyndman" in lower or "forecasting: principles" in lower:
        return "hyndman_forecasting"
    if "box" in lower or "jenkins" in lower or "time series analysis" in lower:
        return "box_time_series"
    if "winston" in lower or "operations research" in lower:
        return "winston_operations"
    if "nemhauser" in lower or "wolsey" in lower or "combinatorial optimization" in lower:
        return "nemhauser_integer"
    if "赛题" in item or "题面" in item or "组委会" in item or "数据材料" in item:
        return "contest_statement"
    return f"ref{index}"


def unique_reference_label(label: str, used: set[str]) -> str:
    base = re.sub(r"[^A-Za-z0-9_:-]", "_", label) or "ref"
    candidate = base
    counter = 2
    while candidate in used:
        candidate = f"{base}_{counter}"
        counter += 1
    used.add(candidate)
    return candidate


def reference_hint_labels(item: str, label: str) -> dict[str, str]:
    lower = item.lower()
    hints: dict[str, str] = {}
    if "赛题" in item or "题面" in item or "组委会" in item or "数据材料" in item:
        hints["contest"] = label
    if "hyndman" in lower or "forecasting" in lower:
        hints["forecast_hyndman"] = label
    if "box" in lower or "jenkins" in lower or "time series" in lower or "arima" in lower:
        hints["forecast_box"] = label
    if "winston" in lower or "operations research" in lower:
        hints["optimization_winston"] = label
    if "nemhauser" in lower or "wolsey" in lower or "integer" in lower or "combinatorial" in lower:
        hints["optimization_integer"] = label
    return hints


def method_reference_basis_latex(manifest: dict[str, Any], labels: dict[str, str]) -> str:
    if not labels:
        return ""
    topic_text = " ".join(
        [
            str(manifest.get("problem_title") or ""),
            json.dumps(manifest.get("metrics", {}), ensure_ascii=False),
            " ".join(str(item.get("title") or "") for item in manifest.get("per_problem_results", []) if isinstance(item, dict)),
        ]
    )
    forecast_cite = cite_from_labels(labels, ["forecast_hyndman", "forecast_box"])
    opt_cite = cite_from_labels(labels, ["optimization_winston", "optimization_integer"])
    contest_cite = cite_from_labels(labels, ["contest"])

    if any(term in topic_text for term in ["物流", "分拣", "包裹", "集包", "格口", "产能", "设备"]):
        sentences = [
            "本文的模型选择将参考文献对应到具体求解环节，而不是把文献作为装饰性列表。",
        ]
        if forecast_cite:
            sentences.append(
                f"货量预测部分参考时间序列预测中的滚动起点验证、季节朴素、指数平滑和 ARIMA 候选模型比较思想{forecast_cite}，并以验证误差决定最终预测规则。"
            )
        if opt_cite:
            sentences.append(
                f"集包规则与设备扩容部分参考运筹学和整数规划中的“变量--目标--约束”建模范式{opt_cite}，把路由可达性、格口数量、产能上限和年化成本写成可核验约束。"
            )
        if contest_cite:
            sentences.append(f"业务参数、数据字段和提交结果口径均以赛题材料为准{contest_cite}。")
        sentences.append("上述文献只提供方法依据，论文中的预测值、规则数量、设备数量和成本数值均由附件数据计算得到。")
        return "\\subsection{文献与方法依据}\n" + latex_paragraph_preserving_citations("".join(sentences))

    available = [labels[key] for key in labels if key != "contest"]
    if not available:
        return ""
    cites = r"\cite{" + ",".join(dict.fromkeys(available[:4])) + "}"
    return "\\subsection{文献与方法依据}\n" + latex_paragraph_preserving_citations(
        f"本文根据任务类型选择预测、统计学习、网络优化或整数规划方法，方法来源参考相关教材与经典文献{cites}；所有精确数值仍以附件数据和程序计算结果为准。"
    )


def cite_from_labels(labels: dict[str, str], keys: list[str]) -> str:
    selected = [labels[key] for key in keys if key in labels]
    selected = list(dict.fromkeys(selected))
    return r"\cite{" + ",".join(selected) + "}" if selected else ""


def latex_paragraph_preserving_citations(text: str) -> str:
    parts = re.split(r"(\\cite\{[^{}]+\})", str(text or ""))
    rendered = []
    for part in parts:
        if not part:
            continue
        if re.fullmatch(r"\\cite\{[^{}]+\}", part):
            rendered.append(part)
        else:
            rendered.append(latex_text_preserving_math(part))
    return "".join(rendered) + "\n"


def integrate_abstract_results(tex: str, manifest: dict[str, Any], prose: dict[str, Any]) -> str:
    pattern = re.compile(
        r"(% BEGIN AUTO COMPUTED ABSTRACT[\s\S]*?% END AUTO COMPUTED ABSTRACT\s*)",
        flags=re.S,
    )
    tex = pattern.sub("", tex)
    abstract_match = re.search(
        r"(\\noindent\\textbf\{摘要[：:]?\}\s*)([\s\S]*?)(?=\n\s*\\noindent\\textbf\{关键词[：:]?\})",
        tex,
    )
    if not abstract_match:
        return tex

    abstract = sanitize_abstract_text(abstract_match.group(2))
    abstract = rebuild_computed_abstract(abstract, manifest, prose)
    return tex[: abstract_match.start(2)] + abstract + tex[abstract_match.end(2) :]


def rebuild_computed_abstract(existing_abstract: str, manifest: dict[str, Any], prose: dict[str, Any]) -> str:
    by_problem = group_problem_results(manifest)
    if not by_problem:
        return sanitize_abstract_text(existing_abstract)

    title = clean_abstract_problem_title(manifest.get("problem_title") or "")
    if not title or title == "赛题":
        title = clean_abstract_problem_title(extract_topic_from_abstract(existing_abstract))
    if not title:
        title = "所研究问题"

    sentences = [
        abstract_intro_sentence(title, manifest),
        abstract_method_chain_sentence(manifest),
    ]
    results = abstract_problem_results(manifest, prose)
    for problem_index in sorted(by_problem):
        item = by_problem[problem_index]
        method = abstract_problem_method_phrase(problem_index, item, manifest)
        result = sanitize_abstract_result(results.get(problem_index) or abstract_result_from_problem_item(problem_index, item))
        if not result:
            result = "由附件数据计算得到可追溯结果"
        sentences.append(f"针对问题{problem_index}，{method}，得到{result}。")
    reliability = abstract_reliability_sentence(manifest)
    if reliability:
        sentences.append(reliability)
    return sanitize_abstract_text("".join(sentences))


def clean_abstract_problem_title(title: Any) -> str:
    text = sanitize_abstract_text(str(title or ""))
    text = re.sub(r"^\s*赛题\s*[A-H]\s*[：:、\-—\s]*", "", text)
    text = re.sub(r"^\s*[A-H]\s*题\s*[：:、\-—\s]*", "", text)
    text = re.sub(r"^赛题[：:、\-—\s]*", "", text)
    return text.strip(" ：:，,。")


def extract_topic_from_abstract(abstract: str) -> str:
    match = re.search(r"针对(.{4,80}?)(?:中|的)(?:多源|综合|联合|预测|优化|建模)", abstract)
    return match.group(1) if match else ""


def abstract_intro_sentence(title: str, manifest: dict[str, Any]) -> str:
    corpus = json.dumps(manifest, ensure_ascii=False)[:12000]
    if any(term in corpus for term in ["物流", "分拣", "包裹", "集包", "格口", "产能", "设备"]):
        return (
            f"针对{title}中首末流向货量预测、路径集包规则和设备扩容配置的联合优化问题，"
            "本文以历史包裹量、唯一走货路由、现有分拣能力和候选设备参数为依据，"
            "构建预测--路由约束--容量扩容的可追溯建模流程。"
        )
    return f"针对{title}中的数据预测、约束优化和决策评价问题，本文依据题目数据建立可复现的模型求解流程。"


def abstract_method_chain_sentence(manifest: dict[str, Any]) -> str:
    corpus = json.dumps(manifest, ensure_ascii=False)[:12000]
    if any(term in corpus for term in ["物流", "分拣", "包裹", "集包", "格口", "产能", "设备"]):
        return (
            "首先按日期和首末分拣流向清洗聚合货量序列，并通过滚动验证比较候选预测规则；"
            "随后形成流向预测需求并识别稀疏流向的稳健兜底规则；"
            "再将走货路由转化为有向路径集合，建立满足唯一性、可达性、格口和产能约束的集包规则模型；"
            "最后在货量增长情景下引入设备购置、人工补充和年化成本变量，形成容量扩容与成本控制联合优化模型。"
        )
    return (
        "首先完成字段识别、缺失异常处理和样本对齐；随后根据子问题目标建立预测、分类、网络优化或资源配置模型；"
        "最后通过误差指标、约束核验和敏感性分析检验结果可靠性。"
    )


def abstract_problem_method_phrase(problem_index: int, item: dict[str, Any], manifest: dict[str, Any]) -> str:
    text = " ".join(str(item.get(key) or "") for key in ["title", "description", "analysis", "conclusion"])
    metrics = item.get("metrics") if isinstance(item.get("metrics"), dict) else {}
    if any(key in metrics for key in ["purchase_rows", "total_devices", "device_annual_cost", "post_expansion_capacity_violation_sites"]) or any(term in text for term in ["设备", "扩容", "增长", "人工"]):
        return "考虑货量增长、设备年化成本、格口和产能双重约束，建立设备购置与人工补充联合整数优化模型，采用单位能力成本筛选和缺口补齐策略"
    if any(key in metrics for key in ["rule_rows", "route_feasible_rows", "port_violation_sites", "capacity_violation_sites"]) or any(term in text for term in ["集包", "路由", "格口", "产能"]):
        return "考虑唯一走货路由、建包节点可达性、格口数量和产能上限，建立有向路径上的0-1集包规则优化模型，采用候选弧枚举、规则唯一性约束和容量可行性核验"
    if any(key in metrics for key in ["forecast_rows", "forecast_flow_count", "forecast_total_7days"]) or any(term in text for term in ["预测", "货量", "包裹"]):
        return "考虑流向层级差异、星期周期、短期波动和数据稀疏性，建立滚动验证驱动的分层时间序列预测模型，采用季节朴素、近邻滚动均值和稳健中位数兜底的模型选择策略"
    return f"围绕该子问题的输入变量、约束条件和目标输出，建立任务适配的数学模型并采用可复现实验流程"


def append_abstract_result_sentence(tex: str, sentence: str) -> str:
    """Backward-compatible wrapper; new code should use integrate_abstract_results."""
    sentence = sanitize_abstract_text(sentence.strip())
    if not sentence:
        return tex
    keyword_match = re.search(r"\n\s*\\noindent\\textbf\{关键词", tex)
    if keyword_match:
        return tex[: keyword_match.start()] + "\n" + latex_text_preserving_math(sentence) + "\n" + tex[keyword_match.start() :]
    return tex


def abstract_problem_results(manifest: dict[str, Any], prose: dict[str, Any]) -> dict[int, str]:
    results: dict[int, str] = {}
    for item in manifest.get("per_problem_results", []) or []:
        if not isinstance(item, dict):
            continue
        index = safe_int(item.get("problem_index"))
        if index:
            results[index] = abstract_result_from_problem_item(index, item)
    for item in prose.get("abstract_problem_results", []) or []:
        if not isinstance(item, dict):
            continue
        index = safe_int(item.get("problem_index"))
        result = sanitize_abstract_result(str(item.get("result") or ""))
        if index and result and index not in results:
            results[index] = result
    return {index: result for index, result in results.items() if result}


def abstract_result_from_problem_item(problem_index: int, item: dict[str, Any]) -> str:
    metrics = item.get("metrics") if isinstance(item.get("metrics"), dict) else {}
    title = " ".join(str(item.get(key) or "") for key in ["title", "description", "analysis", "conclusion"])
    metric = lambda key: metric_lookup(metrics, key)

    if any(key in metrics for key in ["forecast_rows", "forecast_flow_count", "forecast_total_7days"]):
        start = metric("forecast_start")
        end = metric("forecast_end")
        period = f"{start}至{end}" if start and end else "未来7天"
        parts = [
            f"覆盖{format_abstract_number(metric('forecast_flow_count'))}个首末流向",
            f"{period}预测记录{format_abstract_number(metric('forecast_rows'))}条",
            f"预测总包裹量{format_abstract_number(metric('forecast_total_7days'))}件",
        ]
        errors = []
        if metric("MAE") is not None:
            errors.append(f"MAE={format_abstract_number(metric('MAE'))}")
        if metric("RMSE") is not None:
            errors.append(f"RMSE={format_abstract_number(metric('RMSE'))}")
        if metric("sMAPE") is not None:
            errors.append(f"sMAPE={format_abstract_number(metric('sMAPE'))}")
        if errors:
            parts.append("滚动验证" + "、".join(errors))
        return "，".join(part for part in parts if "None" not in str(part))

    if any(key in metrics for key in ["rule_rows", "route_feasible_rows", "port_violation_sites", "capacity_violation_sites"]):
        parts = [
            f"生成{format_abstract_number(metric('rule_rows'))}条集包规则",
            f"{format_abstract_number(metric('route_feasible_rows'))}条通过路由可行性检查",
        ]
        if metric("capacity_checked_sites") is not None:
            parts.append(f"核验{format_abstract_number(metric('capacity_checked_sites'))}个分拣中心容量")
        if metric("port_violation_sites") is not None or metric("capacity_violation_sites") is not None:
            parts.append(
                f"发现{format_abstract_number(metric('port_violation_sites'))}个格口超限场地和{format_abstract_number(metric('capacity_violation_sites'))}个产能超限场地"
            )
        return "，".join(parts)

    if any(key in metrics for key in ["purchase_rows", "total_devices", "device_annual_cost", "post_expansion_capacity_violation_sites"]):
        parts = [
            f"形成{format_abstract_number(metric('purchase_rows'))}条设备购置记录",
            f"合计购置{format_abstract_number(metric('total_devices'))}台设备",
        ]
        if metric("labor_total_people") is not None:
            parts.append(f"人工补充{format_abstract_number(metric('labor_total_people'))}人")
        if metric("device_annual_cost") is not None:
            parts.append(f"设备年化成本{format_abstract_number(metric('device_annual_cost'))}元")
        if metric("post_expansion_port_violation_sites") is not None or metric("post_expansion_capacity_violation_sites") is not None:
            parts.append(
                f"扩容后格口和产能违约场地分别为{format_abstract_number(metric('post_expansion_port_violation_sites'))}个、{format_abstract_number(metric('post_expansion_capacity_violation_sites'))}个"
            )
        return "，".join(parts)

    if any(key in metrics for key in ["accuracy", "macro_f1", "f1", "weighted_f1"]):
        parts = []
        if metric("accuracy") is not None:
            parts.append(f"准确率为 {format_metric_value(metric('accuracy'))}")
        if metric("macro_f1") is not None:
            parts.append(f"宏平均 F1 为 {format_metric_value(metric('macro_f1'))}")
        elif metric("f1") is not None:
            parts.append(f"F1 为 {format_metric_value(metric('f1'))}")
        return "、".join(parts) + " 的阶段识别与分类评价结果"

    if any(key in metrics for key in ["tau1_index", "tau2_index", "tau1", "tau2"]):
        tau1 = metric("tau1_index") if metric("tau1_index") is not None else metric("tau1")
        tau2 = metric("tau2_index") if metric("tau2_index") is not None else metric("tau2")
        parts = []
        if tau1 is not None:
            parts.append(f"$\\tau_1={format_metric_value(tau1)}$")
        if tau2 is not None:
            parts.append(f"$\\tau_2={format_metric_value(tau2)}$")
        return "转换节点" + "、".join(parts) + "及三阶段划分结果" if parts else "三阶段划分结果"

    if any(key in metrics for key in ["risk_score_max", "risk_score_mean", "threshold_q90", "threshold_q75"]):
        parts = []
        if metric("risk_score_max") is not None:
            parts.append(f"最大综合风险评分为 {format_metric_value(metric('risk_score_max'))}")
        if metric("risk_score_mean") is not None:
            parts.append(f"平均风险评分为 {format_metric_value(metric('risk_score_mean'))}")
        if metric("threshold_q90") is not None:
            parts.append(f"高风险分位阈值为 {format_metric_value(metric('threshold_q90'))}")
        return "、".join(parts) + " 的预警等级判定结果"

    if any(key in metrics for key in ["mae", "rmse", "r2", "mape"]):
        parts = []
        if metric("mae") is not None:
            parts.append(f"MAE 为 {format_metric_value(metric('mae'))}")
        if metric("rmse") is not None:
            parts.append(f"RMSE 为 {format_metric_value(metric('rmse'))}")
        if metric("r2") is not None:
            parts.append(f"$R^2$ 为 {format_metric_value(metric('r2'))}")
        if "校正" in title or problem_index == 1:
            return "、".join(parts) + " 的位移校正序列与残差评价结果"
        return "、".join(parts) + " 的多源预测与误差评价结果"

    conclusion = sanitize_abstract_result(str(item.get("conclusion") or item.get("analysis") or ""))
    if conclusion:
        conclusion = re.sub(r"^问题\s*\d+\s*的?", "", conclusion)
        return conclusion.rstrip("。")
    return "由附件数据计算得到的模型求解结果"


def format_metric_value(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value)


def metric_lookup(metrics: dict[str, Any], key: str) -> Any:
    if key in metrics:
        return metrics.get(key)
    lower_key = key.lower()
    for existing, value in metrics.items():
        if str(existing).lower() == lower_key:
            return value
    return None


def format_abstract_number(value: Any) -> str:
    if value is None or value == "":
        return "未给出"
    if isinstance(value, str):
        return value
    try:
        number = float(value)
    except Exception:
        return str(value)
    if not np_is_finite(number):
        return str(value)
    if abs(number - round(number)) < 1e-9:
        integer = int(round(number))
        return f"{integer:,}" if abs(integer) >= 10000 else str(integer)
    abs_number = abs(number)
    if abs_number >= 10000:
        return f"{number:,.2f}".rstrip("0").rstrip(".")
    if abs_number >= 1:
        return f"{number:.3f}".rstrip("0").rstrip(".")
    return f"{number:.4f}".rstrip("0").rstrip(".")


def abstract_reliability_sentence(manifest: dict[str, Any]) -> str:
    metrics = manifest.get("metrics") if isinstance(manifest.get("metrics"), dict) else {}
    p1 = metrics.get("problem_1") if isinstance(metrics.get("problem_1"), dict) else {}
    p2 = metrics.get("problem_2") if isinstance(metrics.get("problem_2"), dict) else {}
    p3 = metrics.get("problem_3") if isinstance(metrics.get("problem_3"), dict) else {}
    parts = []
    if p1.get("validation_records") is not None:
        parts.append(f"{format_abstract_number(p1.get('validation_records'))}条滚动验证记录")
    if p2.get("route_feasible_rows") is not None:
        parts.append(f"{format_abstract_number(p2.get('route_feasible_rows'))}条路由可行性核验")
    if p3.get("capacity_checked_sites") is not None:
        parts.append(f"{format_abstract_number(p3.get('capacity_checked_sites'))}个场地扩容后容量复核")
    if parts:
        corpus = json.dumps(manifest, ensure_ascii=False)[:12000]
        target = "物流网络集包规则制定和设备配置" if any(term in corpus for term in ["物流", "分拣", "包裹", "集包", "格口", "产能", "设备"]) else "相关预测、优化和决策"
        return "通过" + "、".join(parts) + f"检验结果的可靠性、可追溯性与工程可执行性，说明模型能够为{target}提供量化依据。"
    table_count = manifest.get("table_count")
    figure_count = manifest.get("figure_count") or len(manifest.get("figures", []) or [])
    if table_count or figure_count:
        return f"本次求解形成{format_abstract_number(table_count)}个结果表和{format_abstract_number(figure_count)}张图，所有关键结论均可追溯到计算结果。"
    return ""


def sanitize_abstract_result(text: str) -> str:
    text = sanitize_abstract_text(text)
    text = re.sub(r"^(得到|获得|形成)", "", text).strip()
    return text.rstrip("。；;，,")


def sanitize_abstract_text(text: str) -> str:
    text = str(text or "")
    text = re.sub(r"\s*% BEGIN AUTO COMPUTED ABSTRACT[\s\S]*?% END AUTO COMPUTED ABSTRACT\s*", "", text, flags=re.S)
    text = re.sub(r"([围绕针对关于基于])\s*[A-H]\s*题[“\"]([^”\"]+)[”\"]", r"\1\2", text)
    text = re.sub(r"([围绕针对关于基于])\s*[A-H]\s*题", r"\1赛题", text)
    text = re.sub(r"(?<!问题)[A-H]\s*题[“\"][^”\"]+[”\"]", "赛题", text)
    text = re.sub(r"(?<!问题)[A-H]\s*题", "赛题", text)
    text = re.sub(r"附件[一二三四五六七八九十\d]+[“\"][^”\"]+\.(?:xlsx|xls|csv|txt|pdf|docx)(?:::?Sheet\d+)?[^”\"]*[”\"]", "附件数据", text, flags=re.I)
    text = re.sub(r"[\w\u4e00-\u9fff（）()《》\-—·]+?\.(?:xlsx|xls|csv|txt|pdf|docx)(?:::?Sheet\d+)?", "附件数据", text, flags=re.I)
    text = re.sub(r"::\s*Sheet\d+", "", text, flags=re.I)
    text = text.replace("computed_manifest", "结果清单").replace("computed_summary", "结果摘要")
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip()


def insert_before_section(tex: str, section_title: str, block: str) -> str:
    pattern = re.compile(rf"\\section\{{{re.escape(section_title)}\}}")
    match = pattern.search(tex)
    if not match:
        appendix = re.search(r"\\appendix", tex)
        pos = appendix.start() if appendix else tex.rfind(r"\end{document}")
        if pos < 0:
            return tex + "\n" + block
        return tex[:pos] + "\n" + block + "\n" + tex[pos:]
    return tex[: match.start()] + "\n" + block + "\n" + tex[match.start() :]


def strip_auto_blocks(tex: str) -> str:
    patterns = [
        r"\n?% BEGIN AUTO COMPUTED RESULTS[\s\S]*?% END AUTO COMPUTED RESULTS\n?",
        r"\n?% BEGIN AUTO COMPUTED VALIDATION[\s\S]*?% END AUTO COMPUTED VALIDATION\n?",
        r"\n?% BEGIN AUTO COMPUTED ABSTRACT[\s\S]*?% END AUTO COMPUTED ABSTRACT\n?",
    ]
    for pattern in patterns:
        tex = re.sub(pattern, "\n", tex, flags=re.S)
    return tex


def latex_paragraph(text: str) -> str:
    text = str(text or "").strip()
    if not text:
        return ""
    text = clean_final_paper_prose(text)
    text = normalize_path_text(text)
    path_pattern = r"((?:results|artifacts|code|paper)/[^\s，。；;：:、]+|[A-Za-z0-9_.-]*_[A-Za-z0-9_.-]*\.(?:csv|png|json|py|md|tex|xlsx|xls))"
    parts = re.split(path_pattern, text)
    rendered = []
    for part in parts:
        if not part:
            continue
        if re.match(r"^(?:results|artifacts|code|paper)/", part) or re.match(r"^[A-Za-z0-9_.-]*_[A-Za-z0-9_.-]*\.(?:csv|png|json|py|md|tex|xlsx|xls)$", part):
            rendered.append(r"\texttt{" + latex_escape(part) + "}")
        else:
            rendered.append(latex_text_preserving_math(part))
    return "".join(rendered) + "\n"


def clean_final_paper_prose(text: str) -> str:
    """Remove workflow labels that should never appear in the final paper."""
    replacements = {
        "LLM 规划的代码求解结果回填": "模型求解结果",
        "LLM 规划的代码求解结果": "模型求解结果",
        "程序计算结果回填": "模型求解结果",
        "计算结果回填": "模型求解结果",
        "程序计算结果": "计算结果",
        "程序生成结果图": "模型结果图",
        "程序生成的结果表": "模型结果表",
        "结果回填": "结果整合",
        "自动求解过程": "求解过程",
        "本次回填": "本次求解",
        "回填保留": "求解保留",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    label_patterns = [
        r"(?:表格|图形|结果)?描述[:：]\s*",
        r"(?:表格|图形|结果)?分析[:：]\s*",
        r"(?:表格|图形|结果)?结论[:：]\s*",
        r"描述部分\s*",
        r"分析部分\s*",
        r"结论部分\s*",
    ]
    for pattern in label_patterns:
        text = re.sub(pattern, "", text)
    return re.sub(r"\s{2,}", " ", text).strip()


def clean_final_paper_document(tex: str) -> str:
    """Clean final-paper wording while preserving LaTeX structure."""
    tex = replace_legacy_symbol_table(tex)
    replacements = {
        r"\subsubsection{结果表格与图形解释}": "",
        r"\subsubsection{结果组织与判读}": "",
        r"\subsection{LLM 规划的代码求解结果回填}": r"\subsection{模型计算结果}",
        "程序计算关键指标": "模型求解关键指标",
        "LLM 规划的代码求解结果": "模型求解结果",
        "程序计算结果": "计算结果",
        "结果回填": "结果整合",
        "本次回填": "本次求解",
        "给出描述、分析和结论": "给出自然判读段落",
        "写明描述、分析和结论": "写明图表内容、关键现象和结论落点",
        "都有描述、分析和结论": "都有自然判读段落",
        "均需写明描述、分析和结论": "均需写明图表内容、关键现象和结论落点",
        "分别给出描述、分析和结论": "分别给出自然判读段落",
        "补充描述、分析和结论": "补充自然判读段落",
        "描述、分析和结论文字": "自然判读文字",
        "描述、分析和结论": "内容交代、结果判读和结论落点",
        "“描述、分析、结论”三部分文字": "自然判读文字",
        "“描述、分析、结论”": "自然判读",
        "描述/分析/结论": "自然判读",
        "描述部分": "",
        "分析部分": "",
        "结论部分": "",
        "输出 & 保存结果表、图形文件、评价指标和可复现实验日志，并在论文中给出内容交代、结果判读和结论落点。\\\\": "输出 & 保存结果表、图形文件、评价指标和可复现实验日志，并在论文中形成紧邻图表的自然判读段落。\\\\",
        "建模 & 根据子问题目标选择校正、变点检测、预测、分类、优化或风险评估模型，写出目标函数与约束。\\\\": "建模 & 根据子问题目标选择预测、统计学习、网络流、整数规划、仿真、分类或风险评估模型，写出目标函数与约束。\\\\",
        "物理一致性 & 检查趋势、阶段和预警是否符合边坡演化机理 & 若统计结果与物理规律冲突，应优先复核数据和特征。\\\\": "业务或工程一致性 & 检查趋势、规则、分类或决策是否符合题目约束和业务机理 & 若统计结果与业务约束冲突，应优先复核数据、特征和约束表达。\\\\",
        "该表把统计误差、分类效果、稳定性和物理一致性放入同一检验框架。不同检验并不互相替代，误差低但物理解释差的模型仍存在提交风险；最终论文应同时报告数值指标和机制解释，确保模型可靠性不是由单一分数支撑。": "该表把统计误差、分类效果、稳定性和业务一致性放入同一检验框架。不同检验并不互相替代，误差低但约束解释差的模型仍存在提交风险；最终论文应同时报告数值指标和业务约束解释，确保模型可靠性不是由单一分数支撑。",
        "表中流程用于约束代码实现顺序。其说明每一步的输入和输出；关注各环节如何降低数据噪声、模型偏差和信息泄漏风险；结论是该子问题的模型建立必须先形成可复现的数据接口，再进入正式求解。": "表中流程用于约束代码实现顺序，逐项明确每一步的输入、输出及其对数据噪声、模型偏差和信息泄漏风险的控制作用。由此可见，该子问题的模型建立必须先形成可复现的数据接口，再进入正式求解。",
    }
    for old, new in replacements.items():
        tex = tex.replace(old, new)
    tex = re.sub(
        r"\n\\subsection\{统一数学表达\}[\s\S]*?(?=\n\\subsection\{问题\s*\d+\s*模型建立\})",
        "\n",
        tex,
    )
    tex = re.sub(
        r"\n\\subsubsection\{(?:结果组织与判读|结果表格与图形解释)\}[\s\S]*?(?=\n(?:% BEGIN AUTO COMPUTED RESULTS|\\subsection\{问题\s*\d+\s*模型求解\}|\\section\{模型检验\}))",
        "\n",
        tex,
    )
    tex = re.sub(r"\n\\noindent\\textbf\{任务定位：\}.*?(?=\n)", "\n", tex)
    tex = re.sub(r"\n\\subsubsection\{模型思想与数学表达\}\s*", "\n", tex)
    tex = re.sub(r"\n\\subsubsection\{算法流程与输入输出\}\s*", "\n", tex)
    tex = re.sub(
        r"\\subsubsection\{问题\s*(\d+)\s*(?:计算结果回填|计算结果整合|模型求解结果)\}",
        r"\\subsubsection{问题 \1 模型求解结果}",
        tex,
    )
    label_patterns = [
        r"(?:表格|图形|结果)?描述[:：]\s*",
        r"(?:表格|图形|结果)?分析[:：]\s*",
        r"(?:表格|图形|结果)?结论[:：]\s*",
    ]
    for pattern in label_patterns:
        tex = re.sub(pattern, "", tex)
    canned_replacements = {
        "表中不预填未经计算的数值，只规定正式运行后必须填入的结果项目。这些项目把参数、指标和最终输出分开，能够避免把模型建立的原理与模型求解的结果混在一起。正式提交前应由程序将附件计算结果写入该表，并逐项复核是否支撑摘要和结论中的表述。":
            "表中不预填未经计算的数值，只规定正式运行后必须填入的结果项目。参数、评价指标和最终输出被分开列示，有助于避免把模型建立的原理与模型求解的结果混在一起；正式提交前应由附件数据计算得到相应数值，并逐项复核其是否支撑摘要和结论中的表述。",
        "该图用于展示该子问题最能支撑结论的曲线、对比或分布结构。正式结果应重点观察趋势转折、误差集中区域、类别混淆位置、特征贡献或风险等级跃迁，而不是只报告单个指标。若图形与表格指标一致，则可作为该子问题结论的主要证据；若二者不一致，需要回到数据清洗、参数选择或验证划分重新检查。":
            "该图用于展示该子问题最能支撑结论的曲线、对比或分布结构。正式结果应重点观察趋势转折、误差集中区域、类别混淆位置、特征贡献或风险等级跃迁，而不是只报告单个指标；若图形与表格指标一致，可作为该子问题结论的主要证据，若二者不一致，则需要回到数据清洗、参数选择或验证划分重新检查。",
        "该表把统计误差、分类效果、稳定性和物理一致性放入同一检验框架。不同检验并不互相替代，误差低但物理解释差的模型仍存在提交风险。最终论文应同时报告数值指标和机制解释，确保模型可靠性不是由单一分数支撑。":
            "该表把统计误差、分类效果、稳定性和物理一致性放入同一检验框架。不同检验并不互相替代，误差低但物理解释差的模型仍存在提交风险；最终论文应同时报告数值指标和机制解释，确保模型可靠性不是由单一分数支撑。",
    }
    for old, new in canned_replacements.items():
        tex = tex.replace(old, new)
    return sanitize_abstract_in_document(tex)


def replace_legacy_symbol_table(tex: str) -> str:
    pattern = re.compile(
        r"\\begin\{longtable\}\{p\{0\.18\\textwidth\}p\{0\.56\\textwidth\}p\{0\.18\\textwidth\}\}"
        r"[\s\S]*?\\caption\{主要符号及含义\}[\s\S]*?\\end\{longtable\}",
        flags=re.S,
    )

    def repl(match: re.Match[str]) -> str:
        block = match.group(0)
        if not any(term in block for term in ["表面位移", "爆破", "微震", "孔隙水压力", "边坡"]):
            return block
        return generic_symbol_table_latex()

    return pattern.sub(repl, tex)


def generic_symbol_table_latex() -> str:
    return r"""
\begin{longtable}{p{0.18\textwidth}p{0.56\textwidth}p{0.18\textwidth}}
\caption{主要符号及含义}\\
\toprule
符号 & 含义 & 单位或说明\\
\midrule
$t$ & 时间、日期、阶段或样本序号 & 按题目数据定义\\
$i,j$ & 起点、终点、类别或对象索引 & 按子问题定义\\
$v,u$ & 网络节点、候选位置或资源单元索引 & 按子问题定义\\
$x_t$ & 第 $t$ 个样本的特征向量 & 可标准化或保持原单位\\
$y_t$ & 观测目标、状态标签或决策输出 & 按子问题定义\\
$\hat y_t$ & 模型预测值或估计值 & 与 $y_t$ 同单位\\
$q_{ijt}$ & 对象 $(i,j)$ 在 $t$ 时刻的需求量、流量或任务量 & 按题目数据定义\\
$G_v,C_v$ & 节点或资源单元 $v$ 的容量、数量或处理能力 & 按题目数据定义\\
$z_{vm}$ & 节点 $v$ 选择资源、设备或方案 $m$ 的整数变量 & 非负整数\\
$\theta$ & 模型参数、阈值或权重集合 & 由训练、优化或规则确定\\
$\mathcal{L}$ & 损失函数、代价函数或优化目标 & 越小越优或按题设判定\\
\bottomrule
\end{longtable}
"""


def sanitize_abstract_in_document(tex: str) -> str:
    abstract_match = re.search(
        r"(\\noindent\\textbf\{摘要[：:]?\}\s*)([\s\S]*?)(?=\n\s*\\noindent\\textbf\{关键词[：:]?\})",
        tex,
    )
    if not abstract_match:
        return tex
    abstract = sanitize_abstract_text(abstract_match.group(2))
    return tex[: abstract_match.start(2)] + abstract + tex[abstract_match.end(2) :]


def latex_inline_text(text: str) -> str:
    return latex_paragraph(text).strip()


def normalize_path_text(text: str) -> str:
    text = re.sub(r"\s*/\s*", "/", text)
    text = re.sub(r"\$([A-Za-z0-9_.-]*_[A-Za-z0-9_.-]*)\$", r"\1", text)
    text = re.sub(r"\$((?:computed|run|main|paper|latex|support)[A-Za-z0-9_.-]*)\$", r"\1", text)
    return text


def local_result_prose(manifest: dict[str, Any], error: str) -> dict[str, Any]:
    per_problem = []
    for item in manifest.get("per_problem_results", []) or []:
        index = item.get("problem_index")
        per_problem.append(
            {
                "problem_index": index,
                "description": item.get("description") or f"问题{index}已形成计算结果。",
                "analysis": item.get("analysis") or "结果表和图形来自求解输出，可用于替换原论文中待计算的占位说明。",
                "conclusion": item.get("conclusion") or "该子问题的精确结论以结果清单和对应结果文件为准。",
            }
        )
    return {
        "abstract_result_sentence": f"本次求解生成了 {len(manifest.get('tables', []) or [])} 个结果表和 {len(manifest.get('figures', []) or [])} 张图，所有新增数值均可追溯。",
        "abstract_problem_results": [
            {"problem_index": index, "result": abstract_result_from_problem_item(index, item)}
            for index, item in [
                (safe_int(problem_item.get("problem_index")), problem_item)
                for problem_item in manifest.get("per_problem_results", []) or []
                if isinstance(problem_item, dict)
            ]
            if index
        ],
        "solving_intro": "由于 LLM 结果解释生成失败，系统使用本地规则概述计算结果；数值、表格和图片仍以结果清单为准。",
        "per_problem_commentary": per_problem,
        "validation_commentary": "本次求解保留了计算规范、脚本、运行日志和结果清单。LLM 解释生成异常为：" + error,
        "limitations": ["需要人工阅读 computed_summary.md，确认自动识别的目标字段与赛题语义一致。"],
    }


def normalize_solver_spec(spec: dict[str, Any], analysis: dict[str, Any]) -> dict[str, Any]:
    rec = analysis.get("recommended_problem", {}) or {}
    if not isinstance(spec, dict):
        spec = {}
    spec["final_problem_id"] = rec.get("id") or spec.get("final_problem_id") or ""
    spec["final_problem_title"] = rec.get("title") or spec.get("final_problem_title") or ""
    filters = spec.get("attachment_filters")
    if not isinstance(filters, list):
        filters = []
    required_filters = [str(rec.get("id") or ""), str(rec.get("title") or "")]
    spec["attachment_filters"] = list(dict.fromkeys([item for item in [*required_filters, *filters] if item]))
    tasks = rec.get("tasks") or []
    per_problem = spec.get("per_problem")
    if not isinstance(per_problem, list) or not per_problem:
        per_problem = []
        for index, task in enumerate(tasks or ["赛题数据计算"], 1):
            per_problem.append(
                {
                    "problem_index": index,
                    "goal": str(task),
                    "data_keywords": [f"Question {index}", f"问题{index}", f"附件{index}", f"Attachment {index}"],
                    "target_keywords": [],
                    "feature_keywords": [],
                    "model_family": "数据驱动统计建模",
                    "expected_outputs": ["结果表", "结果图", "评价指标"],
                }
            )
    normalized = []
    for index, item in enumerate(per_problem, 1):
        item = item if isinstance(item, dict) else {}
        item.setdefault("problem_index", index)
        item.setdefault("goal", "")
        item.setdefault("data_keywords", [f"Question {item['problem_index']}", f"问题{item['problem_index']}"])
        item.setdefault("target_keywords", [])
        item.setdefault("feature_keywords", [])
        item.setdefault("model_family", "数据驱动统计建模")
        item.setdefault("expected_outputs", ["结果表", "结果图", "评价指标"])
        normalized.append(item)
    spec["per_problem"] = normalized
    spec.setdefault("paper_result_focus", [])
    spec.setdefault("traceability_rules", ["所有论文数值必须来自 computed_manifest、结果表或图片。"])
    return spec


def compact_inventory(inventory: list[dict[str, Any]]) -> list[dict[str, Any]]:
    compact = []
    for item in inventory[:120]:
        compact.append(
            {
                "path": item.get("path"),
                "kind": item.get("kind"),
                "suffix": item.get("suffix"),
                "size": item.get("size"),
                "schema": item.get("schema"),
                "text_preview": item.get("text_preview"),
            }
        )
    return compact


def compact_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(manifest, dict):
        return {}
    compact = {
        "problem_id": manifest.get("problem_id"),
        "problem_title": manifest.get("problem_title"),
        "table_count": manifest.get("table_count"),
        "figure_count": len(manifest.get("figures", []) or []),
        "tables": [],
        "figures": [],
        "metrics": manifest.get("metrics", {}),
        "per_problem_results": [],
        "narrative_findings": manifest.get("narrative_findings", [])[:12],
        "limitations": manifest.get("limitations", [])[:12],
    }
    for table in manifest.get("tables", [])[:20]:
        if isinstance(table, dict):
            compact["tables"].append(
                {
                    "path": table.get("path"),
                    "title": table.get("title"),
                    "rows": table.get("rows"),
                    "cols": table.get("cols"),
                    "preview_records": table.get("preview_records", [])[:4],
                }
            )
        else:
            compact["tables"].append({"path": table})
    for figure in manifest.get("figures", [])[:20]:
        if isinstance(figure, dict):
            compact["figures"].append({k: figure.get(k) for k in ["path", "title", "description", "problem_index"]})
        else:
            compact["figures"].append({"path": figure})
    for item in manifest.get("per_problem_results", [])[:8]:
        compact["per_problem_results"].append(
            {
                "problem_index": item.get("problem_index"),
                "title": item.get("title"),
                "metrics": item.get("metrics"),
                "tables": item.get("tables", [])[:4],
                "figures": item.get("figures", [])[:4],
                "description": item.get("description"),
                "analysis": item.get("analysis"),
                "conclusion": item.get("conclusion"),
            }
        )
    return compact


def artifacts_from_run_result(result: dict[str, Any]) -> dict[str, str]:
    artifacts = {
        "computed_solver_log": result.get("log", ""),
        "computed_solution_status": STATUS_RELATIVE,
        "computed_manifest": result.get("manifest", ""),
        "computed_summary": result.get("summary", ""),
    }
    return {key: value for key, value in artifacts.items() if value}


def render_spec_markdown(payload: dict[str, Any]) -> str:
    spec = payload.get("spec") or {}
    lines = [
        "# LLM 代码求解规范",
        "",
        f"- 生成时间：{payload.get('generated_at')}",
        f"- 模型：{payload.get('settings', {}).get('model', '-')}",
        f"- 最终选题：{spec.get('final_problem_id', '-')} {spec.get('final_problem_title', '')}",
        "",
        "## 总体目标",
        str(spec.get("global_objective", "")),
        "",
        "## 子问题计算规范",
    ]
    for item in spec.get("per_problem", []) or []:
        lines.extend(
            [
                f"### 问题 {item.get('problem_index')}",
                f"- 目标：{item.get('goal', '')}",
                f"- 数据关键词：{'、'.join(str(x) for x in item.get('data_keywords', []))}",
                f"- 模型算法：{item.get('model_family', '')}",
                f"- 输出：{'、'.join(str(x) for x in item.get('expected_outputs', []))}",
                "",
            ]
        )
    return "\n".join(lines)


def render_result_prose_markdown(prose: dict[str, Any]) -> str:
    lines = [
        "# 计算结果论文回填说明",
        "",
        f"- 生成时间：{prose.get('generated_at')}",
        f"- 模型：{prose.get('settings', {}).get('model', '-')}",
        "",
        "## 摘要补充句",
        prose.get("abstract_result_sentence", ""),
        "",
        "## 求解总述",
        prose.get("solving_intro", ""),
        "",
        "## 分问题说明",
    ]
    for item in prose.get("per_problem_commentary", []) or []:
        lines.extend(
            [
                f"### 问题 {item.get('problem_index')}",
                f"- 描述：{item.get('description', '')}",
                f"- 分析：{item.get('analysis', '')}",
                f"- 结论：{item.get('conclusion', '')}",
                "",
            ]
        )
    lines.extend(["## 检验说明", prose.get("validation_commentary", ""), ""])
    return "\n".join(lines)


def extract_json_object(text: str) -> str:
    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text, flags=re.I)
    if fenced:
        return fenced.group(1).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end >= start:
        return text[start : end + 1]
    raise ValueError("LLM 未返回 JSON 对象")


def load_json_if_exists(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return load_json(path)
    except Exception:
        return {}


def read_text(path: Path, max_chars: int) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")[:max_chars]


def compact_cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.6g}"
    text = str(value)
    return text[:80]


def safe_int(value: Any) -> int:
    try:
        return int(str(value).strip())
    except Exception:
        return 0
