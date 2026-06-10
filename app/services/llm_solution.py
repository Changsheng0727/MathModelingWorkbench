from __future__ import annotations

import json
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from app.services.backend_skills import render_backend_skill_context, render_model_method_routes, render_standard_paper_rules
from app.services.llm_assistant import call_chat_completion, compact_analysis
from app.services.llm_settings import get_llm_settings
from app.services.paper import latex_escape
from app.services.store import save_json


def require_llm_configured() -> dict[str, Any]:
    settings = get_llm_settings()
    if not settings.get("configured"):
        raise ValueError("请先在左侧 AI 设置中填写 API Key；LLM 自动解题与代码求解流程不提供本地降级模式。")
    return settings


def run_llm_only_solution(root: Path, analysis: dict[str, Any], paper_options: dict[str, Any] | None = None) -> dict[str, str]:
    settings = require_llm_configured()
    paper_options = paper_options or {}

    sections = generate_llm_sections(analysis, paper_options)
    solution = render_solution_markdown(sections)
    solution_payload = {
        "stage": "llm_full_solution",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "settings": public_settings(settings),
        "success": True,
        "content": solution,
        "sections": sections,
        "paper_options": paper_options,
    }
    solution_md = root / "artifacts" / "llm_full_solution.md"
    solution_json = root / "artifacts" / "llm_full_solution.json"
    solution_md.parent.mkdir(parents=True, exist_ok=True)
    solution_md.write_text(render_stage_markdown("LLM 全流程题解与论文写作方案", solution_payload), encoding="utf-8")
    save_json(solution_json, solution_payload)

    tex = render_latex_from_llm_sections(analysis, sections)

    paper_dir = root / "paper"
    paper_dir.mkdir(parents=True, exist_ok=True)
    main_tex = paper_dir / "main.tex"
    backup = paper_dir / "main_before_llm_only.tex"
    if main_tex.exists() and not backup.exists():
        shutil.copy2(main_tex, backup)
    llm_tex = paper_dir / "main_llm.tex"
    llm_tex.write_text(tex, encoding="utf-8")
    main_tex.write_text(tex, encoding="utf-8")

    paper_payload = {
        "stage": "llm_paper_latex",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "settings": public_settings(settings),
        "success": True,
        "content": "LaTeX 文档由本地程序根据 LLM 分段题解内容拼接生成，以避免单次超长响应被上游接口断开。",
        "latex_extracted": True,
    }
    paper_md = root / "artifacts" / "llm_paper_latex.md"
    paper_json = root / "artifacts" / "llm_paper_latex.json"
    paper_md.write_text(render_stage_markdown("LLM LaTeX 论文生成记录", paper_payload), encoding="utf-8")
    save_json(paper_json, paper_payload)

    return {
        "llm_full_solution": "artifacts/llm_full_solution.md",
        "llm_full_solution_json": "artifacts/llm_full_solution.json",
        "llm_paper_latex": "artifacts/llm_paper_latex.md",
        "llm_paper_latex_json": "artifacts/llm_paper_latex.json",
        "paper_main": "paper/main.tex",
        "paper_llm": "paper/main_llm.tex",
    }


def run_llm_planning_solution(root: Path, analysis: dict[str, Any], paper_options: dict[str, Any] | None = None) -> dict[str, str]:
    """Generate only modeling/code-solver planning context; do not write paper/main.tex."""
    settings = require_llm_configured()
    paper_options = paper_options or {}
    sections = generate_llm_planning_sections(analysis, paper_options)
    solution = render_solution_markdown(sections)
    solution_payload = {
        "stage": "llm_planning_solution",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "settings": public_settings(settings),
        "success": True,
        "content": solution,
        "sections": sections,
        "paper_options": paper_options,
        "paper_written": False,
        "note": "本阶段只完成选题、子问题、模型链、代码求解和图表产出规划；不生成 paper/main.tex。",
    }
    solution_md = root / "artifacts" / "llm_full_solution.md"
    solution_json = root / "artifacts" / "llm_full_solution.json"
    solution_md.parent.mkdir(parents=True, exist_ok=True)
    solution_md.write_text(render_stage_markdown("LLM 建模与代码求解规划", solution_payload), encoding="utf-8")
    save_json(solution_json, solution_payload)
    return {
        "llm_full_solution": "artifacts/llm_full_solution.md",
        "llm_full_solution_json": "artifacts/llm_full_solution.json",
    }


def generate_llm_planning_sections(analysis: dict[str, Any], paper_options: dict[str, Any]) -> dict[str, Any]:
    backend_skill_context = render_backend_skill_context(max_chars=12000)
    standard_paper_rules = render_standard_paper_rules()
    context = {
        "analysis": compact_analysis(analysis),
        "inventory": compact_inventory(analysis.get("inventory", [])),
        "paper_options": paper_options,
        "backend_skill_context": backend_skill_context,
        "standard_paper_rules": standard_paper_rules,
        "model_method_routes": render_model_method_routes(max_chars=6000),
    }
    rec = analysis.get("recommended_problem", {}) or {}
    selection = call_json_response(
        f"""你是数学建模竞赛自动求解流程的总控。当前阶段只允许做选题确认、子问题拆解、模型链和代码求解规划，不允许撰写论文正文、摘要或结论。

用户已经确认本次求解使用 {rec.get("id", "-")} 题：{rec.get("title", "")}。不得自行改选其他题目。

只输出 JSON，不要 Markdown，不要解释。字段：
{{
  "final_problem_id": "最终选择题号",
  "final_problem_title": "最终选择题名",
  "reason": "选择理由，500字以内",
  "tasks": ["按子问题列出任务"],
  "model_chain": ["按顺序列出拟采用的模型或算法"],
  "data_needs": ["需要从附件中读取或计算的关键数据"],
  "risk_control": ["不能编造数值、需要复核的风险点"]
}}

要求：final_problem_id 和 final_problem_title 必须与用户确认的题目一致；每个子问题都要能进入后续代码求解；如果缺少可计算数值，只写需由数据计算得到。

输入 JSON：
```json
{json.dumps(context, ensure_ascii=False, indent=2)}
```""",
        max_tokens=1600,
        stream_label="生成建模求解规划：选题与任务拆解",
    )
    selection["final_problem_id"] = rec.get("id") or selection.get("final_problem_id")
    selection["final_problem_title"] = rec.get("title") or selection.get("final_problem_title")
    model = call_json_response(
        f"""请继续为自动代码求解生成建模规划。当前阶段仍然不允许写论文正文、摘要、结论或图表分析段落；只写给代码求解器使用的规划。

只输出 JSON，不要 Markdown，不要解释。字段：
{{
  "model_building": "按子问题说明数学模型、变量、目标函数、约束和算法思路；不写结果",
  "solving": "按子问题说明代码如何读取数据、计算结果、生成表格和绘制图片",
  "validation": "按子问题说明必须由代码跑出的检验表、检验图和评价指标",
  "per_problem_plan": [
    {{
      "problem_index": 1,
      "goal": "本问最终要解决的问题",
      "data_mapping": ["需要读取的附件、表、字段或文本参数"],
      "model_family": "模型或算法",
      "baseline_model": "先跑通的基线或PoC",
      "candidate_models": ["候选模型"],
      "expected_tables": ["必须输出的结果表或检验表"],
      "expected_figures": ["必须绘制的结果图或检验图"],
      "validation_outputs": ["误差、敏感性、约束可行性或稳定性检查"],
      "completion_criteria": "什么情况下才算本问解完"
    }}
  ]
}}

硬性要求：
1. 每个子问题都必须有 expected_tables 和 expected_figures，后续软件会在所有子问题都产出表格和图片后才开始写论文。
2. 先设计简单可解释的 PoC/基线，再给候选模型；不能只给黑箱模型名。
3. 不要编造精确数值，所有数值等待代码从附件计算。

题型-模型路由：
```text
{render_model_method_routes(max_chars=6000)}
```

最终选题 JSON：
```json
{json.dumps(selection, ensure_ascii=False, indent=2)}
```

赛题上下文 JSON：
```json
{json.dumps(context, ensure_ascii=False, indent=2)}
```""",
        max_tokens=3000,
        stream_label="生成建模求解规划：模型与图表产出",
    )
    return {"selection": selection, "model": model, "paper_options": paper_options, "planning_only": True}


def generate_llm_sections(analysis: dict[str, Any], paper_options: dict[str, Any]) -> dict[str, Any]:
    backend_skill_context = render_backend_skill_context(max_chars=14000)
    standard_paper_rules = render_standard_paper_rules()
    context = {
        "analysis": compact_analysis(analysis),
        "inventory": compact_inventory(analysis.get("inventory", [])),
        "paper_options": paper_options,
        "backend_skill_context": backend_skill_context,
        "standard_paper_rules": standard_paper_rules,
        "model_method_routes": render_model_method_routes(max_chars=6000),
    }
    rec = analysis.get("recommended_problem", {}) or {}
    target_pages = paper_options.get("target_body_pages")
    target_note = f"正文目标不少于 {target_pages} 页。" if target_pages else "未设置正文页数下限。"
    selection = call_json_response(
        f"""你是数学建模竞赛选题与建模总控。用户已经确认本次求解使用 {rec.get("id", "-")} 题：{rec.get("title", "")}。请围绕该题完成选题理由、任务拆解和建模总控，不得自行改选其他题目。

只输出 JSON，不要 Markdown，不要解释。字段：
{{
  "final_problem_id": "最终选择题号",
  "final_problem_title": "最终选择题名",
  "reason": "选择理由，500字以内",
  "tasks": ["按子问题列出任务"],
  "model_chain": ["按顺序列出拟采用的模型或算法"],
  "data_needs": ["需要从附件中读取或计算的关键数据"],
  "risk_control": ["不能编造数值、需要复核的风险点"]
}}

要求：final_problem_id 和 final_problem_title 必须与用户确认的题目一致；一切由大模型当场分析，不运行基线模型或专项脚本；如果缺少可计算数值，只写需由数据计算得到。必须遵守输入中的 standard_paper_rules。整体输出不超过 1200 个汉字。
{target_note}

输入 JSON：
```json
{json.dumps(context, ensure_ascii=False, indent=2)}
```""",
        max_tokens=1600,
    )
    selection["final_problem_id"] = rec.get("id") or selection.get("final_problem_id")
    selection["final_problem_title"] = rec.get("title") or selection.get("final_problem_title")
    front = call_json_response(
        f"""请为数学建模论文生成前半部分内容。只输出 JSON，不要 Markdown，不要解释。

字段：
{{
  "restatement": "问题重述，必须按每个子问题分别叙述",
  "problem_analysis": "问题分析，必须按每个子问题分别叙述，说明模型类别、难点和路线",
  "assumptions": "模型假设，分点说明",
  "symbols": "符号说明，用文字列出主要符号、含义和单位"
}}

约束：不要编造结果数值；内容应服务于最终选择题。必须按 standard_paper_rules 分问题组织。整体输出不超过 2200 个汉字。

最终选题 JSON：
```json
{json.dumps(selection, ensure_ascii=False, indent=2)}
```

赛题上下文 JSON：
```json
{json.dumps(context, ensure_ascii=False, indent=2)}
```""",
        max_tokens=2600,
    )
    model = call_json_response(
        f"""请为数学建模论文生成模型主体内容。只输出 JSON，不要 Markdown，不要解释。

字段：
{{
  "model_building": "模型建立。只写数学原理、变量、目标函数、约束、算法流程和伪代码，不写结果",
  "solving": "模型求解。按每个子问题或模型分别写，说明如何用数据计算结果、应生成哪些表格和图片，以及每个图表后应如何用自然论文段落完成内容交代、结果判读和结论落点",
  "validation": "模型检验。写稳定性、敏感性、误差指标、交叉验证或对照验证方案"
}}

硬性要求：不能声称已经得到未提供的精确数值；模型建立只写数学模型的原理、公式、目标函数、约束、算法和伪代码，不写结果；模型求解必须按子问题组织图表，并在图表附近用自然学术段落完成内容交代、结果判读和结论落点，不要使用带冒号的固定图表解读标签；公式既要允许段内内联公式，也要使用独占一行的显式公式，内联公式用 $...$，所有独立公式必须用 $$...$$ 包裹并使用标准 LaTeX 语法，显式公式会自动编号；每个子问题都要覆盖。整体输出不超过 3200 个汉字。
标准论文规则：
```text
{standard_paper_rules}
```

最终选题 JSON：
```json
{json.dumps(selection, ensure_ascii=False, indent=2)}
```

前半部分 JSON：
```json
{json.dumps(front, ensure_ascii=False, indent=2)}
```""",
        max_tokens=3600,
    )
    tail = call_json_response(
        f"""请为数学建模论文生成摘要和收尾内容。只输出 JSON，不要 Markdown，不要解释。

字段：
{{
  "abstract": "摘要。必须严格采用：先写总体目标和具体方法链；再逐句使用“针对问题X，考虑……因素，建立……模型，采用……算法，得到……结果。”；最后写可靠性检验和结论。不要编造精确数值；不得出现A题/B题/C题等题号字母，不得出现具体附件文件名、路径或Sheet名",
  "keywords": ["关键词1", "关键词2", "关键词3", "关键词4"],
  "evaluation": "模型评价与推广，说明优点、不足、改进和推广场景",
  "references": ["参考文献条目，尽量使用通用可靠文献或赛题说明，不要编造具体不存在论文"],
  "appendix": "附录说明，包括数据、程序、AI工具使用说明和复现材料"
}}
整体输出不超过 1600 个汉字。必须遵守 standard_paper_rules，尤其是摘要固定句式、结果位置、图表/附录边界。摘要只能写问题主题、模型、算法和关键结果，不能写具体文件名或工作表名。
标准论文规则：
```text
{standard_paper_rules}
```

最终选题 JSON：
```json
{json.dumps(selection, ensure_ascii=False, indent=2)}
```

模型主体 JSON：
```json
{json.dumps(model, ensure_ascii=False, indent=2)}
```""",
        max_tokens=2000,
    )
    sections: dict[str, Any] = {"selection": selection, "front": front, "model": model, "tail": tail, "paper_options": paper_options}
    if safe_int(target_pages) >= 20:
        sections["expanded"] = build_expanded_sections_with_fallback(
            context,
            selection,
            front,
            model,
            tail,
            safe_int(target_pages),
        )
    paper_title = generate_paper_title(context, sections)
    title_text = sanitize_paper_title(paper_title.get("paper_title") or paper_title.get("title"))
    if title_text:
        paper_title["paper_title"] = title_text
        selection["paper_title"] = title_text
        selection["paper_title_reason"] = inline_text(paper_title.get("title_reason") or paper_title.get("reason"))
        if isinstance(paper_title.get("alternative_titles"), list):
            selection["paper_title_candidates"] = [
                item for item in (sanitize_paper_title(value) for value in paper_title.get("alternative_titles", [])) if item
            ][:3]
    sections["paper_title"] = paper_title
    sections["selection"] = selection
    return sections


def generate_paper_title(context: dict[str, Any], sections: dict[str, Any]) -> dict[str, Any]:
    selection = sections.get("selection") or {}
    front = sections.get("front") or {}
    model = sections.get("model") or {}
    tail = sections.get("tail") or {}
    expanded = sections.get("expanded") or {}
    title_context = {
        "final_problem_id": selection.get("final_problem_id"),
        "final_problem_title": selection.get("final_problem_title"),
        "tasks": normalize_tasks(selection),
        "model_chain": selection.get("model_chain", []),
        "keywords": tail.get("keywords", []),
        "abstract": clip_for_title(
            text_field(expanded.get("abstract_detail", {}), "abstract") or tail.get("abstract") or "",
            1400,
        ),
        "problem_analysis": clip_for_title(
            text_field(expanded.get("front_detail", {}), "analysis_detail") or front.get("problem_analysis") or "",
            1000,
        ),
        "model_building": clip_for_title(
            join_texts(text_field(expanded.get("model_overview", {}), "content"), model.get("model_building") or ""),
            1600,
        ),
        "model_solving": clip_for_title(model.get("solving") or "", 1200),
        "paper_options": context.get("paper_options", {}),
    }
    payload = call_json_response(
        f"""请根据最终选题、解题方法链和已经生成的论文内容，为数学建模论文拟定正式标题。

只输出 JSON，不要 Markdown，不要解释。字段：
{{
  "paper_title": "正式论文标题",
  "title_reason": "为什么该标题能概括问题对象、核心方法和文章内容，100字以内",
  "alternative_titles": ["备选标题1", "备选标题2"]
}}

标题要求：
1. 必须由当前解题方法和文章内容决定，不能只照抄赛题原名。
2. 应体现问题对象和核心模型链，例如预测、优化、分类、评价、网络流、整数规划、时序模型、多源融合等；没有在内容中使用的方法不得写入标题。
3. 中文标题以 14-32 个汉字为宜，避免“数学建模论文”“本文”“研究报告”等空泛表述。
4. 不要出现 A题/B题/C题 等题号字母，不要出现附件文件名、路径、Sheet 名或未计算出的精确数值。
5. 标题应适合放在 LaTeX 正文首页居中标题处。

输入 JSON：
```json
{json.dumps(title_context, ensure_ascii=False, indent=2)}
```""",
        max_tokens=900,
    )
    return payload if isinstance(payload, dict) else {}


def sanitize_paper_title(value: Any) -> str:
    text = inline_text(value)
    if not text:
        return ""
    text = re.sub(r"^#+\s*", "", text)
    text = text.strip(" `\"'“”‘’《》")
    text = re.sub(r"(?<!问题)[A-H]\s*题[：:、，,]?", "", text)
    text = re.sub(r"[\w\u4e00-\u9fff（）()《》\-—·]+?\.(?:xlsx|xls|csv|txt|pdf|docx)(?:::?Sheet\d+)?", "附件数据", text, flags=re.I)
    text = re.sub(r"\s+", "", text)
    if text in {"数学建模论文", "所选赛题", "正式论文标题"}:
        return ""
    return text[:60]


def clip_for_title(value: Any, max_chars: int) -> str:
    text = inline_text(value)
    return text[:max_chars]


def build_expanded_sections_with_fallback(
    context: dict[str, Any],
    selection: dict[str, Any],
    front: dict[str, Any],
    model: dict[str, Any],
    tail: dict[str, Any],
    target_pages: int,
) -> dict[str, Any]:
    try:
        expanded = generate_expanded_sections(context, selection, front, model, tail, target_pages)
        if expanded_has_minimum_content(expanded):
            expanded["expansion_mode"] = "llm_standard_paper_expansion"
            return expanded
        fallback = build_local_expanded_sections(selection, front, model, tail, target_pages)
        fallback["expansion_mode"] = "local_standard_paper_fallback"
        fallback["llm_expansion_warning"] = "LLM 长正文扩写返回内容不足，已使用内置标准论文扩写规则兜底。"
        return fallback
    except Exception as exc:
        fallback = build_local_expanded_sections(selection, front, model, tail, target_pages)
        fallback["expansion_mode"] = "local_standard_paper_fallback"
        fallback["llm_expansion_error"] = f"{type(exc).__name__}: {exc}"
        return fallback


def expanded_has_minimum_content(expanded: dict[str, Any]) -> bool:
    front_detail = expanded.get("front_detail", {})
    data_feature = expanded.get("data_feature", {})
    model_overview = expanded.get("model_overview", {})
    per_problem = expanded.get("per_problem", [])
    validation_detail = expanded.get("validation_detail", {})
    if not text_field(front_detail, "restatement_detail") or not text_field(model_overview, "content"):
        return False
    if len(text_field(data_feature, "content")) < 400 or len(text_field(validation_detail, "content")) < 400:
        return False
    if not per_problem:
        return False
    for item in per_problem:
        if len(text_field(item, "model_building")) < 300 or len(text_field(item, "solving")) < 300:
            return False
    return True


def build_local_expanded_sections(
    selection: dict[str, Any],
    front: dict[str, Any],
    model: dict[str, Any],
    tail: dict[str, Any],
    target_pages: int,
) -> dict[str, Any]:
    tasks = normalize_tasks(selection)
    per_problem = []
    for index, task in enumerate(tasks, 1):
        per_problem.append(
            {
                "index": index,
                "task": task,
                "model_building": local_problem_model_building(index, task, selection),
                "solving": local_problem_solving(index, task, selection),
            }
        )
    return {
        "target_body_pages": target_pages,
        "front_detail": {
            "restatement_detail": local_restatement_detail(tasks, selection),
            "analysis_detail": local_analysis_detail(tasks, selection),
            "assumption_detail": local_assumption_detail(selection),
            "symbol_detail": local_symbol_detail(selection),
        },
        "data_feature": {"content": local_data_feature_text(selection)},
        "model_overview": {"content": local_model_overview_text(selection, model)},
        "per_problem": per_problem,
        "validation_detail": {"content": local_validation_text(selection)},
        "evaluation_detail": {"content": local_evaluation_text(selection, tail)},
        "abstract_detail": {"abstract": skill_abstract_text(selection, tail)},
    }


def local_restatement_detail(tasks: list[str], selection: dict[str, Any]) -> str:
    title = selection.get("final_problem_title") or "所选赛题"
    paragraphs = [
        f"本文最终围绕{title}展开建模。题目材料通常同时包含文字说明、附件数据、格式要求和待回答的若干子问题，因此问题重述不能停留在题面复述，而应把工程对象、数据对象和数学输出逐层明确。各子问题之间具有递进关系：前序问题完成数据校正、特征提取或状态识别，后续问题在此基础上进行融合预测、分类判别或决策优化，最终形成能够写入论文结论的可复现答案。",
    ]
    for index, task in enumerate(tasks, 1):
        paragraphs.append(
            f"问题{index}可以重述为：在题目给定附件和前序处理结果的约束下，完成“{task}”。从数学角度看，该子问题需要先明确输入集合、输出集合和评价指标，再决定是否属于回归、分类、变点识别、优化决策或综合评价任务。其核心不是单纯给出文字判断，而是把题目要求转化为可以由程序读取数据、计算指标、生成表格并绘制图形的模型化流程。若该子问题依赖前一问的结果，则前一问输出必须以中间变量或中间表的形式保存，避免论文写作时出现结论无法追溯的问题。"
        )
    paragraphs.append(
        "因此，本文把所有子问题统一理解为一条从数据到模型、从模型到结果、从结果到检验的闭环链条。每一个子问题的答案都应包含三个层次：第一，说明使用哪些原始数据或中间特征；第二，说明采用何种数学模型以及该模型为何适合题意；第三，说明模型输出如何通过图表和指标回答题目。这样的重述方式可以保证后续模型建立、模型求解和模型检验之间保持一致。"
    )
    return "\n\n".join(paragraphs)


def local_analysis_detail(tasks: list[str], selection: dict[str, Any]) -> str:
    model_chain = "、".join(str(item) for item in selection.get("model_chain", [])[:8]) or "数据清洗、特征构造、模型训练、结果检验"
    paragraphs = [
        f"总体上，本文采用的建模路径可以概括为：{model_chain}。这一链条的优点是既能保留可解释的数学结构，又能为复杂非线性关系预留算法空间。问题分析阶段需要特别区分“模型建立”和“模型求解”：前者只说明变量、公式、约束、算法和选择准则，后者才报告由附件数据计算得到的结果、图表和结论。",
    ]
    for index, task in enumerate(tasks, 1):
        paragraphs.append(
            f"针对问题{index}，其任务描述为“{task}”。该问题的输入通常包括题目附件中的原始变量、经清洗后的样本、由前序问题得到的校正量或阶段标签，以及为消除噪声和刻画滞后效应而构造的衍生特征。该问题的输出则应是参数、标签、预测量、阈值、排序、风险等级或决策规则中的一种或几种。建模难点主要来自三方面：一是附件数据可能存在缺失、重复、异常跳变或采样间隔不一致；二是变量之间可能具有非线性、滞后性和交互性；三是题目要求的结论往往需要兼顾数值精度、物理可解释性和论文可展示性。"
        )
        paragraphs.append(
            f"因此，问题{index}的算法路线应分为四步。第一步进行数据结构检查，明确样本单位、时间或编号含义以及可直接使用的变量。第二步构造与任务匹配的特征集合，例如差分、斜率、移动均值、累计量、滞后量、交互项或标准化指标。第三步建立候选模型，并用统一的损失函数、约束条件和模型选择准则确定参数。第四步将结果写入表格和图形，并在图表附近形成自然的判读段落，使评委能够直接看到该子问题如何被回答。"
        )
    paragraphs.append(
        "在模型类别选择上，若目标变量为连续数值，应优先考虑回归、时间序列预测或状态空间模型；若目标为类别或阶段，应采用分类模型、变点检测或聚类加判别规则；若目标是方案选择或阈值确定，则需要构造优化目标并比较误报、漏报、成本、稳定性等指标。无论采用何种算法，最终都必须回到题目数据本身，通过可复现的程序输出支撑论文中的结论。"
    )
    return "\n\n".join(paragraphs)


def local_assumption_detail(selection: dict[str, Any]) -> str:
    return "\n".join(
        [
            "1. 附件中同名变量或题面明确说明具有相同物理含义的变量，在统一单位和编码后可以放入同一建模框架；若中英文附件重复，正式计算时只保留一套数据，防止样本重复。",
            "2. 少量缺失值、异常跳变和传感器噪声不会改变系统的主要演化规律，可以通过鲁棒统计、局部插补、降权或人工复核处理；但疑似真实突变的样本不得被平滑算法直接抹去。",
            "3. 训练集、实验集或不同附件之间具有可比较的统计背景，经过相同预处理和特征工程后，模型参数、阈值或评价指标具有解释意义。",
            "4. 所有阈值、权重、阶段边界和模型参数均由数据、优化准则或验证指标确定，不在论文中主观填入无法追溯的精确数值。",
            "5. 复杂模型只有在相对简单模型表现出稳定改进时才作为最终方案；若复杂模型与基准模型差异不明显，优先选择可解释性更强的方案。",
        ]
    )


def local_symbol_detail(selection: dict[str, Any]) -> str:
    return (
        "符号说明采用“原始变量—衍生变量—模型函数—评价指标”的顺序组织。原始变量直接来自附件，必须保留题目中的单位；衍生变量由差分、滑动窗口、滞后、累计、标准化或交互运算得到，需要在正文中说明计算口径；模型函数用于表示回归、分类、融合或风险评估映射；评价指标用于比较候选模型与对照模型。"
        "为防止符号混乱，同一符号在全文中只表示一种含义。若不同子问题使用相同字母表示不同对象，应通过上标、下标或附加说明区分。"
    )


def local_data_feature_text(selection: dict[str, Any]) -> str:
    return "\n\n".join(
        [
            "数据预处理是自动建模流程的第一层约束。程序读取附件后，应首先建立文件清单和字段映射表，记录每个字段的来源文件、变量含义、单位、数据类型和缺失比例。对于时间序列数据，需要检查时间戳是否严格递增、采样间隔是否固定、是否存在重复时刻以及不同监测量之间是否需要对齐。对于非时间序列数据，需要检查编号列、类别列和数值列的含义，避免把样本编号误当作连续变量参与建模。",
            "缺失值处理不宜使用单一规则。若缺失长度很短且相邻点变化平缓，可以采用线性插值或局部多项式插补；若缺失出现在关键突变区间，应保留缺失标记并在后续模型中使用掩码变量；若缺失比例过高，则该变量只能作为辅助解释，不应作为最终模型的核心输入。所有插补操作都应在附录中记录，以便复现。",
            "异常值识别采用统计检测与机理判断结合的方式。滑动中位数、MAD、箱线图和差分突变可以快速发现异常候选点，但边坡、制造、调度或工程系统中真实突变也可能具有异常形态。因此异常点不直接删除，而是先进入复核集合，再根据前后趋势、其他传感器同步变化和题目背景判断其来源。若判定为设备误差，可以插补或降权；若判定为真实事件，则应保留并在模型中体现。",
            "特征工程围绕题目目标展开。对连续演化类问题，应构造差分、速度、加速度、滑动均值、滑动方差、累计量和滞后项；对影响因素分析问题，应构造交互项、比值项、距离衰减项和分组统计量；对分类识别问题，应保证训练特征不包含未来信息；对预警或优化问题，应把阈值、代价和约束显式写入特征或目标函数。",
            "训练验证划分必须尊重数据结构。若样本具有时间顺序，不能随机打乱后再评估，而应采用滚动验证、时间切分或前段训练后段验证；若样本存在组别、工况或测点差异，应采用分组划分，防止同一对象的信息同时出现在训练集和验证集中。模型选择时记录随机种子、窗口长度、滞后阶数、惩罚系数和候选参数范围。",
            "可复现输出包括四类文件：一是清洗后的数据表，二是中间特征表，三是模型结果表，四是论文图形文件。每张表和每张图都应能追溯到生成脚本中的函数调用。论文正文只放与结论直接相关的图表，原始字段清单、较长中间表和完整代码放入附录或支撑材料包。"
        ]
    )


def local_model_overview_text(selection: dict[str, Any], model: dict[str, Any]) -> str:
    chain = "、".join(str(item) for item in selection.get("model_chain", [])[:10]) or "数据清洗、特征构造、候选模型比较、结果检验"
    return "\n\n".join(
        [
            f"总体模型框架以“{chain}”为主线。该框架的第一层是数据层，负责将不同附件中的字段统一为标准样本；第二层是特征层，负责从原始变量中提取与题目目标相关的统计量、动力学量或结构量；第三层是模型层，负责通过优化、回归、分类、变点检测或综合评价建立输入与输出之间的映射；第四层是检验层，负责从误差、稳定性、敏感性和可解释性角度判断模型是否可信。",
            "在数学原理上，所有候选模型都可以写成经验风险最小化形式。回归问题最小化预测误差，分类问题最小化交叉熵或加权交叉熵，阶段识别问题最小化分段拟合误差并惩罚过多变点，预警问题则在风险识别能力和误报漏报代价之间取得平衡。这样的统一写法有利于论文中解释模型链条，也方便在程序中用相同的接口比较不同算法。",
            "鲁棒性是模型建立的重要原则。题目附件往往来自实际监测或实验系统，数据误差不可避免。平方损失对异常点敏感，因此在传感器校正、曲线拟合和短样本回归中可引入 Huber 损失、分位数损失或异常点降权；在分类任务中可引入类别权重、阈值移动或代价敏感学习；在预警任务中可用连续窗口确认规则减少偶然尖峰造成的误报。",
            "模型选择不是单纯追求复杂度。若线性模型、分段线性模型或逻辑回归已经能解释主要关系，则复杂机器学习模型只作为对照或补充；若变量之间存在明显非线性、交互和滞后，则可引入随机森林、梯度提升树、支持向量机、神经网络或状态空间模型。最终选择应同时考虑验证指标、图形趋势、参数解释和计算稳定性。",
            "算法伪代码应体现完整闭环：读取数据、检查字段、清洗异常、构造特征、划分训练验证、训练候选模型、选择参数、生成预测或分类结果、绘制图表、保存结果和输出论文结论。伪代码不需要写出具体编程语法，但必须让读者看懂输入是什么、每一步做什么、输出放在哪里，以及哪些结果必须由程序计算后才能写入摘要。",
            "模型建立部分严格不报告数值结果。这里可以写目标函数、约束条件、阈值确定原则、指标定义和算法流程，但不能写基于图表作判断、宣布指标优劣或直接给出准确率的求解性表述。所有由数据计算得到的参数、误差、阶段节点、预测值、预警等级和比较结论都应放入模型求解或模型检验部分。"
        ]
    )


def local_problem_model_building(index: int, task: str, selection: dict[str, Any]) -> str:
    return "\n\n".join(
        [
            f"问题{index}的模型建立围绕“{task}”展开。首先将该子问题写成输入、输出和约束三元组。输入包括题目附件中的原始变量、经过统一单位和缺失异常处理后的清洗变量，以及由前序问题产生的中间结果；输出则是该子问题要求提交的参数、标签、预测值、阈值、排序或决策规则。约束条件来自题目物理背景、数据可用性、训练验证划分和结果可解释性。",
            "变量层面，设清洗后的样本为 x_t，目标量为 y_t。若 y_t 是连续变量，则模型输出为 \\hat y_t=f(x_t)；若 y_t 是阶段或类别，则输出为各类别概率 p(S_t=j|x_t)；若目标是风险等级或阈值，则输出为综合指数 G_t 或阈值集合 \\theta。这样处理可以让不同类型的子问题共用统一的特征接口，同时保留各自的目标函数。",
            "特征层面，原始变量不应直接全部塞入模型，而要依据题目机理进行整理。连续监测量需要构造差分、速度、加速度、滑动均值、滑动方差和累计量；具有滞后效应的变量需要构造 t-1 到 t-l 的滞后项；工程扰动或空间影响变量可以构造交互项、衰减项或归一化强度；类别变量应进行独热编码或有序编码，并在论文中说明其物理含义。",
            "目标函数根据任务类型选择。回归模型以误差平方和、绝对误差或 Huber 损失为主体；分类模型以交叉熵或加权交叉熵为主体；变点识别模型以分段拟合误差加复杂度惩罚为主体；综合评价模型以标准化指标加权、熵权或概率输出为主体；优化决策模型以收益、成本、风险或约束违反惩罚为主体。所有目标函数都应明确自变量、待估参数和约束范围。",
            "参数估计采用候选模型比较而非单模型直接给结论。先设置可解释基准模型，例如线性回归、规则阈值、分段线性或逻辑回归；再根据数据非线性和交互性引入随机森林、梯度提升、支持向量机或神经网络等模型；最后用验证误差、稳定性和图形解释选择最终方案。若复杂模型没有稳定优势，则保留简单模型作为主模型。",
            "算法伪代码可概括为：输入附件数据和题目约束；执行字段映射、单位统一和缺失异常处理；构造与问题目标相关的特征矩阵；定义候选模型、损失函数和参数网格；采用滚动验证、交叉验证或留出验证选择参数；保存中间变量、模型参数、评价指标和可视化数据；输出可写入论文的图表。该伪代码强调可复现性，避免只给概念而无法落地。",
            "本问题的模型建立部分不写任何由数据计算得到的数值结果。可以说明哪些表格需要在求解阶段生成，哪些图形用于解释结果，但不能在模型建立中写出最优参数、阶段节点、预测误差、分类准确率或预警阈值。这样做可以保持论文结构边界清楚，也便于后续审查器检查章节职责。"
        ]
    )


def local_problem_solving(index: int, task: str, selection: dict[str, Any]) -> str:
    return "\n\n".join(
        [
            f"问题{index}的求解目标是完成“{task}”对应的计算输出。求解程序首先读取该子问题所需附件，并调用统一预处理函数生成清洗数据表。随后根据模型建立部分定义的变量和特征工程规则生成特征矩阵，确保训练集、实验集和待预测样本使用完全相同的字段顺序、单位和标准化参数。",
            "第一步是数据核验。程序应输出字段检查表，列出样本数量、有效样本数量、缺失比例、异常候选点数量和主要变量的基本统计量。该表的描述应说明每个字段是否可直接进入模型；分析应关注缺失和异常是否集中在特定时段、类别或工况；结论应说明是否需要插补、剔除、降权或保留异常标记。",
            "第二步是特征计算。对于连续变量，计算差分、斜率、移动均值、移动标准差、累计量、最大值、最小值和分位数；对于存在滞后影响的变量，计算多个滞后阶的特征；对于扰动或空间因素，计算交互项和衰减项。程序应保存特征表，论文中可放入“特征定义与计算口径表”，并在表后说明这些特征分别服务于趋势刻画、非线性耦合、阶段识别或风险解释。",
            "第三步是模型训练和参数选择。若样本具有时间顺序，采用滚动验证或按时间前后划分训练验证集；若样本按类别或工况分组，采用分层或分组验证；若题目给出实验集标签，应按题意决定其用途，避免将验证标签泄漏进训练过程。候选模型的参数由验证指标、网格搜索或交叉验证确定，并写入参数记录表。",
            "第四步是结果生成。回归问题输出预测值、残差和误差指标；分类问题输出预测标签、类别概率和混淆矩阵；变点问题输出阶段边界、分段参数和残差；预警问题输出风险指数、等级、触发原因和提前量；优化问题输出最优方案、目标函数值和约束满足情况。若当前流程尚未运行数值脚本，论文底稿只保留结果表结构，不填入虚构数值。",
            "第五步是图表解释。每张图和表都应紧跟在对应结果之后，并用一段自然文字说明图表包含的变量和计算口径，指出趋势、差异、异常、误差集中区或类别混淆，最后落到该子问题的直接回答。例如，若图展示模型预测与观测对比，应判断残差是否随时间扩大；若表展示阈值和等级，应判断等级边界是否符合数据分布；若图展示特征重要性，应说明关键变量是否符合题意机理。",
            "第六步是复核与落稿。求解完成后，程序把结果写入 results 或 artifacts 目录，并记录脚本名称、输入文件、输出文件和运行时间。论文正文只引用与子问题答案直接相关的图表；完整中间表、参数网格、代码和日志放入附录或支撑材料包。摘要中出现的每一个数值，都必须能在本子问题的表格、图形或审查报告中找到来源。",
            "该求解过程的结论写法应保持克制。若数据计算结果支持某一模型，应写明该模型在指定指标下更优；若不同指标存在冲突，应说明选择理由；若某些结果需要人工复核，应明确列为提交前检查项。这样能够避免自动生成论文中常见的过度断言问题。"
        ]
    )


def local_validation_text(selection: dict[str, Any]) -> str:
    return "\n\n".join(
        [
            "模型检验从四个维度展开：误差检验、稳定性检验、敏感性检验和对照检验。误差检验用于回答模型在现有数据上的拟合或预测能力；稳定性检验用于回答参数、窗口和随机种子变化时结论是否保持一致；敏感性检验用于识别哪些变量或阈值对最终结论影响最大；对照检验用于证明所选模型相对于简单模型具有必要性。",
            "对于回归或校正类任务，主要指标包括 MAE、RMSE、MAPE、最大绝对误差、相关系数和残差自相关。MAE 反映平均绝对偏差，RMSE 对大误差更敏感，最大绝对误差用于检查极端样本，残差自相关用于判断是否仍存在系统性未解释结构。若校正后残差均值接近零、方差降低且无明显时间漂移，说明校正模型具有合理性。",
            "对于阶段识别或分类任务，主要指标包括准确率、精确率、召回率、宏平均 F1、Kappa 系数和混淆矩阵。若类别不均衡，不能只看准确率，应重点报告少数类召回率和宏平均 F1。混淆矩阵应放在模型求解或检验附近，并说明哪些阶段容易被混淆、混淆是否符合相邻阶段过渡的物理或业务逻辑。",
            "对于风险预警或决策类任务，检验指标应包括命中率、误报率、漏报率、平均提前量、最小提前量和预警等级稳定性。阈值不能仅由单次经验设定，而应通过训练集分布、验证集代价函数、ROC 曲线、PR 曲线或分位数规则确定。若提高敏感性会显著增加误报，需要在论文中说明该权衡对实际应用的影响。",
            "稳定性分析通过改变关键建模设定完成。可调整平滑窗口长度、滞后阶数、变点惩罚系数、异常点处理方式、训练验证划分和随机种子，观察核心输出是否发生大幅变化。若最终阶段节点、重要变量排序、预测趋势或预警等级在合理范围内保持一致，则说明模型对局部设定不敏感；若变化过大，需要回到模型建立部分重新解释约束或改用更稳健方法。",
            "敏感性分析采用单因素扰动和消融实验结合。单因素扰动用于考察某一输入变量、权重或阈值变化对输出的影响；消融实验用于比较去掉某类特征后模型性能是否下降。若删除某类变量后结果变化很小，说明该变量在当前数据中贡献有限；若删除后误差上升或关键结论改变，则该变量应在论文中作为主要影响因素讨论。",
            "对照检验设置简单模型作为基准。回归任务可比较均值模型、线性模型和非线性模型；分类任务可比较规则阈值、逻辑回归和树模型；预警任务可比较单指标阈值和多源融合阈值。只有当复杂模型在多个指标上稳定优于对照模型，且图形解释与实际机理一致时，才将复杂模型作为最终方案。",
            "所有检验指标必须由附件数据计算得到。若当前自动流程只生成论文结构而尚未运行完整数值脚本，则正文可以保留计算公式、表格结构和图表解释模板，但不能写入虚构的精确数值。正式提交前应以程序输出替换占位内容，并复核摘要中的每一个数值是否能在正文图表或支撑材料中找到来源。"
        ]
    )


def local_evaluation_text(selection: dict[str, Any], tail: dict[str, Any]) -> str:
    base = str(tail.get("evaluation") or "")
    extra = "\n\n".join(
        [
            "本文模型的主要优点是流程完整、边界清晰、可复现性较强。数据预处理层保证不同附件进入统一变量体系；模型建立层把目标函数、约束和算法流程写清楚；模型求解层把每个子问题的图表放在对应结果附近；模型检验层通过误差、稳定性、敏感性和对照实验验证结论。这样的结构符合数学建模竞赛论文的阅读习惯，也便于评委快速追踪每个结论的来源。",
            "模型的不足主要来自自动化流程和数据条件。若附件中样本量较小、标签较少或极端事件不足，复杂模型的泛化能力可能被高估；若题面文字中存在未被程序完全解析的隐含约束，模型可能需要人工补充业务判断；若官方模板只有 Word 或规则说明，LaTeX 自动排版仍需在提交前人工核对页边距、标题格式、图表编号和匿名要求。",
            "后续改进可以从三方面展开。第一，引入更强的数据读取模块，自动识别 Word、PDF、Excel 中的表格、图片和公式说明；第二，引入可运行的结果计算沙箱，在 LLM 完成建模设计后自动生成代码、运行并回填数值；第三，引入论文审查闭环，让系统根据页数、章节、图表、引用和数值可追溯性自动提出二次修订。",
            "该建模思想可以推广到多传感器监测、工业过程质量控制、交通运行评估、能源负荷预测、灾害预警和资源调度等问题。只要任务能够被表示为“数据清洗—特征构造—模型映射—指标检验—决策输出”的链条，就可以复用本文的自动化论文生成框架。"
        ]
    )
    return join_texts(base, extra)


def skill_abstract_text(selection: dict[str, Any], tail: dict[str, Any] | None = None) -> str:
    tasks = normalize_tasks(selection)
    title = sanitize_abstract_text(selection.get("final_problem_title") or "所选赛题")
    problem_sentences = [abstract_problem_sentence(index, task) for index, task in enumerate(tasks, 1)]
    return sanitize_abstract_text(
        f"针对{title}中数据预测、约束优化与决策评价的综合建模问题，本文以题目数据为依据，目标是在不编造数值结果的前提下完成模型设计、可复现求解、图表组织和可靠性检验。"
        f"{abstract_method_chain_sentence(selection)}"
        + "".join(problem_sentences)
        + "为检验模型可靠性，本文采用残差诊断、交叉验证、敏感性分析、消融对照、图表一致性检查和约束可行性复核等方法，确认模型建立与模型求解边界清晰，图表附近均配有能够交代内容、解释现象并归纳结论的自然判读段落。"
        "最终形成可复现的建模结论；其中预测值、优化变量、误差指标、分类指标、权重和阈值等精确数值均需由题目数据和程序输出计算得到，并在提交前进行人工复核。"
    )


def abstract_method_chain_sentence(selection: dict[str, Any]) -> str:
    chain = [inline_text(item) for item in selection.get("model_chain", []) if inline_text(item)]
    corpus = " ".join([inline_text(selection.get("final_problem_title")), *chain, *normalize_tasks(selection)])
    if any(term in corpus for term in ["物流", "集包", "分拣", "包裹", "格口", "产能", "设备"]):
        return (
            "本文首先对历史货量、走货路由、设备能力和候选设备参数进行字段校验、编码统一、重复记录合并和异常识别；"
            "随后面向首末流向构造滞后项、滚动统计量、星期周期和趋势特征，并通过滚动时间窗验证比较季节朴素、指数平滑、ARIMA类模型和可解释机器学习候选；"
            "再将分拣中心抽象为有向路径图，建立包含规则唯一性、路径可达性、格口占用和产能上限的0-1集包规则优化模型；"
            "最后在货量增长情景下引入设备购置、人工补充、年化成本和约束余量变量，构建设备配置混合整数优化与敏感性检验流程。"
        )
    if any(term in corpus for term in ["海上风电", "风力发电机", "风机", "无人艇", "无人机", "停泊点", "巡检"]):
        return (
            "本文首先对风机坐标、港口位置和设备参数进行字段校验、单位统一和局部投影距离换算；"
            "随后由安全距离、续航时间和巡检时间构造风机--停泊点可服务矩阵，并建立候选停泊点覆盖、无人艇闭合路径和并行无人机调度模型；"
            "再通过多艇分区、车辆路径启发式和最大完工时间均衡形成协同巡检方案；"
            "最后采用区间不确定性、保守参数情景对比和上界续航复核检验方案的鲁棒性。"
        )
    if any("预警" in item or "阈值" in item for item in chain):
        return (
            "本文首先使用字段盘点、单位统一、缺失异常识别和时间或编号对齐完成数据质量控制；"
            "随后基于传感器校正、平滑去噪、速度加速度和滞后滑动统计量构建统一特征体系；"
            "再通过分段回归、变点检测、多源融合和监督分类完成阶段识别、影响因素分析与实验集判别；"
            "最后采用综合风险指数、数据驱动阈值和连续窗口确认构建分级预警与可靠性检验流程。"
        )
    return (
        "本文首先使用字段盘点、单位统一、缺失异常识别和样本对齐完成数据质量控制；"
        "随后基于题目变量、约束条件和评价指标构建统一特征体系；"
        "再通过候选模型比较、参数选择和交叉验证完成核心模型求解；"
        "最后采用图表解释、敏感性分析和论文审查形成可复现的结论。"
    )


def method_chain_sentence(selection: dict[str, Any]) -> str:
    chain = [inline_text(item) for item in selection.get("model_chain", []) if inline_text(item)]
    if not chain:
        return "基于数据清洗、特征工程、候选模型比较、模型检验和论文审查建立完整建模流程"
    pieces = []
    for item in chain[:6]:
        if "清洗" in item or "预处理" in item or "对齐" in item:
            pieces.append("基于数据清洗与时序对齐构造统一样本表")
        elif "校正" in item:
            pieces.append("使用传感器校正模型统一观测尺度")
        elif "变点" in item or "阶段" in item:
            pieces.append("采用去噪、速度加速度特征和变点检测识别状态阶段")
        elif "融合" in item or "预测" in item:
            pieces.append("构造滞后项、滑动统计量和多源融合模型完成预测或判别")
        elif "预警" in item or "阈值" in item:
            pieces.append("采用风险指数、概率输出和数据驱动阈值构建预警规则")
        elif "检验" in item or "验证" in item:
            pieces.append("通过误差、稳定性和敏感性检验评价可靠性")
        else:
            pieces.append(item.rstrip("。；;"))
    deduped = []
    for piece in pieces:
        if piece not in deduped:
            deduped.append(piece)
    return "；".join(deduped)


def abstract_problem_sentence(index: int, task: str) -> str:
    task_text = inline_text(task)
    lower = task_text.lower()
    if any(term in task_text for term in ["不确定", "鲁棒", "风险偏好", "保守"]):
        factors = "巡检时间区间波动、名义时间、最大偏差、保守参数、续航裕度和上界情景违约风险"
        model_name = "基于保守参数的区间鲁棒协同调度模型"
        algorithm = "确定性、低保守和高保守三情景对比、上界续航复核和效率--稳健性权衡分析"
        result = "各保守情景的最大完工时间、上界情景续航裕度、违约次数和鲁棒权衡图"
    elif any(term in task_text for term in ["多无人艇", "多艇", "多无人机", "舰队"]):
        factors = "多艇任务互斥、艇载无人机容量、停泊点服务范围、路径连通和最大完工时间均衡"
        model_name = "多车辆路径与负载均衡协同优化模型"
        algorithm = "空间分区、车辆路径启发式、单艇子路径2-opt改进和LPT无人机装载调度"
        result = "多艇访问路径、各艇完工时间、瓶颈无人艇、覆盖唯一性和续航安全核验结果"
    elif any(term in task_text for term in ["无人艇", "无人机", "停泊点", "风机", "巡检", "路径规划"]):
        factors = "停泊点覆盖、安全距离、无人机续航、无人艇闭合路径和停泊点内并行作业时间"
        model_name = "KMeans候选停泊点覆盖--单艇TSP路径--并行机调度模型"
        algorithm = "KMeans候选点生成、最近邻TSP初解、2-opt局部搜索和LPT任务分配"
        result = "停泊点选择、单艇访问序列、无人机任务分配、总完工时间和约束可行性检查表"
    elif any(term in task_text for term in ["设备", "购置", "扩容", "折旧", "人工", "增长"]):
        factors = "增长需求、候选设备格口与产能、年化折旧成本、人工补充能力和场地容量余量"
        model_name = "设备购置与人工补充联合混合整数优化模型"
        algorithm = "容量缺口计算、单位能力成本筛选、整数枚举或混合整数规划求解以及成本敏感性检验"
        result = "各场地设备购置数量、人工补充量、年化成本分解、扩容后约束满足表和可复核的结果表"
    elif any(term in task_text for term in ["集包", "路由", "格口", "产能", "分拣中心", "建包"]):
        factors = "唯一走货路由、建包节点可达性、规则唯一性、格口占用、产能上限和节点负载均衡"
        model_name = "有向路径约束下的0-1集包规则优化模型"
        algorithm = "候选建包弧枚举、路径可行性核验、容量约束检查和整数规划或启发式优化"
        result = "每个首末流向的集包规则、路由可行性检查、容量利用率和超限场地清单"
    elif any(term in task_text for term in ["货量", "预测", "包裹量", "时间序列", "未来"]):
        factors = "首末流向层级差异、星期周期、趋势波动、异常值、稀疏流向和非负需求约束"
        model_name = "滚动验证驱动的分层时间序列预测模型"
        algorithm = "季节朴素、指数平滑、ARIMA类模型、滞后特征回归和稳健兜底规则的候选比较"
        result = "未来预测表、滚动验证误差、模型选择记录和主要流向趋势图"
    elif "爆破" in task_text:
        factors = "爆破点距离、单段最大药量、位移响应、环境变量和阶段标签不均衡"
        model_name = "含爆破扰动衰减特征的监督阶段分类模型"
        algorithm = "扰动强度特征构造、加权分类训练、混淆矩阵和类别召回率检验"
        result = "实验集阶段识别结果、混淆矩阵、分类评价指标和爆破因素贡献分析"
    elif "校正" in task_text or "传感器" in task_text or "位移序列" in task_text and "基准" in task_text:
        factors = "传感器偏移、比例误差、时间漂移、异常点和残差稳定性"
        model_name = "鲁棒线性校正与分段漂移校正模型"
        algorithm = "最小二乘、Huber 损失、残差对比和误差指标筛选"
        result = "校正后的观测序列、候选模型参数表和由数据计算的 MAE、RMSE、最大绝对误差等评价结果"
    elif "阶段" in task_text or "变点" in task_text or "快速" in task_text:
        factors = "位移趋势、平滑窗口、速度、加速度、阶段连续性和转换节点稳定性"
        model_name = "去噪特征提取与受约束分段回归阶段识别模型"
        algorithm = "滑动平滑、速度加速度计算、变点搜索和分段拟合"
        result = "三阶段划分、转换节点表、阶段特征表和由数据生成的位移及动力学特征图"
    elif "融合" in task_text or "降雨" in task_text or "孔压" in task_text or "微震" in task_text:
        factors = "降雨量、孔隙水压力、微震事件、深部位移、表面位移及其滞后耦合关系"
        model_name = "多源滞后特征融合与预测判别模型"
        algorithm = "相关性分析、滞后特征构造、标准化处理、回归或分类模型训练"
        result = "关键影响因子排序、实验集预测或判别表、模型性能指标和多源关系图"
    elif "预警" in task_text or "阈值" in task_text or "风险" in task_text:
        factors = "位移速度、加速度、降雨入渗、孔压变化、微震活跃度、爆破扰动和连续触发条件"
        model_name = "多源综合风险指数与分级预警模型"
        algorithm = "指标标准化、权重估计、阈值寻优、连续窗口确认和回放检验"
        result = "预警等级、阈值规则、触发原因表、风险指数曲线和由数据计算的误报漏报及提前量指标"
    else:
        factors = "题目给定变量、数据质量、约束条件、目标函数、输出指标和可解释性要求"
        model_name = "面向本问目标函数和约束结构的统计或优化求解模型"
        algorithm = "字段校验、特征构造、候选算法比较、参数选择、约束核验和结果回填"
        result = "可复现的模型参数、结果表格、图形解释、约束核验和验证指标"
    return f"针对问题{index}，考虑{factors}，建立{model_name}，采用{algorithm}，得到{result}。"


def generate_expanded_sections(
    context: dict[str, Any],
    selection: dict[str, Any],
    front: dict[str, Any],
    model: dict[str, Any],
    tail: dict[str, Any],
    target_pages: int,
) -> dict[str, Any]:
    tasks = normalize_tasks(selection)
    compact_plan = {
        "final_problem_id": selection.get("final_problem_id"),
        "final_problem_title": selection.get("final_problem_title"),
        "tasks": tasks,
        "model_chain": selection.get("model_chain", []),
        "data_needs": selection.get("data_needs", []),
        "risk_control": selection.get("risk_control", []),
    }
    shared_rules = f"""论文正文目标不少于 {target_pages} 页，正文不包含摘要和附录，不生成目录页。
必须遵守：问题重述和问题分析按子问题分别写，直接使用充分展开的分问题段落，不再额外添加“任务概括”或短概括段；模型建立只写数学原理、目标函数、约束、算法和伪代码，不写结果；公式既要允许段内内联公式，也要使用独占一行的显式公式，内联公式用 $...$，所有独立公式必须用 $$...$$ 包裹，公式内部使用标准 LaTeX 语法，显式公式会自动编号；模型求解按子问题分别写；所有图表都要紧跟自然判读段落，段落应同时说明图表内容、关键现象和子问题结论，但不得使用带冒号的固定图表解读标签；不得编造未由附件计算得到的精确数值。

标准论文规则：
{render_standard_paper_rules()}"""
    front_detail = call_json_response(
        f"""请扩写数学建模论文正文的“问题重述、问题分析、模型假设、符号说明”。
只输出 JSON，不要 Markdown，不要解释。字段：
{{
  "restatement_detail": "按每个子问题分别扩写问题重述，要求逻辑关系清楚，约1800-2400汉字",
  "analysis_detail": "按每个子问题分别扩写问题分析，说明模型类型、难点、输入输出、算法路线和相邻问题衔接，约2200-3000汉字",
  "assumption_detail": "扩写模型假设，每条假设说明作用和合理性，约1000-1400汉字",
  "symbol_detail": "补充符号说明的组织逻辑、变量维度、单位处理和一致性要求，约700-1000汉字"
}}
{shared_rules}

选题与任务：
```json
{json.dumps(compact_plan, ensure_ascii=False, indent=2)}
```

已有前半部分：
```json
{json.dumps(front, ensure_ascii=False, indent=2)}
```""",
        max_tokens=5200,
    )
    data_feature = call_json_response(
        f"""请扩写数学建模论文正文中的“数据预处理与特征工程”方法段。
只输出 JSON，不要 Markdown，不要解释。字段：
{{
  "content": "围绕数据读取、时间对齐、缺失处理、异常识别、平滑去噪、速度加速度、滞后特征、滑动统计量、训练验证划分和可复现输出进行系统扩写，约2600-3400汉字；只写方法，不写结果数值"
}}
{shared_rules}

选题与任务：
```json
{json.dumps(compact_plan, ensure_ascii=False, indent=2)}
```

赛题上下文摘要：
```json
{json.dumps(context, ensure_ascii=False, indent=2)[:7000]}
```""",
        max_tokens=5000,
    )
    model_overview = call_json_response(
        f"""请扩写数学建模论文正文中的“总体模型框架与数学原理”。
只输出 JSON，不要 Markdown，不要解释。字段：
{{
  "content": "从统一变量表示、损失函数、鲁棒估计、变点检测、多源融合、分类/预测、风险指数、阈值寻优、模型选择准则等角度扩写，约3000-3800汉字；只写模型建立原理，不写任何结果；内联公式写成 $...$，独立公式必须写成 $$...$$"
}}
{shared_rules}

选题与任务：
```json
{json.dumps(compact_plan, ensure_ascii=False, indent=2)}
```

已有模型主体：
```json
{json.dumps(model, ensure_ascii=False, indent=2)}
```""",
        max_tokens=5600,
    )

    per_problem = []
    for index, task in enumerate(tasks, 1):
        item = call_json_response(
            f"""请针对数学建模论文的第 {index} 个子问题扩写“模型建立”和“模型求解”两个正文段。
只输出 JSON，不要 Markdown，不要解释。字段：
{{
  "model_building": "围绕该子问题扩写模型建立：变量、输入输出、数学原理、目标函数、约束、参数估计、算法流程、伪代码解释；只写原理，不写结果，约1900-2600汉字；内联公式写成 $...$，独立公式必须写成 $$...$$",
  "solving": "围绕该子问题扩写模型求解：数据如何进入模型、程序如何执行、应生成哪些表格和图片、图表后的自然判读段落怎样回答问题；不得编造精确数值，约2200-3000汉字"
}}
{shared_rules}

当前子问题：{task}

整体选题与任务：
```json
{json.dumps(compact_plan, ensure_ascii=False, indent=2)}
```

已有模型主体：
```json
{json.dumps(model, ensure_ascii=False, indent=2)}
```""",
            max_tokens=6200,
        )
        per_problem.append(
            {
                "index": index,
                "task": task,
                "model_building": text_field(item, "model_building"),
                "solving": text_field(item, "solving"),
                "raw": item,
            }
        )

    validation_detail = call_json_response(
        f"""请扩写数学建模论文正文的“模型检验”。
只输出 JSON，不要 Markdown，不要解释。字段：
{{
  "content": "围绕误差指标、滚动验证、交叉验证、消融对照、敏感性分析、稳定性分析、残差诊断、物理一致性、预警代价与提前量评估进行扩写，约3600-4800汉字；不得编造指标数值"
}}
{shared_rules}

选题与任务：
```json
{json.dumps(compact_plan, ensure_ascii=False, indent=2)}
```

已有检验方案：
```json
{json.dumps(model.get("validation", ""), ensure_ascii=False, indent=2)}
```""",
        max_tokens=6200,
    )
    evaluation_detail = call_json_response(
        f"""请扩写数学建模论文正文的“模型评价与推广”。
只输出 JSON，不要 Markdown，不要解释。字段：
{{
  "content": "客观说明模型优点、不足、改进方向和推广场景，要求与本题模型链条对应，约1800-2400汉字"
}}
{shared_rules}

选题与任务：
```json
{json.dumps(compact_plan, ensure_ascii=False, indent=2)}
```

已有评价：
```json
{json.dumps(tail.get("evaluation", ""), ensure_ascii=False, indent=2)}
```""",
        max_tokens=3600,
    )
    abstract_detail = call_json_response(
        f"""请优化数学建模竞赛论文摘要，使其接近一页但不编造数值。
只输出 JSON，不要 Markdown，不要解释。字段：
{{
  "abstract": "必须严格按以下顺序写成一段摘要：1）说明问题背景、总体目标；2）用“首先……；随后……；再……；最后……”具体说明方法链；3）逐个子问题使用固定句式“针对问题X，考虑……因素，建立……模型，采用……算法，得到……结果。”，结果必须紧跟在该句的“得到”之后；4）说明检验方法、可靠性和最终结论。约900-1300汉字；不得写未计算出的具体数值；不得出现A题/B题/C题等题号字母，不得出现具体文件名、路径或Sheet名"
}}

选题与任务：
```json
{json.dumps(compact_plan, ensure_ascii=False, indent=2)}
```

已有摘要：
```json
{json.dumps(tail.get("abstract", ""), ensure_ascii=False, indent=2)}
```""",
        max_tokens=2600,
    )
    return {
        "target_body_pages": target_pages,
        "front_detail": front_detail,
        "data_feature": data_feature,
        "model_overview": model_overview,
        "per_problem": per_problem,
        "validation_detail": validation_detail,
        "evaluation_detail": evaluation_detail,
        "abstract_detail": abstract_detail,
    }


def call_json_response(prompt: str, max_tokens: int, stream_label: str | None = None) -> dict[str, Any]:
    last_error = ""
    for _ in range(2):
        try:
            text = call_chat_completion(prompt, max_tokens=max_tokens, stream_label=stream_label or infer_json_stage_label(prompt))
            try:
                return json.loads(extract_json_object(text))
            except Exception:
                return {"raw": text}
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"
    return {"error": last_error, "raw": ""}


def infer_json_stage_label(prompt: str) -> str:
    text = re.sub(r"\s+", " ", (prompt or "").strip())
    if not text:
        return "生成 JSON 题解内容"
    if "选题与建模总控" in text:
        return "生成选题与任务拆解"
    if "论文生成前半部分" in text:
        return "生成问题重述与问题分析"
    if "模型主体内容" in text:
        return "生成模型建立与求解方案"
    if "摘要和收尾内容" in text:
        return "生成摘要、评价与附录"
    if "拟定正式标题" in text or "paper_title" in text:
        return "生成论文标题"
    if "扩写" in text or "正文" in text:
        return "扩写标准论文正文"
    return text[:48] or "生成 JSON 题解内容"


def extract_json_object(text: str) -> str:
    fenced = re.search(r"```json\s*([\s\S]*?)\s*```", text, re.I)
    if fenced:
        return fenced.group(1)
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end >= start:
        return text[start : end + 1]
    raise ValueError("LLM 未返回 JSON 对象")


def render_solution_markdown(sections: dict[str, Any]) -> str:
    lines = ["# LLM 全流程题解", ""]
    for title, key in [
        ("最终选题", "selection"),
        ("论文前半部分", "front"),
        ("模型主体", "model"),
        ("摘要与收尾", "tail"),
        ("论文标题", "paper_title"),
        ("25页正文扩展材料", "expanded"),
    ]:
        if key in sections:
            lines.extend([f"## {title}", "", "```json", json.dumps(sections.get(key, {}), ensure_ascii=False, indent=2), "```", ""])
    return "\n".join(lines)


def bibliography_items_latex(references: list[Any]) -> tuple[str, dict[str, str]]:
    labels: dict[str, str] = {}
    used: set[str] = set()
    lines: list[str] = []
    for index, item in enumerate(references, 1):
        text = inline_text(item)
        label = unique_bib_label(reference_label_from_text(text, index), used)
        labels.update(reference_hint_labels(text, label))
        lines.append(rf"\bibitem{{{label}}} {latex_text_preserving_math(text)}")
    return "\n".join(lines), labels


def reference_label_from_text(text: str, index: int) -> str:
    lower = text.lower()
    if "hyndman" in lower or "forecasting: principles" in lower:
        return "hyndman_forecasting"
    if "box" in lower or "jenkins" in lower or "time series analysis" in lower:
        return "box_time_series"
    if "winston" in lower or "operations research" in lower:
        return "winston_operations"
    if "nemhauser" in lower or "wolsey" in lower or "combinatorial optimization" in lower:
        return "nemhauser_integer"
    if "赛题" in text or "题面" in text or "组委会" in text or "数据材料" in text:
        return "contest_statement"
    return f"ref{index}"


def unique_bib_label(label: str, used: set[str]) -> str:
    base = re.sub(r"[^A-Za-z0-9_:-]", "_", label) or "ref"
    candidate = base
    counter = 2
    while candidate in used:
        candidate = f"{base}_{counter}"
        counter += 1
    used.add(candidate)
    return candidate


def reference_hint_labels(text: str, label: str) -> dict[str, str]:
    lower = text.lower()
    hints: dict[str, str] = {}
    if "赛题" in text or "题面" in text or "组委会" in text or "数据材料" in text:
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


def literature_method_basis_latex(selection: dict[str, Any], references: list[Any], labels: dict[str, str]) -> str:
    if not labels:
        return ""
    corpus = " ".join(
        [
            inline_text(selection.get("final_problem_title")),
            " ".join(normalize_tasks(selection)),
            " ".join(inline_text(item) for item in selection.get("model_chain", []) if item),
        ]
    )
    forecast_cite = cite_from_label_hints(labels, ["forecast_hyndman", "forecast_box"])
    opt_cite = cite_from_label_hints(labels, ["optimization_winston", "optimization_integer"])
    contest_cite = cite_from_label_hints(labels, ["contest"])
    if any(term in corpus for term in ["物流", "集包", "分拣", "包裹", "格口", "产能", "设备"]):
        sentences = ["本文的模型建立以题面约束和经典方法为依据。"]
        if forecast_cite:
            sentences.append(
                f"货量预测部分参考时间序列预测中的滚动起点验证、季节朴素、指数平滑和 ARIMA 候选模型比较思想{forecast_cite}，用于避免随机划分造成的信息泄漏。"
            )
        if opt_cite:
            sentences.append(
                f"集包规则和设备配置部分参考运筹学及整数规划中的决策变量、目标函数和容量约束表达{opt_cite}，将路由连续性、格口占用、产能上限和年化成本统一到可计算框架。"
            )
        if contest_cite:
            sentences.append(f"字段口径、业务参数和结果表要求以赛题材料为准{contest_cite}。")
        sentences.append("这些文献提供方法来源，所有精确数值仍由题目数据和程序输出确定。")
        return "\\subsection{文献与方法依据}\n" + latex_text_preserving_citations("".join(sentences))
    available = [value for key, value in labels.items() if key != "contest"]
    if not available:
        return ""
    cites = r"\cite{" + ",".join(dict.fromkeys(available[:4])) + "}"
    return "\\subsection{文献与方法依据}\n" + latex_text_preserving_citations(
        f"本文根据任务类型选择预测、统计学习、网络优化或整数规划方法，方法来源参考相关教材与经典文献{cites}；所有精确数值仍以题目数据和程序输出为准。"
    )


def cite_from_label_hints(labels: dict[str, str], keys: list[str]) -> str:
    selected = [labels[key] for key in keys if key in labels]
    selected = list(dict.fromkeys(selected))
    return r"\cite{" + ",".join(selected) + "}" if selected else ""


def latex_text_preserving_citations(text: str) -> str:
    parts = re.split(r"(\\cite\{[^{}]+\})", str(text or ""))
    rendered: list[str] = []
    for part in parts:
        if not part:
            continue
        if re.fullmatch(r"\\cite\{[^{}]+\}", part):
            rendered.append(part)
        else:
            rendered.append(latex_text_preserving_math(part))
    return "".join(rendered) + "\n"


def render_latex_from_llm_sections(analysis: dict[str, Any], sections: dict[str, Any]) -> str:
    selection = sections.get("selection") or {}
    front = sections.get("front") or {}
    model = sections.get("model") or {}
    tail = sections.get("tail") or {}
    expanded = sections.get("expanded") or {}
    rec = analysis.get("recommended_problem", {})
    title = paper_title_from_selection(selection, rec)
    abstract_text = strict_skill_abstract(selection, text_field(expanded.get("abstract_detail", {}), "abstract") or tail.get("abstract"))
    keywords = tail.get("keywords") or ["数学建模", "大模型辅助", "模型求解", "论文生成"]
    references = tail.get("references") or ["数学建模竞赛组委会. 竞赛赛题与格式规范. 2026."]
    reference_items, reference_labels = bibliography_items_latex(references)
    tasks = normalize_tasks(selection)
    per_problem = expanded.get("per_problem") or [
        {"index": index, "task": task, "model_building": "", "solving": ""} for index, task in enumerate(tasks, 1)
    ]
    front_detail = expanded.get("front_detail") or {}
    data_feature = expanded.get("data_feature") or {}
    model_overview = expanded.get("model_overview") or {}
    validation_detail = expanded.get("validation_detail") or {}
    evaluation_detail = expanded.get("evaluation_detail") or {}
    restatement_text = text_field(front_detail, "restatement_detail") or front.get("restatement") or selection.get("reason") or ""
    problem_analysis_text = text_field(front_detail, "analysis_detail") or front.get("problem_analysis") or ""
    tex = rf"""\documentclass[UTF8,a4paper,zihao=-4]{{ctexart}}
\usepackage[margin=2.2cm]{{geometry}}
\usepackage{{amsmath,amssymb,booktabs,longtable,graphicx,float,hyperref,array}}
\usepackage{{setspace}}
\setstretch{{1.14}}
\setlength{{\parindent}}{{2em}}
\setlength{{\parskip}}{{0.22em}}
\setcounter{{secnumdepth}}{{3}}
\emergencystretch=10em
\tolerance=9000
\hbadness=4000
\sloppy
\pagestyle{{plain}}
\hypersetup{{hidelinks}}
\newcommand{{\eqnum}}{{\refstepcounter{{equation}}\eqno\hbox{{\normalfont(\theequation)}}}}

\begin{{document}}
\thispagestyle{{empty}}
\begin{{center}}
{{\zihao{{3}}\heiti {latex_escape(title)}}}
\end{{center}}

\noindent\textbf{{摘要：}} {markdown_to_latex(inline_text(abstract_text or "本文基于大模型对赛题材料进行当场分析，完成选题、模型设计、求解方案和论文撰写。"))}

\noindent\textbf{{关键词：}} {latex_escape("；".join(str(item) for item in keywords))}

\newpage
\setcounter{{page}}{{1}}
\phantomsection\label{{page:body-start}}

\section{{问题重述}}
{markdown_to_latex(restatement_text)}

\section{{问题分析}}
{markdown_to_latex(problem_analysis_text)}

\section{{模型假设}}
{markdown_to_latex(join_texts(front.get("assumptions") or "", text_field(front_detail, "assumption_detail")))}

\section{{符号说明}}
{symbol_table_latex()}
{markdown_to_latex(join_texts(front.get("symbols") or "", text_field(front_detail, "symbol_detail")))}

\section{{模型建立}}
{literature_method_basis_latex(selection, references, reference_labels)}
{markdown_to_latex(join_texts(text_field(data_feature, "content"), text_field(model_overview, "content"), model.get("model_building") or ""))}
{model_building_per_problem_latex(per_problem)}

\section{{模型求解}}
{markdown_to_latex(model.get("solving") or "")}
{solving_per_problem_latex(per_problem)}

\section{{模型检验}}
{markdown_to_latex(join_texts(model.get("validation") or "", text_field(validation_detail, "content")))}

\section{{模型评价与推广}}
{markdown_to_latex(join_texts(tail.get("evaluation") or "", text_field(evaluation_detail, "content")))}

\section{{参考文献}}
\begin{{thebibliography}}{{99}}
{reference_items}
\end{{thebibliography}}

\clearpage
\phantomsection\label{{page:appendix-start}}
\appendix
\section{{附录与复现说明}}
{markdown_to_latex(tail.get("appendix") or "附录应包含原始数据、程序、公式推导、图表清单和 AI 工具使用说明。")}

\end{{document}}
"""
    return repair_latex_math_fragments(tex)


def paper_title_from_selection(selection: dict[str, Any], rec: dict[str, Any] | None = None) -> str:
    rec = rec or {}
    explicit = inline_text(selection.get("paper_title") or selection.get("title"))
    if explicit and explicit not in {"数学建模论文", "所选赛题"}:
        return explicit
    base = inline_text(selection.get("final_problem_title") or rec.get("title") or "数学建模问题")
    tasks_text = " ".join(normalize_tasks(selection))
    model_chain = " ".join(str(item) for item in selection.get("model_chain", []) if item)
    corpus = f"{base} {tasks_text} {model_chain}"
    if any(term in corpus for term in ["边坡", "位移", "孔压", "微震", "爆破", "预警"]):
        return "基于多源监测融合的边坡形变阶段识别与预警模型"
    if any(term in corpus for term in ["锚杆", "巷道", "预紧", "支护", "煤矿"]):
        return "煤矿巷道锚杆支护参数转换与稳定性评价模型"
    if any(term in corpus for term in ["物流", "集包", "分拣", "包裹", "格口", "产能", "设备"]):
        return "物流网络集包规则与设备配置优化模型"
    if any(term in corpus for term in ["调度", "工序", "排产", "资源", "优化"]):
        return "面向多工序生产的调度优化与资源配置模型"
    if any(term in corpus for term in ["预测", "分类", "融合", "评价"]):
        return f"基于数据驱动模型的{base}求解与评价"
    return base


def strict_skill_abstract(selection: dict[str, Any], abstract_text: Any) -> str:
    text = sanitize_abstract_text(inline_text(abstract_text))
    tasks = normalize_tasks(selection)
    has_chain = all(term in text for term in ["首先", "随后", "再", "最后"])
    has_fixed_problem_sentences = all(
        f"针对问题{index}，考虑" in text and "建立" in text and "采用" in text and "得到" in text
        for index in range(1, len(tasks) + 1)
    )
    has_reliability = any(term in text for term in ["可靠性", "模型检验", "敏感性", "稳定性", "交叉验证"])
    generic_markers = [
        "任务适配的数学模型",
        "建立数学模型并采用",
        "建立任务适配",
        "数据驱动的任务适配数学模型",
    ]
    concrete_method_markers = [
        "KMeans",
        "2-opt",
        "LPT",
        "TSP",
        "0-1",
        "整数优化",
        "混合整数",
        "时间序列",
        "ARIMA",
        "指数平滑",
        "分段回归",
        "变点",
        "鲁棒",
        "车辆路径",
        "负载均衡",
        "风险指数",
    ]
    has_concrete_method = any(term in text for term in concrete_method_markers)
    is_not_generic = not any(term in text for term in generic_markers)
    if has_chain and has_fixed_problem_sentences and has_reliability and has_concrete_method and is_not_generic:
        return text
    return sanitize_abstract_text(skill_abstract_text(selection))


def sanitize_abstract_text(text: Any) -> str:
    text = str(text or "")
    text = re.sub(r"([围绕针对关于基于])\s*[A-H]\s*题[“\"]([^”\"]+)[”\"]", r"\1\2", text)
    text = re.sub(r"([围绕针对关于基于])\s*[A-H]\s*题", r"\1赛题", text)
    text = re.sub(r"(?<!问题)[A-H]\s*题[“\"][^”\"]+[”\"]", "赛题", text)
    text = re.sub(r"(?<!问题)[A-H]\s*题", "赛题", text)
    text = re.sub(r"附件[一二三四五六七八九十\d]+[“\"][^”\"]+\.(?:xlsx|xls|csv|txt|pdf|docx)(?:::?Sheet\d+)?[^”\"]*[”\"]", "附件数据", text, flags=re.I)
    text = re.sub(r"[\w\u4e00-\u9fff（）()《》\-—·]+?\.(?:xlsx|xls|csv|txt|pdf|docx)(?:::?Sheet\d+)?", "附件数据", text, flags=re.I)
    text = re.sub(r"::\s*Sheet\d+", "", text, flags=re.I)
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip()


def safe_int(value: Any) -> int:
    try:
        return int(str(value).strip())
    except Exception:
        return 0


def text_field(payload: Any, key: str = "content") -> str:
    if isinstance(payload, dict):
        value = payload.get(key)
        if value is None:
            value = payload.get("content") or payload.get("raw") or payload.get("error") or ""
    else:
        value = payload
    if isinstance(value, list):
        return "\n".join(str(item) for item in value)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, indent=2)
    return str(value or "").strip()


def join_texts(*values: Any) -> str:
    return "\n\n".join(str(value).strip() for value in values if str(value or "").strip())


def normalize_tasks(selection: dict[str, Any]) -> list[str]:
    raw = selection.get("tasks")
    if isinstance(raw, list):
        tasks = [inline_text(item) for item in raw if inline_text(item)]
    else:
        text = str(raw or "")
        tasks = [inline_text(item) for item in re.split(r"[\n；;]+", text) if inline_text(item)]
    tasks = [task for task in tasks if not is_meta_paper_task(task)]
    tasks = merge_numbered_tasks(tasks)
    if not tasks:
        tasks = [
            "问题1：完成数据理解、预处理和基础变量构造",
            "问题2：建立核心数学模型并给出可复现求解流程",
            "问题3：完成模型检验、结果解释和决策输出",
        ]
    return tasks[:8]


def merge_numbered_tasks(tasks: list[str]) -> list[str]:
    grouped: dict[int, list[str]] = {}
    unnumbered: list[str] = []
    for task in tasks:
        index = task_problem_index(task)
        if index:
            grouped.setdefault(index, []).append(strip_task_problem_prefix(task))
        else:
            unnumbered.append(task)
    if not grouped:
        return tasks
    merged: list[str] = []
    for index in sorted(grouped):
        parts = [part for part in dict.fromkeys(grouped[index]) if part]
        merged.append(f"问题{index}：" + "；".join(parts))
    merged.extend(unnumbered)
    return merged


def task_problem_index(task: str) -> int:
    text = inline_text(task)
    match = re.search(r"(?:问题|Question|Problem)\s*([0-9]+)", text, flags=re.I)
    if not match:
        match = re.search(r"闂.{0,12}?([0-9]+)", text)
    return safe_int(match.group(1)) if match else 0


def strip_task_problem_prefix(task: str) -> str:
    text = inline_text(task)
    text = re.sub(r"^\s*(?:问题|Question|Problem)\s*[0-9]+\s*[：:、.\-]?\s*", "", text, flags=re.I)
    text = re.sub(r"^\s*闂.{0,12}?[0-9]+\s*[：:、.\-锛]*\s*", "", text)
    return text.strip() or inline_text(task)


def is_meta_paper_task(task: str) -> bool:
    text = inline_text(task)
    meta_markers = [
        "论文任务",
        "正文",
        "LaTeX",
        "图表紧跟",
        "模型建立只写",
        "模型求解按",
        "提交审查",
        "不得编造",
        "结果回填",
        "AI工具",
        "全流程",
        "代码规划",
        "manifest",
        "复核日志",
        "总控任务",
        "G1-G6",
    ]
    return any(marker in text for marker in meta_markers)


def front_subsections_latex(kind: str, tasks: list[str]) -> str:
    return ""


def symbol_table_latex() -> str:
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


def core_equations_latex() -> str:
    return ""


def model_building_per_problem_latex(per_problem: list[dict[str, Any]]) -> str:
    blocks = []
    for fallback_index, item in enumerate(per_problem, 1):
        index = safe_int(item.get("index")) or fallback_index
        task = inline_text(item.get("task") or f"问题{index}")
        content = text_field(item, "model_building") or fallback_model_building_text(index, task)
        blocks.append(
            f"\\subsection{{问题 {index} 模型建立}}\n"
            f"{markdown_to_latex(content)}\n\n"
            f"{algorithm_table_latex(index, task)}"
        )
    return "\n".join(blocks)


def solving_per_problem_latex(per_problem: list[dict[str, Any]]) -> str:
    blocks = []
    for fallback_index, item in enumerate(per_problem, 1):
        index = safe_int(item.get("index")) or fallback_index
        task = inline_text(item.get("task") or f"问题{index}")
        content = text_field(item, "solving") or fallback_solving_text(index, task)
        blocks.append(
            f"\\subsection{{问题 {index} 模型求解}}\n"
            f"\\noindent\\textbf{{求解目标：}} {latex_escape(task)}\n\n"
            f"\\subsubsection{{求解步骤与实现路径}}\n"
            f"{markdown_to_latex(content)}"
        )
    return "\n".join(blocks)


def algorithm_table_latex(index: int, task: str) -> str:
    return rf"""
\begin{{table}}[H]
\centering
\caption{{问题 {index} 的算法流程与输入输出}}
\begin{{tabular}}{{p{{0.18\textwidth}}p{{0.72\textwidth}}}}
\toprule
环节 & 内容\\
\midrule
输入 & {latex_escape(task)}；读取题目附件、前序清洗数据和必要的中间特征。\\
预处理 & 统一单位、对齐时间或编号、识别缺失与异常、生成滞后项和滑动统计量。\\
建模 & 根据子问题目标选择预测、统计学习、网络流、整数规划、仿真、分类或风险评估模型，写出目标函数与约束。\\
求解 & 采用网格搜索、交叉验证、滚动验证或代价敏感阈值寻优确定参数；所有数值由程序计算。\\
输出 & 保存结果表、图形文件、评价指标和可复现实验日志，并在论文中形成紧邻图表的自然判读段落。\\
\bottomrule
\end{{tabular}}
\end{{table}}
表中流程用于约束代码实现顺序，逐项明确每一步的输入、输出及其对数据噪声、模型偏差和信息泄漏风险的控制作用。由此可见，该子问题的模型建立必须先形成可复现的数据接口，再进入正式求解。
"""


def result_table_latex(index: int) -> str:
    return ""


def result_figure_latex(index: int) -> str:
    return ""


def validation_metrics_latex() -> str:
    return ""


def fallback_model_building_text(index: int, task: str) -> str:
    return (
        f"针对问题{index}，模型建立首先应明确输入变量、目标变量和约束条件。"
        f"该任务可概括为“{task}”。在数学表达上，设清洗后的输入为特征向量 x_t，输出为 y_t，"
        "模型需要在噪声、缺失和滞后影响存在的条件下估计映射 f(x_t)。"
        "目标函数采用经验损失加正则化项的形式，既控制拟合误差，也限制模型复杂度。"
        "若任务涉及时间序列，应采用滚动窗口或真实时间差计算导出特征；若任务涉及分类，应采用类别权重或阈值寻优处理类别不均衡。"
        "算法流程包括数据清洗、特征构造、候选模型训练、参数选择、对照验证和结果输出。"
    )


def fallback_solving_text(index: int, task: str) -> str:
    return (
        f"针对问题{index}，模型求解以“{task}”为目标。程序读取对应附件后，先完成单位统一、时间或编号对齐、缺失异常处理，"
        "再按模型建立部分定义的公式生成特征矩阵。随后在训练集或可用样本上拟合候选模型，并通过验证指标选择最终方案。"
        "求解结果不得手工填造，所有参数、误差、阶段节点、预测值或阈值均应由程序写入结果表。"
        "论文中需要把结果表和图形放在该子问题附近，并用自然段说明图表包含的内容、趋势或误差特征以及该子问题的直接结论。"
    )


def inline_text(value: Any) -> str:
    return " ".join(str(value or "").split())


def markdown_to_latex(value: Any) -> str:
    text = clean_final_paper_labels(str(value or "")).replace("\r\n", "\n").replace("\r", "\n")
    if not text.strip():
        return "待补充。"
    lines: list[str] = []
    in_itemize = False
    for raw in text.split("\n"):
        line = raw.strip()
        if not line:
            if in_itemize:
                lines.append("\\end{itemize}")
                in_itemize = False
            lines.append("")
            continue
        heading = re.match(r"^(#{1,4})\s+(.+)$", line)
        if heading:
            if in_itemize:
                lines.append("\\end{itemize}")
                in_itemize = False
            lines.append(f"\\subsection*{{{latex_escape(heading.group(2))}}}")
            continue
        bullet = re.match(r"^[-*]\s+(.+)$", line)
        if bullet:
            if not in_itemize:
                lines.append("\\begin{itemize}")
                in_itemize = True
            lines.append(f"  \\item {latex_text_preserving_math(bullet.group(1))}")
            continue
        numbered = re.match(r"^\d+[.)]\s+(.+)$", line)
        if numbered:
            if not in_itemize:
                lines.append("\\begin{itemize}")
                in_itemize = True
            lines.append(f"  \\item {latex_text_preserving_math(numbered.group(1))}")
            continue
        if in_itemize:
            lines.append("\\end{itemize}")
            in_itemize = False
        lines.append(latex_text_preserving_math(line) + "\n")
    if in_itemize:
        lines.append("\\end{itemize}")
    return "\n".join(lines)


def clean_final_paper_labels(text: str) -> str:
    """Remove backstage workflow labels before text enters the paper."""
    replacements = {
        "结果表格与图形解释": "模型求解结果",
        "结果组织与判读": "模型求解结果",
        "程序计算结果回填": "模型求解结果",
        "计算结果回填": "模型求解结果",
        "程序计算结果": "计算结果",
        "结果回填": "结果整合",
        "程序生成结果图": "模型结果图",
        "程序生成的结果表": "模型结果表",
        "描述部分": "",
        "分析部分": "",
        "结论部分": "",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    label_patterns = [
        r"(?:表格|图形|结果)?描述[:：]\s*",
        r"(?:表格|图形|结果)?分析[:：]\s*",
        r"(?:表格|图形|结果)?结论[:：]\s*",
    ]
    for pattern in label_patterns:
        text = re.sub(pattern, "", text)
    return text


MATH_RUN_PATTERN = re.compile(
    r"([A-Za-z0-9\\_{}\[\]\(\),.;:+\-*/=<>\s\|"
    r"αβγδεζηθικλμνξοπρστυφχψωΑΒΓΔΘΛΞΠΣΦΩ"
    r"≤≥∈∞∑√·ΔΩ]+)"
)

GREEK_TO_LATEX = {
    "ŷ": r"\hat{y}",
    "α": r"\alpha",
    "β": r"\beta",
    "γ": r"\gamma",
    "δ": r"\delta",
    "ε": r"\epsilon",
    "η": r"\eta",
    "θ": r"\theta",
    "λ": r"\lambda",
    "μ": r"\mu",
    "ξ": r"\xi",
    "π": r"\pi",
    "ρ": r"\rho",
    "σ": r"\sigma",
    "τ": r"\tau",
    "φ": r"\phi",
    "ω": r"\omega",
    "Δ": r"\Delta",
    "Ω": r"\Omega",
    "Σ": r"\sum",
    "≤": r"\le",
    "≥": r"\ge",
    "≠": r"\ne",
    "∈": r"\in",
    "∞": r"\infty",
    "∑": r"\sum",
    "√": r"\sqrt",
    "→": r"\to",
    "·": r"\cdot ",
    "ℓ": r"\ell",
}


def repair_latex_math_fragments(tex: str) -> str:
    """Repair common LLM math fragments after Markdown-to-LaTeX rendering."""
    text = clean_final_paper_labels(tex).replace(r"\tableofcontents", "")
    text = re.sub(r"\\setcounter\{tocdepth\}\{[^{}]*\}\s*", "", text)
    text = re.sub(r"\\pagestyle\{(?:headings|fancy)\}", r"\\pagestyle{plain}", text)

    replacements = {
        r"$L_1$(θ)=∑|$e_i$|": r"$L_1(\theta)=\sum_i |e_i|$",
        r"校正函数为h($x_A,t$;θ)": r"校正函数为$h(x_A,t;\theta)$",
        r"每段趋势函数$g_k$(t;$\theta_k$)": r"每段趋势函数$g_k(t;\theta_k)$",
        r"$\min_\theta$∑ρ($y_i-F_i\theta$)+λ$\lVert \theta\rVert_p$": r"$\min_\theta\sum_i\rho(y_i-F_i\theta)+\lambda\lVert \theta\rVert_p$",
        r"阶段标签为Y(t)∈\{1,2,3\}": r"阶段标签为$Y(t)\in\{1,2,3\}$",
        r"判别结果为$argmax_k$ $p_k(t)$": r"判别结果为$\arg\max_k p_k(t)$",
        r"函数f:$F_i$→$y_i$": r"函数$f:F_i\to y_i$",
        r"速度型特征$V_S(t)$=$\Delta S_t$/Δt": r"速度型特征$V_S(t)=\Delta S_t/\Delta t$",
        r"阈值优化目标可写为$\min_c$ $C_FN$·FN(c)+$C_FP$·FP(c)+$C_D$·D(c)": r"阈值优化目标可写为$\min_c C_{\mathrm{FN}}\mathrm{FN}(c)+C_{\mathrm{FP}}\mathrm{FP}(c)+C_{\mathrm{D}}\mathrm{D}(c)$",
        r"总体准确率为Accuracy=$Σ_k$ $N_{kk}$/$Σ_{k,l}$$N_{kl}$": r"总体准确率为$\operatorname{Accuracy}=\sum_k N_{kk}/\sum_{k,l}N_{kl}$",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)

    regex_replacements: list[tuple[str, str]] = [
        (
            r"\$\\min_F\$\s+\$sum_\{t\$\s+in\s+train\\?\}\s+L\(\$y_t,F\(f_t\)\$\)\+Ω\(F\)",
            r"$\min_F \sum_{t\in \mathrm{train}} L(y_t,F(f_t))+\Omega(F)$",
        ),
        (
            r"\$\\min_\{\\hat\{y\}\}\$\s*-\$Σ_i\$\s*log\s*\$p_\{i,\\hat\{y\}_i\}\+\\gammaΣ_\{i = 2\}\^n I\(\$\$\\hat\{y\}_i\$≠\$\\hat\{y\}_\{i-1\}\)\+\\etaΣ_\{i = 2\}\^n C\(\$\$\\hat\{y\}_\{i-1\}\$,\$\\hat\{y\}_i\$\)",
            r"$\min_{\hat{y}}-\sum_i \log p_{i,\hat{y}_i}+\gamma\sum_{i=2}^{n} I(\hat{y}_i\ne\hat{y}_{i-1})+\eta\sum_{i=2}^{n} C(\hat{y}_{i-1},\hat{y}_i)$",
        ),
        (
            r"\$p_\{ik\} = exp\(\\beta_k\^T F_i\)/Σ_l exp\(\\beta_l\^T F_i\)\$",
            r"$p_{ik}=\exp(\beta_k^T F_i)/\sum_l\exp(\beta_l^T F_i)$",
        ),
        (
            r"\$\\min_\\beta -Σ_iΣ_k I\(y_i = k\)log p_\{ik\}\+\\lambda\\Omega\(\\beta\)\$",
            r"$\min_\beta -\sum_i\sum_k I(y_i=k)\log p_{ik}+\lambda\Omega(\beta)$",
        ),
        (
            r"L=\$Σ_i\$\s*ℓ\(\$y_i,f\(F_i\)\$\)\+Ω\(f\)",
            r"$L=\sum_i \ell(y_i,f(F_i))+\Omega(f)$",
        ),
        (
            r"\$Precision_k = N_\{kk\}/Σ_l N_\{lk\}\$",
            r"$\operatorname{Precision}_k=N_{kk}/\sum_l N_{lk}$",
        ),
        (
            r"\$Recall_k = N_\{kk\}/Σ_l N_\{kl\}\$",
            r"$\operatorname{Recall}_k=N_{kk}/\sum_l N_{kl}$",
        ),
        (
            r"\$F1_k = 2Precision_k Recall_k / \(Precision_k \+ Recall_k\)\$",
            r"$F1_k=2\operatorname{Precision}_k\operatorname{Recall}_k/(\operatorname{Precision}_k+\operatorname{Recall}_k)$",
        ),
        (
            r"\$A_R\(t,w\) = sum_\{i = 0\}\^\{w-1\}R_\{t-i\}\$",
            r"$A_R(t,w)=\sum_{i=0}^{w-1}R_{t-i}$",
        ),
        (
            r"\$\\min_\{\\beta_0,\\beta\} sum_\{t in train\}\(([^$]+?)\)\^2\+\\lambda\\lVert \\beta\\rVert_2\^2\$",
            r"$\min_{\beta_0,\beta}\sum_{t\in\mathrm{train}}(\1)^2+\lambda\lVert \beta\rVert_2^2$",
        ),
        (
            r"\$\\min_\{\\beta_0,\\beta\} sum_\{t in train\}\(([^$]+?)\)\^2\+\\lambda\\lVert \\beta\\rVert_1\$",
            r"$\min_{\beta_0,\beta}\sum_{t\in\mathrm{train}}(\1)^2+\lambda\lVert \beta\rVert_1$",
        ),
    ]
    for pattern, replacement in regex_replacements:
        text = re.sub(pattern, lambda match, repl=replacement: expand_plain_replacement(match, repl), text)

    text = normalize_math_blocks_in_tex(text)
    text = repair_post_normalized_math_fragments(text)
    text = promote_standalone_inline_formulas(text)
    text = number_display_equations(text)
    return text


def number_display_equations(tex: str) -> str:
    """Add equation numbers to every standalone ``$$...$$`` display formula."""
    added_number = False

    def repl(match: re.Match[str]) -> str:
        body = match.group(1).strip()
        if not body:
            return match.group(0)
        if any(marker in body for marker in [r"\eqno", r"\tag{", r"\notag", r"\nonumber"]):
            return match.group(0)
        if has_unclosed_latex_environment(body):
            return match.group(0)
        clean_body = re.sub(r"\s*\\eqnum\s*$", "", body).strip()
        nonlocal added_number
        added_number = True
        return "$$" + clean_body.rstrip() + r"\eqnum" + "\n$$"

    updated = re.sub(r"\$\$\s*([\s\S]*?)\s*\$\$", repl, tex)
    if added_number and r"\newcommand{\eqnum}" not in updated:
        updated = updated.replace(
            r"\hypersetup{hidelinks}",
            r"\hypersetup{hidelinks}" + "\n" + r"\newcommand{\eqnum}{\refstepcounter{equation}\eqno\hbox{\normalfont(\theequation)}}",
            1,
        )
    return updated


def has_unclosed_latex_environment(body: str) -> bool:
    stack: list[str] = []
    for match in re.finditer(r"\\(begin|end)\{([A-Za-z*]+)\}", body):
        action, name = match.groups()
        if action == "begin":
            stack.append(name)
        elif stack and stack[-1] == name:
            stack.pop()
        else:
            return True
    return bool(stack)


STANDALONE_FORMULA_SKIP_ENVIRONMENTS = {
    "algorithm",
    "enumerate",
    "figure",
    "itemize",
    "lstlisting",
    "longtable",
    "table",
    "tabular",
    "verbatim",
}


def promote_standalone_inline_formulas(tex: str) -> str:
    """Promote formula-only lines written with ``$...$`` into display math blocks."""
    lines = tex.splitlines()
    rendered: list[str] = []
    env_stack: list[str] = []
    in_display_math = False

    for raw_line in lines:
        line = raw_line.rstrip()
        stripped = line.strip()
        begin_env = re.match(r"\\begin\{([A-Za-z*]+)\}", stripped)
        end_env = re.match(r"\\end\{([A-Za-z*]+)\}", stripped)
        if begin_env:
            rendered.append(line)
            env_stack.append(begin_env.group(1))
            continue
        if end_env:
            rendered.append(line)
            if env_stack and env_stack[-1] == end_env.group(1):
                env_stack.pop()
            continue
        if "$$" in stripped:
            rendered.append(line)
            if stripped.count("$$") % 2 == 1:
                in_display_math = not in_display_math
            continue
        if not stripped:
            rendered.append(line)
            continue
        if in_display_math or any(env in STANDALONE_FORMULA_SKIP_ENVIRONMENTS for env in env_stack):
            rendered.append(line)
            continue
        if is_standalone_inline_formula_line(stripped):
            display = format_display_math(normalize_standalone_inline_formula_line(stripped))
            if rendered and rendered[-1] != "":
                rendered.append("")
            rendered.append(display)
            rendered.append("")
            continue
        rendered.append(line)
    return "\n".join(rendered)


def is_standalone_inline_formula_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped or "$" not in stripped:
        return False
    if stripped.startswith("$$") or stripped.endswith("$$"):
        return False
    if re.match(r"\\(?:section|subsection|subsubsection|paragraph|caption|label|item|begin|end|includegraphics|textbf|textit|centering)\b", stripped):
        return False
    if re.search(r"[\u4e00-\u9fff]", re.sub(r"\\text\{[^{}]*\}", "", stripped)):
        return False
    candidate = stripped.replace("$", "")
    candidate = candidate.replace(r"\textbackslash{}\textbackslash{}", "")
    candidate = candidate.replace(r"\textbackslash{}", "")
    candidate = candidate.replace(r"\&", "")
    candidate = re.sub(r"\\text\{[^{}]*\}", "", candidate)
    candidate = re.sub(r"\\[A-Za-z]+", "", candidate)
    candidate = re.sub(r"[\\{}&,.;:，。；、\s\[\]\(\)\|]+", "", candidate)
    candidate = re.sub(r"[0-9A-Za-z_+\-*/=<>\^≤≥≠∀∈∑∏∫→×−·√]+", "", candidate)
    if candidate:
        return False
    return bool(re.search(r"[=<>≤≥≠∀∈\+\-*/^]|\\(?:min|max|sum|forall|exists|frac|sqrt|operatorname)", stripped))


def normalize_standalone_inline_formula_line(line: str) -> str:
    text = line.strip()
    text = text.replace("$", "")
    text = text.replace(r"\textbackslash{}\textbackslash{}", r"\\")
    text = text.replace(r"\textbackslash{}", r"\quad ")
    text = text.replace(r"\&", "&")
    text = text.replace("≥", r"\geq")
    text = text.replace("≤", r"\leq")
    text = text.replace("≠", r"\ne")
    text = text.replace("∀", r"\forall ")
    text = text.replace("∈", r"\in ")
    text = text.replace("∑", r"\sum")
    text = text.replace("∏", r"\prod")
    text = text.replace("∫", r"\int")
    text = text.replace("→", r"\to ")
    text = text.replace("×", r"\times ")
    text = text.replace("−", "-")
    text = text.replace("·", r"\cdot ")
    text = text.replace("√", r"\sqrt{}")
    text = re.sub(r"\\text\{([^{}]*)\}", lambda match: rf"\text{{{match.group(1).strip()}}}", text)
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\s*([,，；;。\.])\s*$", "", text)
    text = re.sub(r"\\\\(?=\S)", r"\\\\ ", text)
    text = re.sub(r"\s{2,}", " ", text).strip()
    return normalize_formula_for_latex(text)


def should_number_display_equation(body: str) -> bool:
    compact = re.sub(r"\s+", "", body)
    if len(compact) < 45:
        return False
    if re.fullmatch(r"[A-Za-z0-9_{}\\,\.\^\-\+\s=]+", body) and not any(op in body for op in [r"\sum", r"\min", r"\max"]):
        return False
    core_markers = [
        r"\min",
        r"\max",
        r"\operatorname{arg",
        r"\forall",
        r"\sum",
        r"\prod",
        r"\int",
        r"\begin{aligned}",
        r"\begin{cases}",
    ]
    if any(marker in body for marker in core_markers):
        return True
    if any(marker in body for marker in [r"\le", r"\ge", r"\leq", r"\geq"]) and len(compact) >= 65:
        return True
    if any(marker in body for marker in [r"\arcsin", r"\sqrt"]) and len(compact) >= 70:
        return True
    if "A_" in body and "L_" in body and r"\tau" in body:
        return True
    return False


def expand_plain_replacement(match: re.Match[str], replacement: str) -> str:
    result = replacement
    for index, group in enumerate(match.groups(), 1):
        result = result.replace(fr"\{index}", group or "")
    return result


def repair_post_normalized_math_fragments(tex: str) -> str:
    replacements = {
        r"判别结果为$\arg\max _k$ $p_k(t)$": r"判别结果为$\arg\max_k p_k(t)$",
        r"非线性模型的目标可统一写为$\min_F$ $\sum_{t$ in train\} L($y_t,F(f_t)$)+Ω(F)": r"非线性模型的目标可统一写为$\min_F \sum_{t\in \mathrm{train}} L(y_t,F(f_t))+\Omega(F)$",
        r"学习目标可写为逐步最小化分类损失L=$\sum_i$ ℓ($y_i,f(F_i)$)+Ω(f)": r"学习目标可写为逐步最小化分类损失$L=\sum_i \ell(y_i,f(F_i))+\Omega(f)$",
        r"可构造目标函数$\min _{\hat{y}}$ -$\sum_i$ log $p_{i,\hat{y}_i} + \gamma\sum _{i = 2}^n I($$\hat{y}_i$≠$\hat{y}_{i-1}) + \eta\sum _{i = 2}^n C($$\hat{y}_{i-1}$,$\hat{y}_i$)": r"可构造目标函数$\min_{\hat{y}}-\sum_i \log p_{i,\hat{y}_i}+\gamma\sum_{i=2}^{n} I(\hat{y}_i\ne\hat{y}_{i-1})+\eta\sum_{i=2}^{n} C(\hat{y}_{i-1},\hat{y}_i)$",
        r"总体准确率为Accuracy=$\sum_k$ $N_{kk}$/$\sum_{k,l}$$N_{kl}$": r"总体准确率为$\operatorname{Accuracy}=\sum_k N_{kk}/\sum_{k,l}N_{kl}$",
        r"$D_train = {(x_t,y_t)}$": r"$D_{\mathrm{train}}=\{(x_t,y_t)\}$",
        r"$D_test = {x_t}$": r"$D_{\mathrm{test}}=\{x_t\}$",
        "τ1和τ2": r"$\tau_1$和$\tau_2$",
        "τ1、τ2": r"$\tau_1$、$\tau_2$",
        "θ表示": r"$\theta$表示",
        "其中ρ": r"其中$\rho$",
        "，Ω(θ)": r"，$\Omega(\theta)$",
        "J(τ)": r"$J(\tau)$",
        "B(θ)": r"$B(\theta)$",
        "参数λ": r"参数$\lambda$",
        "其中ε": r"其中$\epsilon$",
        "阶段平滑参数γ、η": r"阶段平滑参数$\gamma$、$\eta$",
        "当Ω取": r"当$\Omega$取",
        "其中ℓ": r"其中$\ell$",
        "Ω控制": r"$\Omega$控制",
        "Ω(F)表示": r"$\Omega(F)$表示",
        "估计λ": r"估计$\lambda$",
        "时间间隔为Δt": r"时间间隔为$\Delta t$",
        "位移增量ΔS": r"位移增量$\Delta S$",
        "，ε用于": r"，$\epsilon$用于",
        "其中γ为": r"其中$\gamma$为",
    }
    text = tex
    for old, new in replacements.items():
        text = text.replace(old, new)
    text = text.replace(r"\le ft", r"\left")
    return text


def normalize_math_blocks_in_tex(tex: str) -> str:
    parts = re.split(r"(\$\$.*?\$\$|\$[^$\n]+\$)", tex, flags=re.S)
    rendered: list[str] = []
    for part in parts:
        if part.startswith("$$") and part.endswith("$$"):
            rendered.append("$$" + normalize_formula_for_latex(part[2:-2]) + "$$")
        elif part.startswith("$") and part.endswith("$"):
            rendered.append("$" + normalize_formula_for_latex(part[1:-1]) + "$")
        else:
            rendered.append(part)
    return "".join(rendered)


def latex_text_preserving_math(text: str) -> str:
    """Escape prose while keeping explicit display formulas as $$...$$ blocks."""
    if "$" in text:
        parts = re.split(r"(\$\$.*?\$\$|\$[^$]+\$)", text, flags=re.S)
        rendered = []
        for part in parts:
            if part.startswith("$$") and part.endswith("$$"):
                rendered.append(format_display_math(part[2:-2]))
            elif part.startswith("$") and part.endswith("$"):
                rendered.append(format_inline_math(part[1:-1]))
            else:
                rendered.append(latex_escape_with_math_fragments(part))
        return "".join(rendered)
    return latex_escape_with_math_fragments(text)


LATEX_COMMAND_FORMULA_PATTERN = re.compile(
    r"(?<![A-Za-z])("
    r"(?:\\[A-Za-z]+|\\[{}]|[A-Za-z0-9_{}()[\],.;:+\-*/=<>\s\|^·≤≥∈∞∑√…αβγδεζηθικλμνξοπρστυφχψωΑΒΓΔΘΛΞΠΣΦΩ])+"
    r")"
)

SUBSCRIPT_FORMULA_PATTERN = re.compile(
    r"(?<![A-Za-z])("
    r"[A-Za-zŷαβγδεζηθικλμνξοπρστυφχψωΑΒΓΔΘΛΞΠΣΦΩ][A-Za-z0-9ŷαβγδεζηθικλμνξοπρστυφχψωΑΒΓΔΘΛΞΠΣΦΩ]*"
    r"(?:_\{?[A-Za-z0-9,+\-ŷαβγδεζηθικλμνξοπρστυφχψωΑΒΓΔΘΛΞΠΣΦΩ]+\}?|\^\{?[A-Za-z0-9,+\-*]+\}?)+"
    r"(?:\([A-Za-z0-9_,+\-{} ]+\))?"
    r")"
)

EQUALITY_FORMULA_PATTERN = re.compile(
    r"(?<![A-Za-z])("
    r"[A-Za-z0-9_{}()[\],.;:+\-*/=<>\s\|^·≤≥∈∞∑√…αβγδεζηθικλμνξοπρστυφχψωΑΒΓΔΘΛΞΠΣΦΩ]+"
    r"[=<>≤≥]"
    r"[A-Za-z0-9_{}()[\],.;:+\-*/=<>\s\|^·≤≥∈∞∑√…αβγδεζηθικλμνξοπρστυφχψωΑΒΓΔΘΛΞΠΣΦΩ]+"
    r")"
)

POWER_FORMULA_PATTERN = re.compile(
    r"(?<![A-Za-z])("
    r"[A-Za-z0-9_{}()[\],.;:+\-*/=<>\s\|^·≤≥∈∞∑√…αβγδεζηθικλμνξοπρστυφχψωΑΒΓΔΘΛΞΠΣΦΩ]+"
    r"\^"
    r"[A-Za-z0-9_{}()[\],.;:+\-*/=<>\s\|^·≤≥∈∞∑√…αβγδεζηθικλμνξοπρστυφχψωΑΒΓΔΘΛΞΠΣΦΩ]+"
    r")"
)

NORM_FORMULA_PATTERN = re.compile(r"(\|\|[^，,。；;：:\s]+?\|\|_\{?[A-Za-z0-9,+\-]+\}?)")


def latex_escape_with_math_fragments(text: str) -> str:
    """Escape prose while turning unwrapped formula fragments into inline math."""
    if not text:
        return ""
    spans = formula_fragment_spans(text)
    if not spans:
        return latex_escape(soften_inline_formula_text(text))
    pieces: list[str] = []
    cursor = 0
    for start, end in spans:
        if start < cursor:
            continue
        if start > cursor:
            pieces.append(latex_escape(soften_inline_formula_text(text[cursor:start])))
        pieces.append(format_inline_math(text[start:end]))
        cursor = end
    if cursor < len(text):
        pieces.append(latex_escape(soften_inline_formula_text(text[cursor:])))
    return "".join(pieces)


def formula_fragment_spans(text: str) -> list[tuple[int, int]]:
    candidates: list[tuple[int, int]] = []
    for match in LATEX_COMMAND_FORMULA_PATTERN.finditer(text):
        start, end = trim_formula_span(text, match.start(1), match.end(1))
        fragment = text[start:end]
        if start < end and re.search(r"\\[A-Za-z]+", fragment):
            candidates.append((start, end))
    for match in EQUALITY_FORMULA_PATTERN.finditer(text):
        start, end = trim_formula_span(text, match.start(1), match.end(1))
        fragment = text[start:end]
        if start < end and re.search(r"[A-Za-z0-9)}\]]\s*[=<>≤≥]\s*[A-Za-z0-9\\({\[]", fragment):
            candidates.append((start, end))
    for match in POWER_FORMULA_PATTERN.finditer(text):
        start, end = trim_formula_span(text, match.start(1), match.end(1))
        if start < end:
            candidates.append((start, end))
    for match in SUBSCRIPT_FORMULA_PATTERN.finditer(text):
        start, end = trim_formula_span(text, match.start(1), match.end(1))
        if start < end:
            candidates.append((start, end))
    for match in NORM_FORMULA_PATTERN.finditer(text):
        start, end = trim_formula_span(text, match.start(1), match.end(1))
        if start < end:
            candidates.append((start, end))
    if not candidates:
        return []
    candidates.sort(key=lambda item: (item[0], -(item[1] - item[0])))
    merged: list[tuple[int, int]] = []
    for start, end in candidates:
        if not merged or start >= merged[-1][1]:
            merged.append((start, end))
        elif end > merged[-1][1]:
            merged[-1] = (merged[-1][0], end)
    return merged


def trim_formula_span(text: str, start: int, end: int) -> tuple[int, int]:
    while start < end and text[start] in " ，,。；;：:、":
        start += 1
    while end > start and text[end - 1] in " ，,。；;：:、":
        end -= 1
    return start, end


def should_protect_formula_fragment(fragment: str) -> bool:
    formula = fragment.strip()
    if not formula:
        return False
    if re.search(r"\\[A-Za-z]+", formula):
        return True
    if re.search(r"[A-Za-z0-9)}\]]\s*[=<>≤≥]\s*[A-Za-z0-9\\({\[]", formula):
        return True
    if re.search(r"[A-Za-z][A-Za-z0-9]*(?:_\{?[A-Za-z0-9,+\-]+\}?|\^\{?[A-Za-z0-9,+\-]+\}?)+", formula):
        return True
    return False


def format_inline_math(formula: str) -> str:
    normalized = normalize_formula_for_latex(formula)
    if not normalized:
        return ""
    return f"${normalized}$"


def auto_wrap_formula_segments(text: str) -> str:
    matches = []
    for match in MATH_RUN_PATTERN.finditer(text):
        candidate = match.group(1).strip()
        if is_formula_candidate(candidate):
            matches.append((match.start(1), match.end(1), candidate))
    if not matches:
        return latex_escape(soften_inline_formula_text(text))
    pieces = []
    cursor = 0
    for start, end, formula in matches:
        if start < cursor:
            continue
        prefix = text[cursor:start]
        pieces.append(latex_escape(prefix))
        pieces.append(format_display_math(formula))
        cursor = end
    pieces.append(latex_escape(text[cursor:]))
    return "".join(pieces)


def is_formula_candidate(candidate: str) -> bool:
    formula = candidate.strip(" ，,。；;：:")
    if len(formula) < 8:
        return False
    strong_markers = ["=", r"\sum", r"\frac", r"\min", r"\arg", r"\Pr", "≤", "≥", "∈", "<", ">"]
    if any(marker in formula for marker in strong_markers):
        return True
    marker_count = sum(formula.count(marker) for marker in ["_", "\\", "^", "+", "/", "*"])
    has_digit_or_greek = bool(re.search(r"[0-9αβγδεζηθικλμνξοπρστυφχψωΑΒΓΔΘΛΞΠΣΦΩ]", formula))
    return marker_count >= 2 and has_digit_or_greek


def format_display_math(formula: str) -> str:
    normalized = normalize_formula_for_latex(formula)
    if not normalized:
        return ""
    return f"$$\n{normalized}\n$$"


def normalize_formula_for_latex(formula: str) -> str:
    text = formula.strip(" ，,。；;：:")
    unicode_replacements = {
        "≤": r"\leq",
        "≥": r"\geq",
        "≠": r"\ne",
        "∀": r"\forall ",
        "∈": r"\in ",
        "∑": r"\sum",
        "∏": r"\prod",
        "∫": r"\int",
        "→": r"\to ",
        "×": r"\times ",
        "−": "-",
        "·": r"\cdot ",
        "√": r"\sqrt{}",
    }
    for source, target in unicode_replacements.items():
        text = text.replace(source, target)
    text = soften_inline_formula_text(text)
    text = re.sub(r"\|\|(.+?)\|\|(_\{?[A-Za-z0-9,+\-]+\}?)?", r"\\lVert \1\\rVert\2", text)
    for source, target in GREEK_TO_LATEX.items():
        text = text.replace(source, target)
    text = text.replace(r"\_", "_")
    text = text.replace(r"\logic", r"\mathrm{logic}")
    text = re.sub(r"(?<!\\)\bsum\s*_", r"\\sum_", text)
    text = re.sub(r"\\sum_\{([^{}]*?)\s+in\s+([^{}]*?)\}", r"\\sum_{\1\\in \\mathrm{\2}}", text)
    text = re.sub(r"\\sum_\{([^{}]*?)\s*=\s*([^{}]*?)\}", r"\\sum_{\1=\2}", text)
    text = re.sub(r"(?<!\\)\blog(?=\s|[A-Za-z_\\])", r"\\log", text)
    text = re.sub(r"(?<!\\)\bexp\s*\(", r"\\exp(", text)
    text = re.sub(r"(?<!\\)\bargmax\s*_", r"\\arg\\max_", text)
    text = re.sub(r"\by_hat_([A-Za-z0-9]+)\b", r"\\hat{y}_\1", text)
    text = re.sub(r"\by_hat\b", r"\\hat{y}", text)
    text = text.replace("…", r"\ldots")
    text = re.sub(
        r"(\\(?:alpha|beta|gamma|delta|epsilon|eta|theta|lambda|mu|xi|pi|rho|sigma|tau|phi|omega|Delta|Omega|sum|in))(?=[A-Za-z])",
        r"\1 ",
        text,
    )
    text = re.sub(r"(?<!\\)\bPr\s*\(", r"\\Pr(", text)
    text = re.sub(r"(?<!\\)\bcorr\s*\(", r"\\operatorname{corr}(", text)
    text = re.sub(r"(?<!\\)\bsoftmax\s*\(", r"\\operatorname{softmax}(", text)
    text = re.sub(r"(?<!\\)\bSigmoid\s*\(", r"\\operatorname{Sigmoid}(", text)
    text = re.sub(r"(?<!\\)\bmin_", r"\\min_", text)
    text = re.sub(r"(?<!\\)\bargmin\b", r"\\arg\\min", text)
    text = text.replace("...", r"\ldots")
    text = repair_text_macro_closures(text)
    return text.strip()


def repair_text_macro_closures(text: str) -> str:
    r"""Fix generated math like ``\text{label\})`` into ``\text{label})``."""
    return re.sub(r"(\\text\{[^{}\\]*)\\\}(\s*[\)\]\},;+\-*/=<>\^_]|$)", r"\1}\2", text)


def soften_inline_formula_text(text: str) -> str:
    """Add break-friendly spaces inside formula-like prose before LaTeX escaping."""
    formula_markers = ["_", "\\", "^", "=", "+", "/", "*", "<", ">"]
    if sum(text.count(marker) for marker in formula_markers) < 3:
        return text
    softened = re.sub(r"(?<=[A-Za-z0-9_\}\)\]])([=+*/<>])(?=[A-Za-z0-9_\\\{\(\[])", r" \1 ", text)
    softened = re.sub(r"(?<=[A-Za-z0-9_\}\)\]])([=+*/<>])(?=\s*\\)", r" \1 ", softened)
    softened = re.sub(r"(\\[A-Za-z]{1,20})_", r"\1 _", softened)
    softened = re.sub(r"\s{2,}", " ", softened)
    return softened


def build_solution_prompt(analysis: dict[str, Any], paper_options: dict[str, Any]) -> str:
    rec = analysis.get("recommended_problem", {}) or {}
    context = {
        "analysis": compact_analysis(analysis),
        "inventory": compact_inventory(analysis.get("inventory", [])),
        "paper_options": paper_options,
    }
    target_pages = paper_options.get("target_body_pages")
    target_note = f"论文正文目标不少于 {target_pages} 页。" if target_pages else "未设置正文页数下限。"
    return f"""你是一个数学建模竞赛自动解题系统。用户要求：不要使用固定的本地基线模型或专项建模脚本替代思考；一切建模分析、选题、模型设计、求解叙述和论文撰写均由大模型当场完成，后续会由软件根据你的方案运行代码计算数值结果。

用户已确认选题为：{rec.get("id", "-")} 题，{rec.get("title", "")}。不得自行改选其他题目。

请基于下方赛题解析、文档预览、数据表结构和格式要求，完成完整中文题解方案。必须遵守：
1. 围绕用户确认的题目给出选题理由、任务拆解与完整题解，不要重新选择其他题目。
2. 对最终选题逐个子问题给出问题重述、问题分析、模型假设、符号、模型建立、求解算法、结果应如何得到、模型检验、评价推广。
3. 不能编造已经计算出的精确数值；若原始上下文没有给出数值结果，只能写“需由数据计算得到”或给出可复现计算公式。
4. 模型建立只写数学原理、变量、目标函数、约束和算法，不写结果。
5. 公式既要有段内内联公式，也要有独占一行的显式公式；内联公式使用 $...$，所有独立公式必须使用 $$...$$ 包裹，公式内部使用标准 LaTeX 语法，不要把公式写成被转义的普通文本，显式公式会自动编号。
6. 模型求解必须按子问题组织，并说明应生成哪些表格和图片，以及图表后如何用自然段完成内容交代、结果判读和结论落点；不要使用带冒号的固定图表解读标签。
7. {target_note}
8. 输出中文 Markdown，结构要足够详细，可直接作为 LaTeX 论文生成依据。

输入上下文 JSON：
```json
{json.dumps(context, ensure_ascii=False, indent=2)}
```
"""


def build_latex_prompt(analysis: dict[str, Any], solution: str, paper_options: dict[str, Any]) -> str:
    rec = analysis.get("recommended_problem", {})
    target_pages = paper_options.get("target_body_pages")
    target_note = f"正文内容不得少于 {target_pages} 页；正文不包含摘要和附录，且不生成目录页。" if target_pages else "正文页数不设硬性下限，且不生成目录页。"
    return f"""请将下面的 LLM 题解方案改写为一份可用 XeLaTeX 编译的中文数学建模竞赛论文。

硬性要求：
1. 只输出一个完整 LaTeX 文档，使用 ctexart，包含 \\documentclass 到 \\end{{document}}。
2. 必须包含：摘要、关键词、问题重述、问题分析、模型假设、符号说明、模型建立、模型求解、模型检验、模型评价与推广、参考文献、附录；不要生成目录，不要使用页眉。
3. 摘要不得出现A题/B题/C题等题号字母，也不得出现具体文件名、路径或Sheet名；每个问题的结果必须写在“针对问题X，考虑……建立……采用……得到……”句子的“得到”后面。
4. 问题重述和问题分析必须按每个子问题分别叙述，直接使用充分展开的分问题段落，不额外添加“任务概括”或短概括段。
5. 模型建立只写数学模型原理和算法，不写结果内容。
6. 模型求解按每个模型或子问题分别设置小节；如果缺少可计算数值，不要编造结果，写明需由数据表计算得到，并给出计算公式和伪代码。
7. 每张表和图即使是建议性占位，也必须紧跟自然判读段落；段落要同时交代表图内容、主要现象和结论，不得使用带冒号的模板化标签。
8. 必须设置正文页数标签：正文开始处写 \\phantomsection\\label{{page:body-start}}；附录前写 \\clearpage\\phantomsection\\label{{page:appendix-start}}。
9. {target_note}
10. 不要输出 Markdown 解释，不要包裹多余文字；可以使用 ```latex fenced code，但代码块中必须是完整文档。

程序初步推荐题：{rec.get("id", "-")} 题 {rec.get("title", "")}

LLM 题解方案：
```markdown
{solution}
```
"""


def compact_inventory(inventory: list[dict[str, Any]]) -> list[dict[str, Any]]:
    compact = []
    for item in inventory[:80]:
        compact.append(
            {
                "path": item.get("path"),
                "kind": item.get("kind"),
                "suffix": item.get("suffix"),
                "size": item.get("size"),
                "schema": item.get("schema"),
                "text_preview": item.get("text_preview"),
                "char_count": item.get("char_count"),
            }
        )
    return compact


def extract_latex_document(text: str) -> str:
    fenced = re.search(r"```(?:latex|tex)?\s*(\\documentclass[\s\S]*?\\end\{document\})\s*```", text, re.I)
    if fenced:
        return fenced.group(1).strip()
    start = text.find(r"\documentclass")
    end = text.rfind(r"\end{document}")
    if start >= 0 and end >= start:
        return text[start : end + len(r"\end{document}")].strip()
    return ""


def fallback_latex_from_solution(analysis: dict[str, Any], solution: str) -> str:
    rec = analysis.get("recommended_problem", {})
    title = latex_escape(rec.get("title") or "数学建模论文")
    body = latex_escape(solution[:18000])
    return rf"""\documentclass[UTF8,a4paper,zihao=-4]{{ctexart}}
\usepackage[margin=2.2cm]{{geometry}}
\usepackage{{amsmath,amssymb,booktabs,longtable,graphicx,float,hyperref}}
\usepackage{{setspace}}
\setstretch{{1.15}}
\pagestyle{{plain}}
\hypersetup{{hidelinks}}

\begin{{document}}
\begin{{center}}
{{\zihao{{3}}\heiti {title}}}
\end{{center}}

\noindent\textbf{{摘要：}} 本文基于大模型对赛题材料的当场分析形成题解方案。由于当前 LaTeX 文档为兜底生成版本，正式提交前需人工核对数值结果、图表和格式。

\noindent\textbf{{关键词：}} 数学建模；大模型辅助；自动论文生成

\newpage
\setcounter{{page}}{{1}}
\phantomsection\label{{page:body-start}}

\section{{LLM 题解方案}}
\begin{{verbatim}}
{body}
\end{{verbatim}}

\clearpage
\phantomsection\label{{page:appendix-start}}
\appendix
\section{{说明}}
本附录记录大模型生成失败后的兜底 LaTeX 内容。正式论文应使用 artifacts/llm_full_solution.md 进一步整理。
\end{{document}}
"""


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
        payload.get("content") or "",
        "",
    ]
    return "\n".join(lines)


def public_settings(settings: dict[str, Any]) -> dict[str, Any]:
    return {
        key: settings.get(key)
        for key in [
            "provider",
            "configured",
            "source",
            "masked_api_key",
            "base_url",
            "model",
            "workflow_strategy",
            "workflow_strategy_label",
        ]
    }
