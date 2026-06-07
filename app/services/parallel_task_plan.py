from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Any

from app.services.attachment_profile import load_or_build_attachment_profile
from app.services.store import load_json, save_json
from app.services.workflow_strategy import get_workflow_strategy, public_workflow_strategy


PARALLEL_TASK_PLAN_RELATIVE = "artifacts/parallel_task_plan.json"
PARALLEL_TASK_PLAN_MD_RELATIVE = "artifacts/parallel_task_plan.md"


def build_parallel_task_plan(
    root: Path,
    analysis: dict[str, Any],
    spec: dict[str, Any] | None = None,
    workflow_strategy: dict[str, Any] | str | None = None,
) -> dict[str, str]:
    strategy = get_workflow_strategy(workflow_strategy)
    attachment_profile = load_or_build_attachment_profile(root, analysis)
    spec = spec if isinstance(spec, dict) else load_existing_spec(root)
    files = [item for item in attachment_profile.get("files", []) if isinstance(item, dict)]
    data_files = [item for item in files if item.get("kind") == "data"]
    document_files = [item for item in files if item.get("kind") == "document"]
    problems = problem_items(analysis, spec)
    max_workers = suggested_max_workers(len(data_files), len(document_files), len(problems), strategy)

    tasks: list[dict[str, Any]] = []
    groups: list[dict[str, Any]] = []

    profile_task = {
        "id": "profile_attachments",
        "title": "并发附件画像缓存",
        "group": "preprocess",
        "parallel_safe": True,
        "depends_on": [],
        "inputs": ["raw/*"],
        "outputs": ["artifacts/attachment_profile.json"],
        "suggested_worker_pool": "ThreadPoolExecutor",
        "reason": "读取附件 schema 和文档预览互不依赖，可并发执行并复用缓存。",
    }
    tasks.append(profile_task)
    groups.append(
        {
            "id": "preprocess",
            "title": "附件预处理",
            "task_ids": [profile_task["id"]],
            "parallel_safe": True,
            "recommended_max_workers": max(1, min(max_workers, max(1, len(files)))),
        }
    )

    data_task_ids = []
    for index, item in enumerate(data_files[:40], 1):
        task_id = f"load_data_{index}"
        data_task_ids.append(task_id)
        tasks.append(
            {
                "id": task_id,
                "title": f"读取数据表：{item.get('path')}",
                "group": "data_ingestion",
                "parallel_safe": True,
                "depends_on": ["profile_attachments"],
                "inputs": [item.get("path")],
                "outputs": [f"cached dataframe/schema for {item.get('path')}"],
                "suggested_worker_pool": "ThreadPoolExecutor",
                "reason": "不同 CSV/Excel 文件或工作表的读取和字段复核可以独立进行。",
                "schema_summary": summarize_schema(item.get("schema")),
            }
        )
    if data_task_ids:
        groups.append(
            {
                "id": "data_ingestion",
                "title": "数据表读取与字段复核",
                "task_ids": data_task_ids,
                "parallel_safe": True,
                "recommended_max_workers": max(2, min(max_workers, len(data_task_ids))),
            }
        )

    doc_task_ids = []
    for index, item in enumerate(document_files[:30], 1):
        task_id = f"parse_document_{index}"
        doc_task_ids.append(task_id)
        tasks.append(
            {
                "id": task_id,
                "title": f"读取文档：{item.get('path')}",
                "group": "document_parse",
                "parallel_safe": True,
                "depends_on": ["profile_attachments"],
                "inputs": [item.get("path")],
                "outputs": [f"compact text signals for {item.get('path')}"],
                "suggested_worker_pool": "ThreadPoolExecutor",
                "reason": "题面、说明文档和格式附件的文本提取互不依赖。",
                "keyword_signals": (item.get("keywords") or [])[:16],
            }
        )
    if doc_task_ids:
        groups.append(
            {
                "id": "document_parse",
                "title": "文档文本提取",
                "task_ids": doc_task_ids,
                "parallel_safe": True,
                "recommended_max_workers": max(2, min(max_workers, len(doc_task_ids))),
            }
        )

    source_dependencies = data_task_ids + doc_task_ids or ["profile_attachments"]
    solve_task_ids = []
    validation_task_ids = []
    for problem in problems:
        index = int(problem.get("problem_index") or len(solve_task_ids) + 1)
        solve_id = f"solve_problem_{index}"
        validate_id = f"validate_problem_{index}"
        solve_task_ids.append(solve_id)
        validation_task_ids.append(validate_id)
        tasks.append(
            {
                "id": solve_id,
                "title": f"求解问题 {index}",
                "group": "subproblem_solve",
                "parallel_safe": True,
                "depends_on": source_dependencies[:12],
                "inputs": ["solver_spec.per_problem", "attachment_profile"],
                "outputs": [f"per_problem_results[{index}]", f"tables/figures for problem {index}"],
                "suggested_worker_pool": "ThreadPoolExecutor",
                "reason": "各子问题在完成共享附件读取后通常可独立运行基线、候选模型和结果导出。",
                "goal": problem.get("goal") or problem.get("title") or "",
                "expected_outputs": problem.get("expected_outputs", []),
            }
        )
        tasks.append(
            {
                "id": validate_id,
                "title": f"检验问题 {index}",
                "group": "validation_export",
                "parallel_safe": True,
                "depends_on": [solve_id],
                "inputs": [f"per_problem_results[{index}]"],
                "outputs": [f"validation tables/figures for problem {index}"],
                "suggested_worker_pool": "ThreadPoolExecutor",
                "reason": "各子问题的误差、敏感性、约束和鲁棒性检验可独立生成。",
            }
        )
    if solve_task_ids:
        groups.append(
            {
                "id": "subproblem_solve",
                "title": "分问题并行求解",
                "task_ids": solve_task_ids,
                "parallel_safe": True,
                "recommended_max_workers": max(2, min(max_workers, len(solve_task_ids))),
            }
        )
        groups.append(
            {
                "id": "validation_export",
                "title": "分问题检验与图表导出",
                "task_ids": validation_task_ids,
                "parallel_safe": True,
                "recommended_max_workers": max(2, min(max_workers, len(validation_task_ids))),
            }
        )

    final_dependencies = validation_task_ids or solve_task_ids or source_dependencies
    tasks.append(
        {
            "id": "freeze_and_manifest",
            "title": "冻结结果并写 manifest",
            "group": "finalize",
            "parallel_safe": False,
            "depends_on": final_dependencies[:40],
            "inputs": ["all per_problem_results", "all validation outputs"],
            "outputs": ["results/computed_manifest.json", "results/computed_summary.md", "results/frozen_numbers.json"],
            "suggested_worker_pool": "single deterministic writer",
            "reason": "最终 manifest、摘要和冻结数值必须按确定顺序合并，避免并发写文件造成结果漂移。",
        }
    )
    groups.append(
        {
            "id": "finalize",
            "title": "结果冻结与确定性写入",
            "task_ids": ["freeze_and_manifest"],
            "parallel_safe": False,
            "recommended_max_workers": 1,
        }
    )

    payload = {
        "stage": "parallel_task_plan",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "success": True,
        "workflow_strategy": public_workflow_strategy(strategy["id"]),
        "suggested_max_workers": max_workers,
        "planned_task_count": len(tasks),
        "parallel_group_count": sum(1 for group in groups if group.get("parallel_safe")),
        "implementation_contract": {
            "executor": "concurrent.futures.ThreadPoolExecutor",
            "forbidden": ["multiprocessing", "ProcessPoolExecutor", "subprocess", "network"],
            "dispatch_patterns": ["executor.submit", "executor.map", "as_completed"],
            "deterministic_order": "Collect future results into dictionaries/lists, then sort by problem_index/path before writing manifest files.",
            "safe_write_rule": "Only final deterministic writer should create results/computed_manifest.json and frozen_numbers.json.",
        },
        "groups": groups,
        "tasks": tasks,
    }
    save_json(root / PARALLEL_TASK_PLAN_RELATIVE, payload)
    (root / PARALLEL_TASK_PLAN_MD_RELATIVE).write_text(render_parallel_task_plan_markdown(payload), encoding="utf-8")
    return {
        "parallel_task_plan": PARALLEL_TASK_PLAN_MD_RELATIVE,
        "parallel_task_plan_json": PARALLEL_TASK_PLAN_RELATIVE,
    }


def compact_parallel_task_plan_for_prompt(
    root: Path,
    analysis: dict[str, Any],
    spec: dict[str, Any] | None = None,
    workflow_strategy: dict[str, Any] | str | None = None,
) -> dict[str, Any]:
    build_parallel_task_plan(root, analysis, spec, workflow_strategy)
    payload = load_json_if_exists(root / PARALLEL_TASK_PLAN_RELATIVE)
    if not payload:
        return {}
    compact_tasks = []
    for task in payload.get("tasks", [])[:80]:
        if not isinstance(task, dict):
            continue
        compact_tasks.append(
            {
                "id": task.get("id"),
                "group": task.get("group"),
                "parallel_safe": task.get("parallel_safe"),
                "depends_on": task.get("depends_on", [])[:12],
                "outputs": task.get("outputs", [])[:6],
                "reason": task.get("reason", ""),
            }
        )
    return {
        "suggested_max_workers": payload.get("suggested_max_workers"),
        "planned_task_count": payload.get("planned_task_count"),
        "parallel_group_count": payload.get("parallel_group_count"),
        "implementation_contract": payload.get("implementation_contract", {}),
        "groups": payload.get("groups", [])[:12],
        "tasks": compact_tasks,
    }


def render_parallel_task_plan_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# 并行求解任务计划",
        "",
        f"- 生成时间：{payload.get('generated_at', '-')}",
        f"- 求解策略：{(payload.get('workflow_strategy') or {}).get('label', '-')} / {(payload.get('workflow_strategy') or {}).get('id', '-')}",
        f"- 建议线程数：{payload.get('suggested_max_workers', '-')}",
        f"- 任务数：{payload.get('planned_task_count', 0)}",
        f"- 可并行任务组：{payload.get('parallel_group_count', 0)}",
        "",
        "## 并行组",
        "",
        "| 组 | 可并行 | 建议线程 | 任务数 |",
        "|---|---|---:|---:|",
    ]
    for group in payload.get("groups", []) or []:
        if not isinstance(group, dict):
            continue
        lines.append(
            f"| {group.get('title') or group.get('id')} | {'是' if group.get('parallel_safe') else '否'} | "
            f"{group.get('recommended_max_workers', '-')} | {len(group.get('task_ids', []) or [])} |"
        )
    lines.extend(["", "## 任务明细", "", "| 任务 | 分组 | 依赖 | 输出 |", "|---|---|---|---|"])
    for task in payload.get("tasks", []) or []:
        if not isinstance(task, dict):
            continue
        deps = "、".join(str(item) for item in (task.get("depends_on") or [])[:8]) or "-"
        outputs = "、".join(str(item) for item in (task.get("outputs") or [])[:5]) or "-"
        lines.append(f"| {task.get('title') or task.get('id')} | {task.get('group', '-')} | {deps} | {outputs} |")
    contract = payload.get("implementation_contract") if isinstance(payload.get("implementation_contract"), dict) else {}
    lines.extend(
        [
            "",
            "## 脚本实现约束",
            f"- 并发执行器：{contract.get('executor', '-')}",
            f"- 派发模式：{'、'.join(contract.get('dispatch_patterns', []) or [])}",
            f"- 确定性写入：{contract.get('deterministic_order', '-')}",
            f"- 安全写入：{contract.get('safe_write_rule', '-')}",
        ]
    )
    return "\n".join(lines) + "\n"


def problem_items(analysis: dict[str, Any], spec: dict[str, Any]) -> list[dict[str, Any]]:
    items = [item for item in spec.get("per_problem", []) or [] if isinstance(item, dict)]
    if items:
        return items
    rec = analysis.get("selected_problem") or analysis.get("recommended_problem") or {}
    tasks = rec.get("tasks") if isinstance(rec, dict) else []
    if isinstance(tasks, list) and tasks:
        return [
            {
                "problem_index": index,
                "goal": str(task),
                "expected_outputs": ["结果表", "结果图", "评价指标"],
            }
            for index, task in enumerate(tasks, 1)
        ]
    return [{"problem_index": 1, "goal": "完成赛题核心计算", "expected_outputs": ["结果表", "结果图", "评价指标"]}]


def suggested_max_workers(data_count: int, doc_count: int, problem_count: int, strategy: dict[str, Any]) -> int:
    cpu = os.cpu_count() or 4
    workload = max(data_count + doc_count, problem_count, 1)
    if strategy.get("id") == "turbo":
        return max(2, min(12, cpu * 2, workload + 2))
    if strategy.get("id") == "stable":
        return max(2, min(6, cpu, workload + 1))
    return max(2, min(8, cpu + 1, workload + 1))


def summarize_schema(schema: Any) -> str:
    if not isinstance(schema, dict):
        return ""
    if schema.get("error"):
        return str(schema.get("error"))[:200]
    if schema.get("type") == "csv":
        columns = schema.get("columns") or []
        return f"{schema.get('rows', '-')} 行，{schema.get('cols', '-')} 列；字段 {', '.join(str(c) for c in columns[:8])}"
    if schema.get("type") == "excel":
        sheets = schema.get("sheets") or []
        names = [str(sheet.get("name")) for sheet in sheets[:8] if isinstance(sheet, dict)]
        return f"{len(sheets)} 个工作表：{', '.join(names)}"
    return str(schema.get("type") or "")


def load_existing_spec(root: Path) -> dict[str, Any]:
    payload = load_json_if_exists(root / "artifacts" / "computed_solver_spec.json")
    if not isinstance(payload, dict):
        return {}
    spec = payload.get("spec") if isinstance(payload.get("spec"), dict) else payload
    return spec if isinstance(spec, dict) else {}


def load_json_if_exists(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = load_json(path)
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}
