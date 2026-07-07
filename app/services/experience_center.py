from __future__ import annotations

from datetime import datetime
from typing import Any

from app.services.action_catalog import enrich_action
from app.services.trust_center import needs_repair


def build_experience_center(
    projects: list[dict[str, Any]],
    auto_jobs: dict[str, Any],
    delivery_jobs: dict[str, Any],
    capacity_settings: dict[str, Any],
    llm_settings: dict[str, Any],
) -> dict[str, Any]:
    """Product-facing UX scorecard derived from current local state."""
    projects = projects or []
    total = len(projects)
    analyzed = sum(1 for item in projects if item.get("analysis_available"))
    running = sum(1 for item in projects if item.get("auto_workflow_status") in {"running", "queued", "cancel_requested"})
    solved = sum(1 for item in projects if item.get("auto_workflow_status") == "success")
    failed = sum(1 for item in projects if item.get("auto_workflow_status") == "failed")
    deliverable = sum(1 for item in projects if delivery_is_ready(item))
    packaged = sum(1 for item in projects if item.get("delivery_package_status") == "success" or item.get("delivery_package_sha256"))
    repair_backlog = sum(1 for item in projects if needs_repair(item))
    configured = bool(llm_settings.get("configured"))

    queue = int(auto_jobs.get("queued_count") or 0) + int(delivery_jobs.get("queued_count") or 0)
    active = int(auto_jobs.get("running_count") or 0) + int(delivery_jobs.get("running_count") or 0)
    auto_capacity = int(auto_jobs.get("capacity") or capacity_settings.get("auto_workflow_workers") or 0)
    delivery_capacity = int(delivery_jobs.get("capacity") or capacity_settings.get("delivery_batch_job_workers") or 0)
    package_workers = int(capacity_settings.get("delivery_package_workers") or 0)

    dimensions = [
        dimension(
            "setup",
            "接入体验",
            100 if configured else 42,
            "大模型接口已配置，可以直接进入自动求解。" if configured else "尚未配置大模型接口，用户第一步会卡在运行前。",
        ),
        dimension(
            "speed",
            "解题速度",
            speed_score(auto_capacity, delivery_capacity, package_workers, queue),
            f"自动流程槽 {auto_capacity or 0}，批量任务槽 {delivery_capacity or 0}，打包线程 {package_workers or 0}，队列 {queue}。",
        ),
        dimension(
            "recovery",
            "自动修复",
            recovery_score(total, failed, repair_backlog),
            f"{failed} 个项目失败，{repair_backlog} 个项目存在修复/续跑动作。",
        ),
        dimension(
            "clarity",
            "过程可见",
            clarity_score(total, analyzed, running, solved),
            f"{analyzed}/{total or 0} 个项目完成赛题分析，{running} 个项目正在或等待运行。",
        ),
        dimension(
            "delivery",
            "交付闭环",
            delivery_score(deliverable, packaged),
            f"{deliverable} 个项目已就绪，{packaged} 个项目已有正式交付包。",
        ),
    ]
    score = round(sum(item["score"] for item in dimensions) / len(dimensions)) if dimensions else 0
    status = "success" if score >= 82 else "warning" if score >= 58 else "failed"
    actions = recommended_actions(
        configured=configured,
        analyzed=analyzed,
        failed=failed,
        repair_backlog=repair_backlog,
        deliverable=deliverable,
        packaged=packaged,
        queue=queue,
        auto_capacity=auto_capacity,
        total=total,
    )
    principles = [
        {
            "label": "Context first",
            "detail": "优先展示当前项目状态、失败原因和下一步动作，而不是泛泛介绍功能。",
        },
        {
            "label": "Operational beauty",
            "detail": "界面密度服务竞赛工作流：上传、求解、修复、交付都应能一眼定位。",
        },
        {
            "label": "Recovery by design",
            "detail": "失败状态必须给证据、动作和续跑入口，不能只显示报错文本。",
        },
    ]
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "status": status,
        "score": score,
        "label": experience_label(score),
        "summary": experience_summary(score, total, queue, failed),
        "onboarding": onboarding_hint(total, configured),
        "dimensions": dimensions,
        "actions": actions,
        "principles": principles,
        "signals": {
            "projects": total,
            "analyzed": analyzed,
            "running": running,
            "solved": solved,
            "failed": failed,
            "repair_backlog": repair_backlog,
            "deliverable": deliverable,
            "packaged": packaged,
            "queue": queue,
            "active": active,
            "auto_capacity": auto_capacity,
            "delivery_capacity": delivery_capacity,
            "package_workers": package_workers,
            "workflow_strategy": llm_settings.get("workflow_strategy", "balanced"),
        },
    }


def dimension(id_: str, label: str, score: int, detail: str) -> dict[str, Any]:
    bounded = max(0, min(100, int(score)))
    return {
        "id": id_,
        "label": label,
        "score": bounded,
        "status": "success" if bounded >= 82 else "warning" if bounded >= 58 else "failed",
        "detail": detail,
    }


def speed_score(auto_capacity: int, delivery_capacity: int, package_workers: int, queue: int) -> int:
    base = 46 + min(28, auto_capacity * 7) + min(12, delivery_capacity * 4) + min(10, package_workers * 2)
    if queue > auto_capacity + delivery_capacity:
        base -= min(20, (queue - auto_capacity - delivery_capacity) * 4)
    return max(20, min(100, base))


def recovery_score(total: int, failed: int, repair_backlog: int) -> int:
    if not total:
        return 68
    penalty = min(36, failed * 10 + repair_backlog * 5)
    return max(34, 92 - penalty)


def clarity_score(total: int, analyzed: int, running: int, solved: int) -> int:
    if not total:
        return 62
    ratio = analyzed / max(1, total)
    activity_bonus = min(10, running * 3 + solved * 2)
    return max(36, min(100, round(50 + ratio * 38 + activity_bonus)))


def delivery_score(deliverable: int, packaged: int) -> int:
    if not deliverable and not packaged:
        return 58
    ratio = packaged / max(1, deliverable)
    return max(42, min(100, round(56 + ratio * 38 + min(6, packaged))))


def delivery_is_ready(project: dict[str, Any]) -> bool:
    return str(project.get("delivery_readiness_status") or "") in {"deliverable", "review", "ready", "success"}


def recommended_actions(
    *,
    configured: bool,
    analyzed: int,
    failed: int,
    repair_backlog: int,
    deliverable: int,
    packaged: int,
    queue: int,
    auto_capacity: int,
    total: int,
) -> list[dict[str, str]]:
    actions: list[dict[str, str]] = []
    if not configured:
        actions.append(action("test_llm", "配置并测试大模型", "先完成接口测试，减少用户第一次自动求解失败。", "warning"))
    if queue > max(1, auto_capacity):
        actions.append(action("autotune_capacity", "自动调优并发", "根据当前排队压力提升自动流程槽和批量任务槽。", "primary"))
    if failed or repair_backlog:
        actions.append(action("repair_campaign", "运行修复行动", "刷新失败诊断、重建修复简报，并把可续跑项目重新入队。", "danger"))
    if analyzed and total and analyzed >= max(1, total // 2):
        actions.append(action("select_analyzed", "选择已分析项目", "快速选择可直接进入自动流程的项目，适合批量求解。", "primary"))
    if deliverable > packaged:
        actions.append(action("batch_packages", "批量生成交付包", "把已就绪论文、结果、审查报告和支撑材料打成正式交付包。", "primary"))
    if not actions:
        actions.append(action("refresh_all", "刷新产品状态", "重新计算体验雷达、任务中心、交付质检和交付状态。", "neutral"))
    return actions[:4]


def action(id_: str, label: str, detail: str, tone: str) -> dict[str, Any]:
    row = {"id": id_, "label": label, "detail": detail, "tone": tone}
    return enrich_action(row)


def onboarding_hint(total: int, configured: bool) -> dict[str, Any]:
    if not total and not configured:
        return {
            "status": "warning",
            "step_index": 1,
            "title": "先配置接口，再上传赛题",
            "detail": "自动求解依赖可用的大模型接口。先保存并测试 API Key，再上传赛题包会少走弯路。",
            "outcome": "接口连通后，再上传赛题即可进入自动分析和推荐选题。",
            "actions": [
                {**action("focus_llm", "填写接口", "保存 API Key 并测试连接。", "warning"), "primary": True},
                action("focus_upload", "选择赛题", "上传赛题压缩包或文件夹。", "neutral"),
            ],
        }
    if not total:
        return {
            "status": "pending",
            "step_index": 1,
            "title": "上传赛题材料",
            "detail": "选择赛题压缩包或文件夹，系统会自动识别题目、附件和推荐选题。",
            "outcome": "上传完成后，会显示选题建议、附件清单和下一步按钮。",
            "actions": [{**action("focus_upload", "选择赛题", "上传赛题压缩包或文件夹。", "primary"), "primary": True}],
        }
    return {
        "status": "pending",
        "step_index": 1,
        "title": "打开一个项目继续",
        "detail": "项目列表已按优先级排序。先打开最上方项目，再按页面提示继续生成或修复。",
        "outcome": "打开项目后，顶部和引导面板会给出当前最应该做的一步。",
        "actions": [
            {**action("focus_projects", "查看项目", "定位到项目列表。", "primary"), "primary": True},
            action("focus_upload", "上传新赛题", "上传新的赛题材料。", "neutral"),
        ],
    }


def experience_label(score: int) -> str:
    if score >= 88:
        return "产品体验优秀"
    if score >= 74:
        return "产品体验可发布"
    if score >= 58:
        return "产品体验需打磨"
    return "产品体验有阻塞"


def experience_summary(score: int, total: int, queue: int, failed: int) -> str:
    if not total:
        return "还没有项目样本，建议先上传赛题并跑通一条完整解题链路。"
    if failed:
        return f"当前 {failed} 个项目需要修复；先清理失败链路，体验分会明显提升。"
    if queue:
        return f"当前有 {queue} 个后台任务排队；可以通过自动调优并发提升吞吐。"
    if score >= 82:
        return "上传、求解、修复和交付链路比较完整，适合继续做打包发布与传播素材。"
    return "核心链路已经具备，但还需要提升接入、速度、修复或交付闭环中的短板。"
