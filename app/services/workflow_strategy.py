from __future__ import annotations

from typing import Any


DEFAULT_WORKFLOW_STRATEGY = "balanced"
WORKFLOW_STRATEGY_ORDER = ("balanced", "stable", "turbo")


WORKFLOW_STRATEGIES: dict[str, dict[str, Any]] = {
    "stable": {
        "id": "stable",
        "label": "稳妥",
        "summary": "优先提高生成成功率，使用更保守的算法、更多校验和更多自动修复轮次。",
        "max_repairs": 4,
        "script_validation_attempts": 4,
        "repair_validation_attempts": 3,
        "requires_parallel": False,
        "prompt": (
            "Workflow strategy: stable. Prefer simple reproducible baselines, defensive parsing, "
            "small intermediate checkpoints, and explicit validation over advanced but fragile algorithms. "
            "Avoid optional dependencies unless a guarded fallback is present."
        ),
    },
    "balanced": {
        "id": "balanced",
        "label": "均衡",
        "summary": "兼顾速度和成功率，适合默认的一键解题与论文生成流程。",
        "max_repairs": 3,
        "script_validation_attempts": 3,
        "repair_validation_attempts": 2,
        "requires_parallel": False,
        "prompt": (
            "Workflow strategy: balanced. Build a robust baseline first, then add one stronger "
            "task-appropriate method when data supports it. Keep runtime moderate and outputs complete."
        ),
    },
    "turbo": {
        "id": "turbo",
        "label": "极速",
        "summary": "优先提速，要求生成脚本并行读取附件、并行处理独立子问题，并复用中间结果。",
        "max_repairs": 3,
        "script_validation_attempts": 4,
        "repair_validation_attempts": 3,
        "requires_parallel": True,
        "prompt": (
            "Workflow strategy: turbo. When safe, use concurrent.futures.ThreadPoolExecutor for "
            "independent file parsing, sheet profiling, validation tables, and independent subproblem "
            "branches. Cache parsed schemas/results in memory within the run, avoid repeated full-file "
            "reads, and keep deterministic ordering when writing manifest entries. Do not use subprocess, "
            "network, shell commands, multiprocessing, or project-external paths. Local validation rejects "
            "turbo scripts unless a ThreadPoolExecutor is actually used with executor.submit or executor.map."
        ),
    },
}


def normalize_workflow_strategy(value: Any) -> str:
    if isinstance(value, dict):
        value = value.get("id") or value.get("workflow_strategy")
    strategy = str(value or "").strip().lower()
    if strategy in WORKFLOW_STRATEGIES:
        return strategy
    return DEFAULT_WORKFLOW_STRATEGY


def get_workflow_strategy(value: Any = None) -> dict[str, Any]:
    strategy_id = normalize_workflow_strategy(value)
    return dict(WORKFLOW_STRATEGIES[strategy_id])


def workflow_strategy_options() -> list[dict[str, Any]]:
    return [
        {
            "id": item["id"],
            "label": item["label"],
            "summary": item["summary"],
        }
        for item in (WORKFLOW_STRATEGIES[strategy_id] for strategy_id in WORKFLOW_STRATEGY_ORDER)
    ]


def public_workflow_strategy(value: Any = None) -> dict[str, Any]:
    strategy = get_workflow_strategy(value)
    return {
        "id": strategy["id"],
        "label": strategy["label"],
        "summary": strategy["summary"],
        "max_repairs": strategy["max_repairs"],
        "script_validation_attempts": strategy["script_validation_attempts"],
        "repair_validation_attempts": strategy["repair_validation_attempts"],
        "requires_parallel": strategy["requires_parallel"],
    }
