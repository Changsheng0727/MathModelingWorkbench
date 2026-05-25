from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from datetime import datetime
import time
from pathlib import Path
from typing import Any

from app.services.analyzer import build_workflow, choose_problem, clean_question, normalize_problem_id, score_problem
from app.services.llm_settings import get_llm_settings, get_private_llm_config
from app.services.llm_stream import active_llm_stream, bind_llm_stream
from app.services.model_research import search_model_references
from app.services.store import save_json


SYSTEM_PROMPT = """你是数学建模竞赛智能工作台中的大模型协作模块。
你必须遵循以下规则：
1. 所有数值结论必须来自输入中的分析、结果表、manifest 或日志，不得虚构。
2. 使用数学建模竞赛 workflow：赛题盘点、选题分析、数据检查、LLM 当场建模、结果检验、论文写作、提交审查；除非用户明确要求，不依赖本地基线模型或专项模型。
3. 论文建议必须遵循：问题重述和问题分析按子问题分别写；模型建立只写数学原理、目标函数、约束和算法，不写结果；模型求解按每个模型或问题分块；每个图表都要紧跟自然判读段落。
4. 输出中文 Markdown，结构清晰，给出可以直接执行的下一步建议。
"""

MODEL_ASSISTANT_PROGRESS_RELATIVE = "artifacts/model_assistant/progress.json"


def run_problem_llm_analysis(root: Path, analysis: dict[str, Any]) -> dict[str, str]:
    prompt = build_problem_prompt(analysis)
    return run_stage(
        root=root,
        stage="problem_analysis",
        prompt=prompt,
        md_relative="artifacts/llm_problem_analysis.md",
        json_relative="artifacts/llm_problem_analysis.json",
        title="LLM 赛题分析与题解工作流建议",
    )


def run_problem_structure_enhancement(
    root: Path,
    analysis: dict[str, Any],
    docs: list[dict[str, str]],
    inventory: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, str], dict[str, Any]]:
    """Ask the LLM to repair problem/task/data mapping before selection.

    This stage is intentionally non-fatal: upload analysis should still succeed
    with the rule-based parser if the LLM is unavailable, malformed, or too
    conservative.
    """
    settings = get_llm_settings()
    payload: dict[str, Any] = {
        "stage": "problem_structure",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "settings": {k: settings.get(k) for k in ["provider", "configured", "source", "masked_api_key", "base_url", "model"]},
        "success": False,
        "content": "",
        "parsed": {},
        "error": "",
    }
    md_relative = "artifacts/llm_problem_structure.md"
    json_relative = "artifacts/llm_problem_structure.json"
    enhanced = analysis
    try:
        prompt = build_problem_structure_prompt(analysis, docs, inventory)
        content = call_chat_completion(prompt, stream_label="LLM 读取题面和附件结构")
        parsed = extract_json_object(content)
        enhanced = merge_problem_structure(analysis, parsed, inventory, docs)
        payload.update(
            {
                "success": True,
                "content": content,
                "parsed": parsed,
                "enhancement_summary": {
                    "problem_count": len(enhanced.get("problems", []) or []),
                    "recommended_problem_id": (enhanced.get("recommended_problem") or {}).get("id"),
                    "source": "rules+llm",
                },
            }
        )
    except Exception as exc:
        payload["error"] = f"{type(exc).__name__}: {exc}"

    md_path = root / md_relative
    json_path = root / json_relative
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(render_problem_structure_markdown(payload), encoding="utf-8")
    save_json(json_path, payload)
    return enhanced, {"llm_problem_structure": md_relative, "llm_problem_structure_json": json_relative}, payload


def run_baseline_llm_review(root: Path, analysis: dict[str, Any], modeling_result: dict[str, Any]) -> dict[str, str]:
    prompt = build_baseline_prompt(analysis, modeling_result)
    return run_stage(
        root=root,
        stage="baseline_review",
        prompt=prompt,
        md_relative="artifacts/llm_baseline_review.md",
        json_relative="artifacts/llm_baseline_review.json",
        title="LLM 基线建模复盘与后续题解建议",
    )


def run_specialized_llm_review(root: Path, analysis: dict[str, Any], specialized_result: dict[str, Any]) -> dict[str, str]:
    prompt = build_specialized_prompt(analysis, specialized_result)
    return run_stage(
        root=root,
        stage="specialized_review",
        prompt=prompt,
        md_relative="artifacts/llm_specialized_review.md",
        json_relative="artifacts/llm_specialized_review.json",
        title="LLM 专项建模复盘与论文整合建议",
    )


def run_full_llm_refresh(root: Path) -> dict[str, str]:
    analysis_path = root / "artifacts" / "analysis.json"
    if not analysis_path.exists():
        raise FileNotFoundError("artifacts/analysis.json 不存在")
    analysis = json.loads(analysis_path.read_text(encoding="utf-8"))
    artifacts = run_problem_llm_analysis(root, analysis)

    baseline_status = load_json_if_exists(root / "artifacts" / "modeling_status.json")
    if baseline_status:
        artifacts.update(run_baseline_llm_review(root, analysis, baseline_status))

    specialized_status = load_json_if_exists(root / "artifacts" / "specialized_status.json")
    if specialized_status:
        artifacts.update(run_specialized_llm_review(root, analysis, specialized_status))
    return artifacts


def run_custom_model_assistance(root: Path, problem_ref: str, model_name: str, user_goal: str = "") -> dict[str, str]:
    with bind_llm_stream(root, "model_assistant", "模型辅助大模型直播", f"正在为 {model_name} 生成模型辅助方案。") as live_stream:
        try:
            artifacts = _run_custom_model_assistance(root, problem_ref, model_name, user_goal)
            live_stream.finish("success", "模型辅助方案生成完成。")
            return artifacts
        except Exception as exc:
            live_stream.finish("failed", f"{type(exc).__name__}: {exc}")
            raise


def _run_custom_model_assistance(root: Path, problem_ref: str, model_name: str, user_goal: str = "") -> dict[str, str]:
    started_at = datetime.now().isoformat(timespec="seconds")
    steps: list[dict[str, Any]] = []
    current_step: dict[str, Any] | None = None

    def begin_step(step_id: str, title: str, detail: str) -> dict[str, Any]:
        nonlocal current_step
        current_step = {
            "id": step_id,
            "title": title,
            "detail": detail,
            "status": "running",
            "started_at": datetime.now().isoformat(timespec="seconds"),
            "_started_seconds": time.time(),
        }
        write_model_assistant_progress(root, started_at, steps, current_step, status="running")
        return current_step

    def finish_step(status: str = "success", detail: str | None = None) -> None:
        nonlocal current_step
        if not current_step:
            return
        if detail:
            current_step["detail"] = detail
        current_step["status"] = status
        current_step["finished_at"] = datetime.now().isoformat(timespec="seconds")
        current_step["duration_seconds"] = round(time.time() - float(current_step.get("_started_seconds", time.time())), 2)
        current_step.pop("_started_seconds", None)
        steps.append(current_step)
        current_step = None
        final_status = "failed" if status == "failed" else "running"
        write_model_assistant_progress(root, started_at, steps, None, status=final_status)

    write_model_assistant_progress(root, started_at, steps, None, status="running")
    analysis_path = root / "artifacts" / "analysis.json"
    try:
        begin_step("load_context", "读取项目与赛题上下文", "正在读取赛题分析、已有结果清单和用户指定的模型目标。")
        if not analysis_path.exists():
            raise FileNotFoundError("artifacts/analysis.json 不存在")
        if not model_name.strip():
            raise ValueError("请填写模型或算法名称")
        analysis = json.loads(analysis_path.read_text(encoding="utf-8"))
        baseline = load_json_if_exists(root / "results" / "baseline_manifest.json")
        specialized = load_json_if_exists(root / "results" / "specialized_manifest.json")
        finish_step("success", "已读取赛题分析和可用的基线/专项结果。")

        begin_step("reference_search", "检索模型参考资料", f"正在为“{model_name}”检索可参考的模型原理、应用场景和资料链接。")
        search_sources = search_model_references(model_name)
        finish_step("success", f"检索完成：找到 {len(search_sources)} 条可用于辅助判断的参考资料。")

        begin_step("prompt_build", "构建模型辅助提示词", "正在把赛题上下文、已有 manifest、检索资料和用户目标组装为 LLM 输入。")
        prompt = build_model_assistant_prompt(
            analysis=analysis,
            problem_ref=problem_ref,
            model_name=model_name,
            user_goal=user_goal,
            search_sources=search_sources,
            baseline=baseline,
            specialized=specialized,
        )
        run_id = f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{slugify_for_path(model_name)}"
        md_relative = f"artifacts/model_assistant/{run_id}.md"
        json_relative = f"artifacts/model_assistant/{run_id}.json"
        finish_step("success", "提示词已生成，下一步调用 LLM 产出模型原理、伪代码和论文落点。")

        begin_step("llm_generation", "调用 LLM 生成模型辅助方案", "LLM 正在生成模型建立、模型求解、代码实现和论文写作建议。")
        artifacts = run_stage(
            root=root,
            stage="model_assistant",
            prompt=prompt,
            md_relative=md_relative,
            json_relative=json_relative,
            title="LLM 指定模型辅助解题报告",
            extra_payload={
                "request": {
                    "problem_ref": problem_ref,
                    "model_name": model_name,
                    "user_goal": user_goal,
                },
                "search_sources": search_sources,
            },
        )
        payload = load_json_if_exists(root / json_relative)
        if payload.get("success"):
            finish_step("success", "LLM 已生成模型辅助报告。")
        else:
            finish_step("warning", payload.get("error") or "LLM 未生成完整内容，请查看 JSON 记录。")

        begin_step("history_index", "写入模型辅助历史", "正在更新模型辅助历史索引，便于之后回看不同模型尝试。")
        artifacts.update(update_model_assistant_index(root, md_relative, json_relative))
        finish_step("success", "模型辅助报告和历史索引已写入生成文件。")
        final_status = "success" if payload.get("success") else "warning"
        write_model_assistant_progress(root, started_at, steps, None, status=final_status, artifacts=artifacts)
        return artifacts
    except Exception:
        if current_step:
            finish_step("failed", "执行失败，详细错误会返回到界面。")
        write_model_assistant_progress(root, started_at, steps, None, status="failed")
        raise


def write_model_assistant_progress(
    root: Path,
    started_at: str,
    steps: list[dict[str, Any]],
    current_step: dict[str, Any] | None,
    status: str,
    artifacts: dict[str, str] | None = None,
) -> None:
    total = 5
    completed = len(steps)
    progress = {
        "status": status,
        "started_at": started_at,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "current_step": compact_progress_step(current_step) if current_step else None,
        "steps": [compact_progress_step(step) for step in steps],
        "completed_steps": completed,
        "total_steps": total,
        "percent": min(100, round((completed + (0.35 if current_step else 0)) / total * 100)),
        "artifacts": artifacts or {},
    }
    path = root / MODEL_ASSISTANT_PROGRESS_RELATIVE
    path.parent.mkdir(parents=True, exist_ok=True)
    save_json(path, progress)


def compact_progress_step(step: dict[str, Any] | None) -> dict[str, Any] | None:
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
    }


def update_model_assistant_index(root: Path, md_relative: str, json_relative: str) -> dict[str, str]:
    payload = load_json_if_exists(root / json_relative)
    request = payload.get("request") or {}
    index_json = root / "artifacts" / "model_assistant" / "index.json"
    index_md = root / "artifacts" / "model_assistant" / "index.md"
    current = load_json_if_exists(index_json)
    entries = current.get("entries", []) if isinstance(current, dict) else []
    entry = {
        "generated_at": payload.get("generated_at"),
        "model_name": request.get("model_name"),
        "problem_ref": request.get("problem_ref"),
        "user_goal": request.get("user_goal"),
        "success": payload.get("success"),
        "source_count": len(payload.get("search_sources") or []),
        "markdown": md_relative,
        "json": json_relative,
    }
    entries = [item for item in entries if item.get("markdown") != md_relative]
    entries.insert(0, entry)
    entries = entries[:50]
    save_json(index_json, {"updated_at": datetime.now().isoformat(timespec="seconds"), "entries": entries})
    index_md.write_text(render_model_assistant_index(entries), encoding="utf-8")
    return {
        "llm_model_assistant": md_relative,
        "llm_model_assistant_json": json_relative,
        "llm_model_assistant_history": "artifacts/model_assistant/index.md",
        "llm_model_assistant_history_json": "artifacts/model_assistant/index.json",
    }


def render_model_assistant_index(entries: list[dict[str, Any]]) -> str:
    lines = ["# 模型辅助历史", ""]
    if not entries:
        lines.append("暂无模型辅助记录。")
        return "\n".join(lines)
    for index, item in enumerate(entries, 1):
        status = "成功" if item.get("success") else "未完成"
        lines.extend(
            [
                f"## {index}. {item.get('model_name') or '-'}",
                f"- 问题：{item.get('problem_ref') or '-'}",
                f"- 生成时间：{item.get('generated_at') or '-'}",
                f"- 状态：{status}",
                f"- 检索资料数：{item.get('source_count', 0)}",
                f"- 报告：`{item.get('markdown')}`",
                f"- JSON：`{item.get('json')}`",
                "",
            ]
        )
    return "\n".join(lines)


def slugify_for_path(text: str) -> str:
    slug = re.sub(r"[^\w\-\u4e00-\u9fff]+", "-", text, flags=re.UNICODE).strip("-")
    return (slug[:48] or "model").lower()


def run_stage(
    root: Path,
    stage: str,
    prompt: str,
    md_relative: str,
    json_relative: str,
    title: str,
    extra_payload: dict[str, Any] | None = None,
) -> dict[str, str]:
    settings = get_llm_settings()
    payload: dict[str, Any] = {
        "stage": stage,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "settings": {k: settings.get(k) for k in ["provider", "configured", "source", "masked_api_key", "base_url", "model"]},
        "success": False,
        "content": "",
        "error": "",
    }
    if extra_payload:
        payload.update(extra_payload)

    if not settings.get("configured"):
        raise ValueError("LLM 未启用：请先在左侧 AI 设置中填写 API Key。")
    try:
        payload["content"] = call_chat_completion(prompt, stream_label=title)
        payload["success"] = True
    except Exception as exc:
        payload["error"] = f"{type(exc).__name__}: {exc}"

    md_path = root / md_relative
    json_path = root / json_relative
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(render_stage_markdown(title, payload), encoding="utf-8")
    save_json(json_path, payload)
    return {
        stage_artifact_key(stage): md_relative,
        stage_artifact_key(stage) + "_json": json_relative,
    }


def call_chat_completion(
    prompt: str,
    max_tokens: int | None = None,
    attempts: int = 3,
    stream_label: str | None = None,
) -> str:
    config = get_private_llm_config()
    api_key = config["api_key"]
    if not api_key:
        raise ValueError("未配置 API Key")
    base_url = config["base_url"].rstrip("/")
    url = f"{base_url}/chat/completions"
    body: dict[str, Any] = {
        "model": config["model"],
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
    }
    if max_tokens:
        body["max_tokens"] = max_tokens
    last_error = ""
    attempts = max(1, attempts)
    live_stream = active_llm_stream()
    label = stream_label or infer_llm_stream_label(prompt)
    for attempt in range(1, attempts + 1):
        if live_stream:
            live_stream.begin_request(label, attempt, attempts, max_tokens)
        try:
            if live_stream:
                content = request_chat_completion_stream(url, api_key, body, live_stream)
            else:
                content = request_chat_completion_once(url, api_key, body)
            if not content.strip():
                raise RuntimeError("LLM API 返回内容为空")
            result = content.strip()
            if live_stream:
                live_stream.finish_request("success", f"已生成 {len(result)} 个字符。")
            return result
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            last_error = f"LLM API 请求失败：HTTP {exc.code} {detail[:800]}"
            if live_stream:
                live_stream.finish_request("failed", last_error)
            if exc.code in {400, 401, 403, 404}:
                raise RuntimeError(last_error) from exc
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            if live_stream:
                live_stream.finish_request("failed", last_error)
        if attempt < attempts:
            if live_stream:
                live_stream.emit("retry", label, f"{last_error}；准备重试。", status="warning")
            time.sleep(min(1.5 * attempt, 5.0))
    raise RuntimeError(last_error or "LLM API 请求失败")


def request_chat_completion_once(url: str, api_key: str, body: dict[str, Any]) -> str:
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=600) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return extract_completion_content(payload)


def request_chat_completion_stream(url: str, api_key: str, body: dict[str, Any], live_stream: Any) -> str:
    stream_body = dict(body)
    stream_body["stream"] = True
    data = json.dumps(stream_body, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=600) as response:
            content_type = response.headers.get("Content-Type", "").lower()
            if "event-stream" not in content_type:
                payload = json.loads(response.read().decode("utf-8"))
                content = extract_completion_content(payload)
                live_stream.append_delta(content)
                return content

            chunks: list[str] = []
            for raw_line in response:
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line or line.startswith(":") or not line.startswith("data:"):
                    continue
                data_text = line[5:].strip()
                if data_text == "[DONE]":
                    break
                try:
                    payload = json.loads(data_text)
                except json.JSONDecodeError:
                    continue
                delta = extract_stream_delta(payload)
                if delta:
                    chunks.append(delta)
                    live_stream.append_delta(delta)
            content = "".join(chunks)
            if not content.strip():
                raise RuntimeError("LLM API 流式响应为空")
            return content
    except urllib.error.HTTPError as exc:
        if exc.code in {400, 404, 405, 501}:
            detail = exc.read().decode("utf-8", errors="replace")
            live_stream.emit("stream_fallback", "流式响应不可用", f"接口未接受 stream=true，已退回普通响应。{detail[:160]}", status="warning")
            content = request_chat_completion_once(url, api_key, body)
            live_stream.append_delta(content)
            return content
        raise


def extract_completion_content(payload: dict[str, Any]) -> str:
    choices = payload.get("choices") or []
    if not choices:
        raise RuntimeError("LLM API 未返回 choices")
    first = choices[0] or {}
    message = first.get("message") or {}
    content = message.get("content")
    if content is None:
        content = first.get("text")
    return normalize_completion_content(content)


def extract_stream_delta(payload: dict[str, Any]) -> str:
    choices = payload.get("choices") or []
    if not choices:
        return ""
    first = choices[0] or {}
    delta = first.get("delta") or {}
    content = delta.get("content")
    if content is None:
        message = first.get("message") or {}
        content = message.get("content")
    if content is None:
        content = first.get("text")
    return normalize_completion_content(content)


def normalize_completion_content(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                value = item.get("text") or item.get("content") or ""
                if isinstance(value, str):
                    parts.append(value)
        return "".join(parts)
    return str(content)


def infer_llm_stream_label(prompt: str) -> str:
    text = re.sub(r"\s+", " ", (prompt or "").strip())
    if not text:
        return "大模型生成内容"
    for marker in ["。", "，", "：", ".", ":", "\n"]:
        if marker in text[:80]:
            text = text.split(marker, 1)[0]
            break
    return text[:48] or "大模型生成内容"


def build_problem_prompt(analysis: dict[str, Any]) -> str:
    compact = compact_analysis(analysis)
    return f"""请基于以下赛题解析结果，参与完成上传后的第一轮题解分析。

请输出：
1. 赛题整体判断：各题优劣、风险、数据条件和 AI/代码适配性。
2. 推荐选题是否合理，若不合理请给出修正意见。
3. 针对推荐题，按每个子问题给出建模思路、候选算法、需要生成的表格/图、验证方式。
4. 在不运行本地基线模型或专项模型的前提下，大模型应如何完成当场分析、模型选择、求解设计和论文落点。
5. 论文写作时每个章节应如何落地，尤其说明模型建立和模型求解的边界。
6. 给出下一步 workflow 清单。

输入分析 JSON：
```json
{json.dumps(compact, ensure_ascii=False, indent=2)}
```
"""


def build_problem_structure_prompt(
    analysis: dict[str, Any],
    docs: list[dict[str, str]],
    inventory: list[dict[str, Any]],
) -> str:
    context = {
        "rule_analysis": compact_analysis(analysis),
        "documents": compact_documents_for_structure(docs),
        "materials": compact_inventory_for_structure(inventory),
    }
    return f"""请读取下面的数学建模赛题材料上下文，修正软件自动识别出的候选题、子问题和附件数据映射。

你必须只根据输入中的题面文本、文件路径、数据表 schema 和样例判断，不要编造不存在的附件、题号、字段或数值。
如果某个题目的子问题在题面中没有明确写出，请不要硬凑；可以写出最接近的任务概括，并在 evidence 中说明依据。

请只输出一个 JSON 对象，不要输出 Markdown，不要使用代码围栏。JSON 结构如下：

{{
  "problems": [
    {{
      "id": "A",
      "title": "题目标题",
      "document": "题面文件相对路径",
      "tasks": ["问题1原文或准确改写", "问题2原文或准确改写"],
      "data_files": [
        {{"path": "附件相对路径", "reason": "为什么属于该题或该子问题"}}
      ],
      "model_types": ["预测", "优化"],
      "suggested_methods": ["时间序列预测", "整数规划"],
      "risk_items": ["需要外部数据源确认"],
      "evidence": "引用题面中的关键信号，简短说明"
    }}
  ],
  "recommended_problem_id": "B",
  "selection_reason": "推荐该题的依据，必须同时考虑数据条件、子问题清晰度、代码求解可行性和论文可写性",
  "notes": "对规则识别结果的修正说明"
}}

要求：
1. problems 必须覆盖输入材料中能识别到的 A/B/C/D/E 等候选题。
2. tasks 要尽量还原题面中的“问题1/问题2/...”或英文 Problem/Question 子问题，不要只写泛泛的“建模分析”。
3. data_files 只能使用 materials 中真实存在的 path；如果附件通用于全部题目，可以映射给相关题并说明。
4. recommended_problem_id 必须来自 problems 中的 id；如果无法判断，选择数据最清楚、子问题最完整的一题。
5. 不要给出未计算的具体结果数值。

输入上下文 JSON：
{json.dumps(context, ensure_ascii=False, indent=2)}
"""


def compact_documents_for_structure(docs: list[dict[str, str]], total_limit: int = 70000) -> list[dict[str, Any]]:
    ranked = sorted(docs, key=document_structure_rank, reverse=True)
    result: list[dict[str, Any]] = []
    remaining = total_limit
    for doc in ranked[:10]:
        if remaining <= 800:
            break
        text = re.sub(r"\s+", "\n", doc.get("text", "")).strip()
        per_doc_limit = min(18000, max(1200, remaining // max(1, min(4, len(ranked)))))
        snippet = text[:per_doc_limit]
        remaining -= len(snippet)
        result.append(
            {
                "path": doc.get("path", ""),
                "name": doc.get("name", ""),
                "char_count": len(doc.get("text", "")),
                "text": snippet,
            }
        )
    return result


def document_structure_rank(doc: dict[str, str]) -> int:
    name = doc.get("name", "")
    text = doc.get("text", "")
    score = min(len(text), 20000)
    if normalize_problem_id(name + "\n" + text[:800]):
        score += 30000
    if re.search(r"问题\s*[一二三四五六七八九十\d]+|Problem\s*\d+|Question\s*\d+", text, flags=re.IGNORECASE):
        score += 20000
    if any(word in name for word in ["格式", "承诺", "提交", "说明"]):
        score -= 15000
    if re.search(r"[\u4e00-\u9fff]", text[:3000]):
        score += 5000
    return score


def compact_inventory_for_structure(inventory: list[dict[str, Any]], limit: int = 160) -> list[dict[str, Any]]:
    result = []
    for item in inventory[:limit]:
        record = {
            "path": item.get("path"),
            "name": item.get("name"),
            "kind": item.get("kind"),
            "suffix": item.get("suffix"),
            "size": item.get("size"),
        }
        if item.get("kind") == "data":
            record["schema"] = compact_schema_for_structure(item.get("schema") or {})
        elif item.get("kind") == "document":
            record["text_preview"] = item.get("text_preview", "")
            record["char_count"] = item.get("char_count", 0)
        result.append(record)
    return result


def compact_schema_for_structure(schema: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(schema, dict):
        return {}
    if schema.get("type") == "csv":
        return {
            "type": "csv",
            "rows": schema.get("rows"),
            "cols": schema.get("cols"),
            "columns": (schema.get("columns") or [])[:30],
            "sample": (schema.get("sample") or [])[:2],
            "error": schema.get("error", ""),
        }
    if schema.get("type") == "excel":
        sheets = []
        for sheet in (schema.get("sheets") or [])[:12]:
            sheets.append(
                {
                    "name": sheet.get("name"),
                    "rows": sheet.get("rows"),
                    "cols": sheet.get("cols"),
                    "columns": (sheet.get("columns") or [])[:30],
                }
            )
        return {"type": "excel", "sheets": sheets, "error": schema.get("error", "")}
    return {key: schema.get(key) for key in ["type", "error"] if key in schema}


def extract_json_object(content: str) -> dict[str, Any]:
    text = (content or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            raise
        payload = json.loads(text[start : end + 1])
    if not isinstance(payload, dict):
        raise ValueError("LLM 结构化结果不是 JSON 对象")
    return payload


def merge_problem_structure(
    analysis: dict[str, Any],
    parsed: dict[str, Any],
    inventory: list[dict[str, Any]],
    docs: list[dict[str, str]],
) -> dict[str, Any]:
    llm_problems = parsed.get("problems")
    if not isinstance(llm_problems, list) or not llm_problems:
        raise ValueError("LLM 未返回 problems 列表")

    old_problems = {str(item.get("id", "")).upper(): item for item in analysis.get("problems", []) or []}
    path_index = {normalize_path_key(item.get("path", "")): item for item in inventory}
    format_notes = (analysis.get("contest_summary") or {}).get("format_notes", {})
    enhanced_problems: list[dict[str, Any]] = []
    seen: set[str] = set()

    for item in llm_problems:
        if not isinstance(item, dict):
            continue
        pid = normalize_llm_problem_id(item.get("id") or item.get("problem_id") or item.get("label"))
        if not pid:
            continue
        seen.add(pid)
        previous = dict(old_problems.get(pid) or {})
        tasks = normalize_llm_tasks(item.get("tasks") or item.get("subproblems") or item.get("questions"))
        data_files = match_llm_data_files(item.get("data_files") or item.get("attachments") or [], inventory, path_index)
        if not data_files and previous.get("data_files"):
            data_files = previous.get("data_files") or []
        problem = {
            **previous,
            "id": pid,
            "title": clean_inline_text(item.get("title") or previous.get("title") or f"{pid} 题", 260),
            "document": clean_inline_text(item.get("document") or previous.get("document") or infer_document_for_problem(pid, docs), 260),
            "tasks": tasks or previous.get("tasks", []),
            "data_files": data_files,
            "llm_enhanced": True,
            "llm_evidence": clean_inline_text(item.get("evidence") or item.get("selection_evidence") or "", 500),
            "llm_data_evidence": collect_llm_data_evidence(item.get("data_files") or item.get("attachments") or []),
        }
        problem["task_count"] = len(problem.get("tasks") or [])
        problem["data_file_count"] = len(problem.get("data_files") or [])
        scored = score_problem(problem, format_notes, source_text=problem_scoring_text(problem, item))
        problem.update(scored)
        problem["model_types"] = merge_unique(problem.get("model_types"), item.get("model_types"))
        problem["suggested_methods"] = merge_unique(problem.get("suggested_methods"), item.get("suggested_methods"))
        problem["risk_items"] = merge_unique(problem.get("risk_items"), item.get("risk_items"))
        enhanced_problems.append(problem)

    for pid, problem in old_problems.items():
        if pid and pid not in seen:
            enhanced_problems.append(problem)

    if not enhanced_problems:
        raise ValueError("LLM 返回的问题均无法匹配题号")

    recommended_id = normalize_llm_problem_id(parsed.get("recommended_problem_id") or parsed.get("recommended_id"))
    recommended = next((item for item in enhanced_problems if item.get("id") == recommended_id), None)
    if not recommended:
        recommended = choose_problem(enhanced_problems)

    enhanced = dict(analysis)
    enhanced["problems"] = enhanced_problems
    enhanced["rule_recommended_problem"] = analysis.get("recommended_problem", {})
    enhanced["llm_recommended_problem"] = {
        "id": recommended.get("id", ""),
        "title": recommended.get("title", ""),
        "selection_reason": clean_inline_text(parsed.get("selection_reason") or "", 800),
    }
    enhanced["recommended_problem"] = dict(recommended)
    enhanced["workflow"] = build_workflow(recommended, enhanced_problems)
    contest_summary = dict(enhanced.get("contest_summary") or {})
    contest_summary["analysis_source"] = "rules+llm"
    contest_summary["llm_structure_status"] = "success"
    contest_summary["llm_structure_notes"] = clean_inline_text(parsed.get("notes") or parsed.get("selection_reason") or "", 800)
    enhanced["contest_summary"] = contest_summary
    return enhanced


def normalize_llm_problem_id(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    pid = normalize_problem_id(text)
    if pid:
        return pid
    match = re.search(r"[A-EＡ-Ｅ]", text, flags=re.IGNORECASE)
    if not match:
        return ""
    return match.group(0).upper().translate(str.maketrans({"Ａ": "A", "Ｂ": "B", "Ｃ": "C", "Ｄ": "D", "Ｅ": "E"}))


def normalize_llm_tasks(value: Any) -> list[str]:
    if isinstance(value, str):
        raw_items = re.split(r"\n+|(?=问题\s*[一二三四五六七八九十\d]+[：:])|(?=(?:Problem|Question)\s*\d+[:.])", value)
    elif isinstance(value, list):
        raw_items = value
    else:
        raw_items = []
    tasks: list[str] = []
    for item in raw_items:
        if isinstance(item, dict):
            text = item.get("text") or item.get("task") or item.get("question") or item.get("content") or item.get("description") or ""
            prefix = item.get("id") or item.get("index") or item.get("label")
            if prefix and not str(text).strip().startswith(("问题", "Problem", "Question")):
                text = f"问题{prefix}：{text}"
        else:
            text = str(item or "")
        text = clean_question(text)
        if len(text) >= 8 and text not in tasks:
            tasks.append(text)
    return tasks[:10]


def match_llm_data_files(value: Any, inventory: list[dict[str, Any]], path_index: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    raw_items = value if isinstance(value, list) else [value] if value else []
    matched: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in raw_items:
        path = ""
        reason = ""
        if isinstance(item, dict):
            path = str(item.get("path") or item.get("file") or item.get("name") or "")
            reason = str(item.get("reason") or item.get("evidence") or "")
        else:
            path = str(item or "")
        record = find_inventory_record(path, inventory, path_index)
        if not record or record.get("kind") != "data":
            continue
        key = normalize_path_key(record.get("path", ""))
        if key in seen:
            continue
        copied = dict(record)
        if reason:
            copied["llm_mapping_reason"] = clean_inline_text(reason, 300)
        matched.append(copied)
        seen.add(key)
    return matched


def find_inventory_record(path: str, inventory: list[dict[str, Any]], path_index: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    key = normalize_path_key(path)
    if key in path_index:
        return path_index[key]
    name = Path(str(path)).name.lower()
    candidates = []
    for record in inventory:
        record_path = str(record.get("path", ""))
        record_name = str(record.get("name", ""))
        if name and name == record_name.lower():
            candidates.append(record)
        elif key and (key in normalize_path_key(record_path) or normalize_path_key(record_path) in key):
            candidates.append(record)
    return candidates[0] if candidates else None


def normalize_path_key(path: str) -> str:
    return str(path or "").replace("\\", "/").strip().lower()


def infer_document_for_problem(pid: str, docs: list[dict[str, str]]) -> str:
    for doc in docs:
        if normalize_problem_id((doc.get("name") or "") + "\n" + (doc.get("text") or "")[:600]) == pid:
            return doc.get("path", "")
    return docs[0].get("path", "") if docs else ""


def collect_llm_data_evidence(value: Any) -> list[dict[str, str]]:
    raw_items = value if isinstance(value, list) else [value] if value else []
    evidence = []
    for item in raw_items:
        if isinstance(item, dict):
            path = str(item.get("path") or item.get("file") or item.get("name") or "")
            reason = str(item.get("reason") or item.get("evidence") or "")
            if path or reason:
                evidence.append({"path": path, "reason": clean_inline_text(reason, 300)})
    return evidence[:20]


def problem_scoring_text(problem: dict[str, Any], llm_item: dict[str, Any]) -> str:
    parts = [
        str(problem.get("title", "")),
        " ".join(str(task) for task in problem.get("tasks", []) or []),
        " ".join(str(value) for value in llm_item.get("model_types", []) or []),
        " ".join(str(value) for value in llm_item.get("suggested_methods", []) or []),
        str(llm_item.get("evidence", "")),
    ]
    return "\n".join(parts)[:12000]


def merge_unique(primary: Any, secondary: Any) -> list[str]:
    values: list[str] = []
    for source in [primary, secondary]:
        if isinstance(source, str):
            candidates = re.split(r"[,，、/]\s*|\n+", source)
        elif isinstance(source, list):
            candidates = source
        else:
            candidates = []
        for item in candidates:
            text = clean_inline_text(item, 80)
            if text and text not in values:
                values.append(text)
    return values[:16]


def clean_inline_text(value: Any, limit: int = 300) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text[:limit]


def render_problem_structure_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# LLM 赛题结构增强",
        "",
        f"- 生成时间：{payload.get('generated_at', '-')}",
        f"- 模型：{(payload.get('settings') or {}).get('model', '-')}",
        f"- 状态：{'成功' if payload.get('success') else '未完成'}",
        "",
    ]
    if payload.get("success"):
        summary = payload.get("enhancement_summary") or {}
        lines.extend(
            [
                "## 增强结果",
                f"- 候选题数量：{summary.get('problem_count', '-')}",
                f"- 推荐题：{summary.get('recommended_problem_id', '-')}",
                "",
                "## LLM 原始结构化输出",
                "```json",
                json.dumps(payload.get("parsed") or {}, ensure_ascii=False, indent=2),
                "```",
            ]
        )
    else:
        lines.extend(["## 说明", payload.get("error") or "LLM 未生成可合并的结构化结果。"])
    lines.append("")
    return "\n".join(lines)


def build_baseline_prompt(analysis: dict[str, Any], modeling_result: dict[str, Any]) -> str:
    compact = compact_analysis(analysis)
    result = compact_result(modeling_result)
    return f"""基线建模脚本已经运行。请作为大模型协作模块，对基线结果做复盘并指导后续专项题解。

请输出：
1. 基线模型完成了哪些数据盘点、统计、图表或质量检查。
2. 这些结果对推荐题的每个子问题有什么帮助。
3. 哪些信息不足以支撑正式答案，需要专项模型继续完成。
4. 下一步专项模型应优先实现哪些算法、输出哪些表格和图片。
5. 哪些内容应写入论文的模型求解、模型检验和附录。

赛题分析：
```json
{json.dumps(compact, ensure_ascii=False, indent=2)}
```

基线运行结果：
```json
{json.dumps(result, ensure_ascii=False, indent=2)}
```
"""


def build_specialized_prompt(analysis: dict[str, Any], specialized_result: dict[str, Any]) -> str:
    compact = compact_analysis(analysis)
    result = compact_result(specialized_result)
    return f"""专项建模脚本已经运行。请作为大模型协作模块，对专项模型结果进行题解复盘和论文整合建议。

请输出：
1. 逐子问题说明当前专项结果可以回答什么。
2. 哪些表格和图片应放入模型求解部分，并为每个图表给出自然判读段落写法。
3. 模型检验应如何报告，包括误差、稳定性、敏感性和可追溯性。
4. 哪些结论可以写入摘要，哪些数值不能写入摘要。
5. 当前结果的不足与进一步增强建议。

赛题分析：
```json
{json.dumps(compact, ensure_ascii=False, indent=2)}
```

专项运行结果：
```json
{json.dumps(result, ensure_ascii=False, indent=2)}
```
"""


def build_model_assistant_prompt(
    analysis: dict[str, Any],
    problem_ref: str,
    model_name: str,
    user_goal: str,
    search_sources: list[dict[str, Any]],
    baseline: dict[str, Any],
    specialized: dict[str, Any],
) -> str:
    context = {
        "problem_ref": problem_ref,
        "model_name": model_name,
        "user_goal": user_goal,
        "analysis": compact_analysis(analysis),
        "baseline_manifest": compact_manifest(baseline),
        "specialized_manifest": compact_manifest(specialized),
        "search_sources": search_sources,
    }
    return f"""用户希望针对指定问题引入一个新的数学模型或算法。请基于赛题上下文、已有建模结果以及检索到的公开资料，生成一份可执行的模型辅助解题方案。

请严格遵守：
1. 不要编造数值结果、实验指标或不存在的文献。若检索资料不足，请明确说明“检索资料不足，需要人工补充文献”。
2. 模型建立部分只写数学原理、变量、目标函数、约束、算法流程和适用条件，不写尚未计算的结果。
3. 模型求解建议必须能落到代码、数据表、图和验证指标上。
4. 若该模型并不适合用户指定的问题，请直接指出不适配原因，并给出更合适的替代模型。

请输出中文 Markdown，结构必须包含：

## 1. 指定任务理解
- 说明用户指定的问题、模型名称和期望目标。

## 2. 检索资料归纳
- 概括检索到的模型来源、核心思想和常见应用。
- 列出可引用的资料标题与链接；如果检索为空，说明为空。

## 3. 模型原理与数学形式
- 给出变量定义、关键假设、目标函数/损失函数/状态转移/约束条件。
- 给出该模型的适用前提和不适用场景。

## 4. 与本赛题该问题的适配方案
- 说明输入数据来自哪些附件或中间结果。
- 说明该模型如何回答指定子问题。
- 说明与现有基线模型或专项模型的关系，是替代、补充还是融合。

## 5. 算法流程与伪代码
- 给出可复现的步骤，包含数据预处理、参数估计、训练/求解、预测/优化、验证。

## 6. 代码实现建议
- 给出 Python 实现模块、推荐库、输入输出文件、应生成的表格和图片。
- 说明哪些结果可以写入摘要，哪些必须等程序运行后再写。

## 7. 论文写作落点
- 给出“模型建立”“模型求解”“模型检验”中可直接采用的写作框架。
- 提醒图表需要自然判读段落，不能只放表图。

## 8. 下一步执行清单
- 用简短 checklist 给出下一步要写的代码、要生成的结果和要补充的论文段落。

输入上下文 JSON：
```json
{json.dumps(context, ensure_ascii=False, indent=2)}
```
"""


def compact_analysis(analysis: dict[str, Any]) -> dict[str, Any]:
    problems = []
    for problem in analysis.get("problems", []):
        problems.append(
            {
                "id": problem.get("id"),
                "title": problem.get("title"),
                "task_count": problem.get("task_count"),
                "tasks": problem.get("tasks", [])[:8],
                "data_file_count": problem.get("data_file_count"),
                "model_types": problem.get("model_types", []),
                "fit_score": problem.get("fit_score"),
                "risk_items": problem.get("risk_items", []),
                "suggested_methods": problem.get("suggested_methods", []),
                "method_routes": problem.get("method_routes", []),
            }
        )
    return {
        "contest_summary": analysis.get("contest_summary", {}),
        "recommended_problem": analysis.get("recommended_problem", {}),
        "problems": problems,
        "workflow": analysis.get("workflow", []),
    }


def compact_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    if not manifest:
        return {}
    return {
        "problem_id": manifest.get("problem_id"),
        "problem_title": manifest.get("problem_title"),
        "table_count": manifest.get("table_count"),
        "tables_overview": (manifest.get("tables_overview") or [])[:8],
        "specialized_models": manifest.get("specialized_models", []),
        "tables": (manifest.get("tables") or [])[:12],
        "figures": (manifest.get("figures") or [])[:12],
        "notes": (manifest.get("notes") or [])[:8],
        "summary_markdown": manifest.get("summary_markdown"),
    }


def compact_result(result: dict[str, Any]) -> dict[str, Any]:
    outputs = result.get("outputs") or {}
    return {
        "success": result.get("success"),
        "returncode": result.get("returncode"),
        "executor": result.get("executor"),
        "manifest": result.get("manifest"),
        "outputs": {
            "problem_id": outputs.get("problem_id"),
            "problem_title": outputs.get("problem_title"),
            "table_count": outputs.get("table_count"),
            "tables_overview": (outputs.get("tables_overview") or [])[:8],
            "specialized_models": outputs.get("specialized_models", []),
            "tables": outputs.get("tables", [])[:12],
            "figures": outputs.get("figures", [])[:12],
            "notes": outputs.get("notes", []),
            "summary_markdown": outputs.get("summary_markdown"),
        },
    }


def render_stage_markdown(title: str, payload: dict[str, Any]) -> str:
    lines = [
        f"# {title}",
        "",
        f"- 生成时间：{payload['generated_at']}",
        f"- 模型：{payload['settings'].get('model', '-')}",
        f"- Base URL：{payload['settings'].get('base_url', '-')}",
        f"- API Key：{payload['settings'].get('masked_api_key') or '未配置'}",
        f"- 状态：{'成功' if payload['success'] else '未完成'}",
        "",
    ]
    if payload["success"]:
        lines.append(payload["content"])
    else:
        lines.extend(["## 说明", payload["error"] or "LLM 分析未生成。"])
    sources = payload.get("search_sources") or []
    if sources:
        lines.extend(["", "## 检索参考", ""])
        for index, item in enumerate(sources, 1):
            authors = "，".join(item.get("authors") or [])
            meta = "，".join(str(part) for part in [authors, item.get("venue"), item.get("year")] if part)
            url = item.get("url") or ""
            lines.append(f"{index}. {item.get('title', 'Untitled')}。{meta}。{url}")
    lines.append("")
    return "\n".join(lines)


def stage_artifact_key(stage: str) -> str:
    return {
        "problem_analysis": "llm_problem_analysis",
        "baseline_review": "llm_baseline_review",
        "specialized_review": "llm_specialized_review",
        "model_assistant": "llm_model_assistant",
    }.get(stage, f"llm_{stage}")


def load_json_if_exists(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
