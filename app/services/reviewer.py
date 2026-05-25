from __future__ import annotations

import json
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

from app.services.templates import DEFAULT_TEMPLATE_ID, get_template


Check = dict[str, Any]


REQUIRED_SECTIONS = [
    "问题重述",
    "问题分析",
    "模型假设",
    "符号说明",
    "模型建立",
    "模型求解",
    "模型检验",
    "模型评价与推广",
    "参考文献",
]

RESULT_PHRASES_IN_MODEL_BUILDING = [
    "验证结果",
    "预测结果",
    "结果表明",
    r"由表\s*\d",
    r"由表\s*\\ref",
    "由表可知",
    "由图",
    r"表\\ref",
    r"图\\ref",
    "首个预测日",
    "最优模型为",
]

FIGURE_TABLE_ANALYSIS_TERMS = [
    "展示",
    "列出",
    "包含",
    "给出",
    "由表",
    "由图",
    "可知",
    "说明",
    "表明",
    "趋势",
    "差异",
    "异常",
    "误差",
    "变化",
    "影响",
    "支持",
    "依据",
]

FIGURE_TABLE_CONTEXT_TERMS = ["展示", "列出", "包含", "给出", "汇总", "横轴", "纵轴", "指标", "变量", "样本"]
FIGURE_TABLE_REASONING_TERMS = ["比较", "趋势", "差异", "异常", "误差", "变化", "影响", "集中", "偏离", "阈值"]
FIGURE_TABLE_DECISION_TERMS = ["表明", "说明", "可知", "回答", "最终", "支持", "依据", "因此", "由此", "用于"]

IDENTITY_RISK_TERMS = [
    "队员",
    "姓名",
    "学号",
    "电话",
    "手机号",
    "邮箱",
    "指导教师",
    "所在学校",
]

CITATION_COMMAND_RE = re.compile(r"\\(?:cite|citep|citet|parencite|textcite|autocite)(?:\[[^\]]*\])*\{[^{}]+\}")
CITATION_CLAIM_TERMS = [
    "研究表明",
    "文献表明",
    "已有研究",
    "相关研究",
    "根据文献",
    "学者认为",
    "理论认为",
    "实证表明",
]
NUMERIC_CLAIM_RE = re.compile(
    r"(?<![A-Za-z])[-+]?(?:\d+\.\d+|\d{2,})(?:\s*(?:%|‰|万元|元|公里|千米|米|吨|千克|kg|km|m|人|次|天|小时|分钟|年|月|日|个|项|座|类|倍|分|页))?"
)


def review_paper(root: Path) -> dict[str, str]:
    """Run a static paper review and save JSON/Markdown artifacts."""
    report = build_review(root)
    json_path = root / "artifacts" / "paper_review.json"
    md_path = root / "artifacts" / "paper_review.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    return {
        "paper_review": "artifacts/paper_review.md",
        "paper_review_json": "artifacts/paper_review.json",
    }


def build_review(root: Path) -> dict[str, Any]:
    tex_path = root / "paper" / "main.tex"
    pdf_path = root / "paper" / "main.pdf"
    log_path = root / "artifacts" / "latex_compile.log"
    metadata_path = root / "metadata.json"
    analysis_path = root / "artifacts" / "analysis.json"
    specialized_path = root / "results" / "specialized_manifest.json"
    baseline_path = root / "results" / "baseline_manifest.json"
    computed_path = root / "results" / "computed_manifest.json"

    tex = read_text(tex_path)
    log = read_text(log_path)
    metadata = load_json_if_exists(metadata_path)
    analysis = load_json_if_exists(analysis_path)
    specialized = load_json_if_exists(specialized_path)
    baseline = load_json_if_exists(baseline_path)
    computed = load_json_if_exists(computed_path)

    checks: list[Check] = []
    checks.extend(check_required_files(tex_path, pdf_path, log_path))

    if tex:
        checks.extend(check_structure(tex, analysis))
        checks.extend(check_abstract(tex, analysis))
        checks.extend(check_model_building(tex))
        checks.extend(check_formula_numbering(tex))
        checks.extend(check_figures_and_tables(root, tex))
        checks.extend(check_references_and_appendix(tex))
        checks.extend(check_academic_integrity_gate(root, tex, specialized, baseline, computed))
        checks.extend(check_identity_risk(tex))
    else:
        checks.append(make_check("latex_source", "fail", "LaTeX 源文件", "未找到 paper/main.tex，无法进行正文审查。", "high"))

    checks.extend(check_compile_log(log, log_path))
    checks.extend(check_pdf(pdf_path))
    checks.extend(check_template_configuration(metadata))
    checks.extend(check_body_page_target(root, metadata))
    checks.extend(check_traceability(root, specialized, baseline, computed, metadata))

    fail_count = sum(1 for item in checks if item["status"] == "fail")
    warning_count = sum(1 for item in checks if item["status"] == "warning")
    pass_count = sum(1 for item in checks if item["status"] == "pass")
    score = max(0, 100 - fail_count * 15 - warning_count * 5)
    overall_status = "fail" if fail_count else "warning" if warning_count else "pass"

    traceability_files = {
        "latex": "paper/main.tex" if tex_path.exists() else "",
        "pdf": "paper/main.pdf" if pdf_path.exists() else "",
        "latex_log": "artifacts/latex_compile.log" if log_path.exists() else "",
        "analysis": "artifacts/analysis.json" if analysis_path.exists() else "",
    }
    if metadata.get("auto_workflow_mode") == "llm_code_results":
        traceability_files.update(
            {
                "computed_manifest": "results/computed_manifest.json" if computed_path.exists() else "",
                "computed_summary": "results/computed_summary.md" if (root / "results" / "computed_summary.md").exists() else "",
                "computed_solver": "code/run_computed_solution.py" if (root / "code" / "run_computed_solution.py").exists() else "",
                "computed_log": "artifacts/computed_solution_run.log" if (root / "artifacts" / "computed_solution_run.log").exists() else "",
            }
        )
    elif metadata.get("auto_workflow_mode") != "llm_only":
        traceability_files.update(
            {
                "specialized_manifest": "results/specialized_manifest.json" if specialized_path.exists() else "",
                "baseline_manifest": "results/baseline_manifest.json" if baseline_path.exists() else "",
            }
        )

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "project_root": str(root),
        "overall": {
            "status": overall_status,
            "score": score,
            "pass_count": pass_count,
            "warning_count": warning_count,
            "fail_count": fail_count,
        },
        "pdf_info": read_pdf_info(pdf_path),
        "body_page_info": compute_body_page_info(root, metadata),
        "checks": checks,
        "recommendations": build_recommendations(checks),
        "traceability_files": traceability_files,
    }


def check_required_files(tex_path: Path, pdf_path: Path, log_path: Path) -> list[Check]:
    checks = []
    checks.append(
        make_check(
            "required_tex",
            "pass" if tex_path.exists() else "fail",
            "LaTeX 源文件",
            "已找到 paper/main.tex。" if tex_path.exists() else "缺少 paper/main.tex。",
            "high",
        )
    )
    checks.append(
        make_check(
            "required_pdf",
            "pass" if pdf_path.exists() else "warning",
            "PDF 文件",
            "已找到 paper/main.pdf。" if pdf_path.exists() else "尚未找到 paper/main.pdf，请先编译 LaTeX。",
            "medium",
        )
    )
    checks.append(
        make_check(
            "required_compile_log",
            "pass" if log_path.exists() else "warning",
            "编译日志",
            "已找到 artifacts/latex_compile.log。" if log_path.exists() else "缺少编译日志，无法检查 LaTeX 警告。",
            "medium",
        )
    )
    return checks


def check_structure(tex: str, analysis: dict[str, Any]) -> list[Check]:
    checks: list[Check] = []
    section_titles = extract_section_titles(tex)
    missing = [title for title in REQUIRED_SECTIONS if not has_section(section_titles, title)]
    appendix_ok = r"\appendix" in tex or any("附录" in title for title in section_titles)
    if missing or not appendix_ok:
        detail = []
        if missing:
            detail.append("缺少章节：" + "、".join(missing))
        if not appendix_ok:
            detail.append("未检测到 \\appendix 或附录章节。")
        checks.append(make_check("section_structure", "fail", "论文标准章节", "；".join(detail), "high"))
    else:
        checks.append(make_check("section_structure", "pass", "论文标准章节", "标准章节、参考文献与附录结构均已出现。"))

    summary_items = []
    if "摘要" in tex:
        summary_items.append("摘要")
    if "关键词" in tex:
        summary_items.append("关键词")
    missing_front = [item for item in ["摘要", "关键词"] if item not in summary_items]
    checks.append(
        make_check(
            "front_matter",
            "pass" if not missing_front else "warning",
            "摘要关键词",
            "摘要与关键词均已出现。" if not missing_front else "缺少：" + "、".join(missing_front),
            "medium",
        )
    )
    checks.append(
        make_check(
            "table_of_contents",
            "warning" if r"\tableofcontents" in tex else "pass",
            "目录设置",
            "检测到目录；数学建模论文通常不需要目录。" if r"\tableofcontents" in tex else "未检测到目录，符合常见数学建模论文写法。",
            "low",
        )
    )

    expected_count = expected_problem_count(analysis, tex)
    if expected_count:
        restatement = section_body(tex, "问题重述")
        analysis_body = section_body(tex, "问题分析")
        model_building_body = section_body(tex, "模型建立")
        solving_body = section_body(tex, "模型求解")
        checks.append(problem_subsection_check("restatement_by_problem", "问题重述分问题", restatement, expected_count, "重述"))
        checks.append(problem_subsection_check("analysis_by_problem", "问题分析分问题", analysis_body, expected_count, "分析"))
        checks.append(problem_subsection_check("model_building_by_problem", "模型建立分问题", model_building_body, expected_count, "模型建立"))
        checks.append(problem_subsection_check("solving_by_problem", "模型求解分问题", solving_body, expected_count, ""))
    else:
        checks.append(make_check("problem_count", "warning", "子问题数量", "未能从 analysis.json 或 LaTeX 中稳定识别子问题数量。", "low"))
    return checks


def check_abstract(tex: str, analysis: dict[str, Any] | None = None) -> list[Check]:
    abstract = extract_abstract(tex)
    if not abstract:
        return [make_check("abstract_content", "fail", "摘要内容", "未检测到摘要正文。", "high")]
    plain = strip_latex(abstract)
    chinese_chars = len(re.findall(r"[\u4e00-\u9fff]", plain))
    method_terms = ["模型", "算法", "预测", "优化", "验证", "结果"]
    method_hit = sum(1 for term in method_terms if term in plain)
    numbers = re.findall(r"\d+(?:\.\d+)?", plain)
    status = "pass"
    detail = f"摘要约 {chinese_chars} 个汉字，包含 {len(numbers)} 个数值信息，方法关键词覆盖 {method_hit}/{len(method_terms)}。"
    severity = "low"
    if chinese_chars < 250:
        status = "warning"
        detail += " 摘要偏短，建议补充各子问题的模型、算法和关键结果。"
        severity = "medium"
    elif chinese_chars > 1800:
        status = "warning"
        detail += " 摘要偏长，需确认是否符合竞赛摘要页限制。"
        severity = "medium"
    if method_hit < 4:
        status = "warning"
        detail += " 方法链描述还不够完整。"
        severity = "medium"
    if len(numbers) < 2:
        status = "warning"
        detail += " 摘要缺少可追溯数值结果。"
        severity = "medium"
    checks = [make_check("abstract_content", status, "摘要质量", detail, severity)]

    expected_count = expected_problem_count(analysis or {}, tex)
    missing_chain = [term for term in ["首先", "随后", "再", "最后"] if term not in plain]
    missing_problem_sentences = []
    for index in range(1, expected_count + 1):
        pattern = rf"针对问题\s*{index}\s*[，,]\s*考虑[\s\S]*?建立[\s\S]*?采用[\s\S]*?得到"
        if not re.search(pattern, plain):
            missing_problem_sentences.append(str(index))
    reliability_terms = ["可靠性", "模型检验", "敏感性", "稳定性", "交叉验证", "残差诊断", "对照"]
    has_reliability = any(term in plain for term in reliability_terms)
    abstract_pattern_status = "pass"
    abstract_pattern_detail = "摘要包含方法链、逐问题固定句式和可靠性检验信息。"
    abstract_pattern_severity = "low"
    issues = []
    if missing_chain:
        issues.append("缺少方法链词：" + "、".join(missing_chain))
    if missing_problem_sentences:
        issues.append("缺少固定句式覆盖的问题：" + "、".join(missing_problem_sentences))
    if not has_reliability:
        issues.append("缺少可靠性或检验表述")
    if issues:
        abstract_pattern_status = "warning"
        abstract_pattern_detail = "；".join(issues) + "。摘要应按“背景目标—首先/随后/再/最后—针对问题X—可靠性—结论”组织。"
        abstract_pattern_severity = "medium"
    checks.append(
        make_check(
            "abstract_skill_pattern",
            abstract_pattern_status,
            "摘要固定格式",
            abstract_pattern_detail,
            abstract_pattern_severity,
        )
    )
    return checks


def check_model_building(tex: str) -> list[Check]:
    body = section_body(tex, "模型建立")
    if not body:
        return [make_check("model_building_exists", "fail", "模型建立章节", "未找到模型建立正文。", "high")]
    checks = []
    equation_count = len(re.findall(r"\\begin\{equation\}|\\\[", body)) + body.count("$$") // 2
    algorithm_terms = ["算法", "目标函数", "约束", "损失函数", "特征", "伪代码", "步骤"]
    algorithm_hit = [term for term in algorithm_terms if term in body]
    boundary_hits = []
    for phrase in RESULT_PHRASES_IN_MODEL_BUILDING:
        if re.search(phrase, body):
            boundary_hits.append(phrase.replace("\\\\", "\\"))
    if equation_count == 0:
        checks.append(make_check("model_building_equations", "warning", "模型建立数学表达", "模型建立中未检测到 equation 环境或展示公式。", "medium"))
    else:
        checks.append(make_check("model_building_equations", "pass", "模型建立数学表达", f"模型建立中检测到 {equation_count} 处展示公式。"))
    if not algorithm_hit:
        checks.append(make_check("model_building_principles", "warning", "模型建立算法原理", "模型建立中算法、目标函数、约束或特征定义描述偏少。", "medium"))
    else:
        checks.append(make_check("model_building_principles", "pass", "模型建立算法原理", "已检测到原理性关键词：" + "、".join(algorithm_hit[:5]) + "。"))
    if boundary_hits:
        checks.append(
            make_check(
                "model_building_boundary",
                "warning",
                "模型建立与结果边界",
                "模型建立章节疑似出现结果解释词：" + "、".join(boundary_hits) + "。建议把数值结果放入模型求解或模型检验。",
                "medium",
            )
        )
    else:
        checks.append(make_check("model_building_boundary", "pass", "模型建立与结果边界", "未检测到明显结果表述、图表解释或预测结论。"))
    return checks


def check_formula_numbering(tex: str) -> list[Check]:
    display_blocks = re.findall(r"\$\$([\s\S]*?)\$\$", tex)
    equation_blocks = re.findall(r"\\begin\{equation\}([\s\S]*?)\\end\{equation\}", tex)
    align_blocks = re.findall(r"\\begin\{(?:align|gather|multline)\}([\s\S]*?)\\end\{(?:align|gather|multline)\}", tex)
    total = len(display_blocks) + len(equation_blocks) + len(align_blocks)
    if total == 0:
        return [make_check("formula_numbering", "warning", "公式编号", "未检测到展示公式，无法检查公式编号。", "medium")]

    unnumbered = []
    for index, body in enumerate(display_blocks, 1):
        if not any(marker in body for marker in [r"\eqnum", r"\eqno", r"\tag{", r"\notag", r"\nonumber"]):
            unnumbered.append(f"$$ #{index}")
    for index, body in enumerate(equation_blocks, 1):
        if any(marker in body for marker in [r"\notag", r"\nonumber"]):
            unnumbered.append(f"equation #{index}")
    for index, body in enumerate(align_blocks, 1):
        if r"\tag{" not in body and r"\notag" in body:
            unnumbered.append(f"align #{index}")

    if unnumbered:
        return [
            make_check(
                "formula_numbering",
                "warning",
                "公式编号",
                f"检测到 {total} 处展示公式，其中以下公式可能缺少编号：" + "、".join(unnumbered[:8]),
                "medium",
            )
        ]
    return [make_check("formula_numbering", "pass", "公式编号", f"检测到 {total} 处展示公式，均包含编号标记。")]


def check_figures_and_tables(root: Path, tex: str) -> list[Check]:
    checks: list[Check] = []
    figures = extract_environments(tex, "figure")
    tables = extract_environments(tex, "table")
    solving_tex = section_body(tex, "模型求解") or tex
    solving_figures = extract_environments(solving_tex, "figure")
    solving_tables = extract_environments(solving_tex, "table")
    figure_count = len(figures)
    table_count = len(tables)
    caption_count = len(re.findall(r"\\caption\{", tex))
    checks.append(
        make_check(
            "figure_table_counts",
            "pass" if figure_count + table_count > 0 else "warning",
            "图表数量",
            f"正文检测到 {figure_count} 个 figure、{table_count} 个 table、{caption_count} 个 caption。",
            "medium",
        )
    )
    checks.append(
        make_check(
            "figure_table_solving_placement",
            "pass" if solving_figures or solving_tables else "warning",
            "图表与求解同位",
            f"模型求解章节中检测到 {len(solving_figures)} 个 figure、{len(solving_tables)} 个 table。"
            if (solving_figures or solving_tables)
            else "模型求解章节未检测到图表；标准数模论文应把表格和图片放在对应求解结果附近。",
            "medium",
        )
    )

    missing_captions = []
    weak_analysis = []
    thin_narratives = []
    for env_name, blocks in [("figure", figures), ("table", tables)]:
        for index, block in enumerate(blocks, 1):
            if r"\caption" not in block["content"]:
                missing_captions.append(f"{env_name} #{index}")

    for env_name, blocks in [("figure", solving_figures), ("table", solving_tables)]:
        for index, block in enumerate(blocks, 1):
            context = solving_tex[max(0, block["end"] - 180) : min(len(solving_tex), block["end"] + 560)]
            if not any(term in context for term in FIGURE_TABLE_ANALYSIS_TERMS):
                weak_analysis.append(f"{env_name} #{index}")
            has_context = any(term in context for term in FIGURE_TABLE_CONTEXT_TERMS)
            has_reasoning = any(term in context for term in FIGURE_TABLE_REASONING_TERMS)
            has_decision = any(term in context for term in FIGURE_TABLE_DECISION_TERMS)
            plain_context = strip_latex(context)
            if not (has_context and has_reasoning and has_decision and len(plain_context) >= 80):
                missing_bits = []
                if not has_context:
                    missing_bits.append("内容交代")
                if not has_reasoning:
                    missing_bits.append("结果判读")
                if not has_decision:
                    missing_bits.append("结论落点")
                if len(plain_context) < 80:
                    missing_bits.append("解释篇幅")
                thin_narratives.append(f"{env_name} #{index} 缺少{'/'.join(missing_bits)}")

    if missing_captions:
        checks.append(make_check("figure_table_captions", "fail", "图表标题", "缺少 caption：" + "、".join(missing_captions), "high"))
    else:
        checks.append(make_check("figure_table_captions", "pass", "图表标题", "所有 figure/table 环境均检测到 caption。"))
    if weak_analysis:
        checks.append(
            make_check(
                "figure_table_analysis",
                "warning",
                "图表自然判读",
                "模型求解中的以下结果图表附近未检测到充分的判读线索：" + "、".join(weak_analysis) + "。",
                "medium",
            )
        )
    else:
        checks.append(make_check("figure_table_analysis", "pass", "图表自然判读", "模型求解中的结果图表附近均检测到解释性文字。"))
    if thin_narratives:
        checks.append(
            make_check(
                "figure_table_narrative",
                "warning",
                "图表判读完整性",
                "以下求解图表附近的自然判读仍不充分：" + "、".join(thin_narratives) + "。",
                "medium",
            )
        )
    elif solving_figures or solving_tables:
        checks.append(make_check("figure_table_narrative", "pass", "图表判读完整性", "模型求解图表附近均检测到内容交代、结果判读和结论落点。"))

    graphics = re.findall(r"\\includegraphics(?:\[[^\]]*\])?\{([^{}]+)\}", tex)
    missing_graphics = [path for path in graphics if not resolve_graphic(root, path)]
    if missing_graphics:
        checks.append(make_check("figure_files", "fail", "图片文件存在性", "缺少图片文件：" + "、".join(missing_graphics), "high"))
    elif graphics:
        checks.append(make_check("figure_files", "pass", "图片文件存在性", f"{len(graphics)} 个 includegraphics 文件均可定位。"))
    elif figure_count:
        checks.append(make_check("figure_files", "pass", "图片文件存在性", "正文包含 figure 环境占位或绘制框，当前不依赖外部图片文件。"))
    else:
        checks.append(make_check("figure_files", "warning", "图片文件存在性", "未检测到 includegraphics。", "low"))
    return checks


def check_identity_risk(tex: str) -> list[Check]:
    hits = [term for term in IDENTITY_RISK_TERMS if term in tex]
    if hits:
        return [
            make_check(
                "identity_risk",
                "warning",
                "身份信息风险",
                "正文疑似包含身份相关词：" + "、".join(hits) + "。若赛题要求匿名，请提交前人工确认。",
                "medium",
            )
        ]
    return [make_check("identity_risk", "pass", "身份信息风险", "未检测到常见个人或队伍身份字段。")]


def check_references_and_appendix(tex: str) -> list[Check]:
    checks: list[Check] = []
    references = section_body(tex, "参考文献")
    reference_items = len(re.findall(r"\\item|\\bibitem|\\bibitem\{", references))
    if reference_items <= 0:
        checks.append(make_check("references_content", "warning", "参考文献内容", "参考文献章节为空或未检测到条目。", "medium"))
    else:
        checks.append(make_check("references_content", "pass", "参考文献内容", f"检测到 {reference_items} 条参考文献或条目。"))

    appendix = ""
    appendix_match = re.search(r"\\appendix([\s\S]*)", tex)
    if appendix_match:
        appendix = appendix_match.group(1)
    else:
        appendix = section_body(tex, "附录")
    appendix_plain = strip_latex(appendix)
    appendix_terms = ["数据", "程序", "代码", "复现", "AI", "工具", "中间表", "附录"]
    term_hits = [term for term in appendix_terms if term in appendix_plain]
    if not appendix_plain.strip():
        checks.append(make_check("appendix_content", "warning", "附录内容", "未检测到附录正文。", "medium"))
    elif len(term_hits) < 3:
        checks.append(
            make_check(
                "appendix_content",
                "warning",
                "附录内容",
                "附录已出现，但数据、程序、复现材料或 AI 工具说明覆盖不足。",
                "medium",
            )
        )
    else:
        checks.append(make_check("appendix_content", "pass", "附录内容", "附录包含数据、程序、复现或 AI 工具说明等支撑材料信息。"))
    return checks


def check_academic_integrity_gate(
    root: Path,
    tex: str,
    specialized: dict[str, Any],
    baseline: dict[str, Any],
    computed: dict[str, Any],
) -> list[Check]:
    checks: list[Check] = []
    plain = strip_latex(tex)
    references = section_body(tex, "参考文献")
    reference_items = len(re.findall(r"\\item|\\bibitem|\\bibitem\{", references))
    citation_count = len(CITATION_COMMAND_RE.findall(tex))
    citation_claim_hits = [term for term in CITATION_CLAIM_TERMS if term in plain]

    if citation_count > 0 and reference_items <= 0:
        checks.append(
            make_check(
                "claim_citation_alignment",
                "fail",
                "主张与引用对齐",
                f"正文检测到 {citation_count} 处引用命令，但参考文献章节未检测到条目。",
                "high",
            )
        )
    elif citation_claim_hits and citation_count == 0:
        checks.append(
            make_check(
                "claim_citation_alignment",
                "warning",
                "主张与引用对齐",
                "正文出现“" + "、".join(citation_claim_hits[:5]) + "”等文献性表述，但未检测到 \\cite 类引用命令；请确认这些主张有真实来源支撑。",
                "medium",
            )
        )
    elif reference_items > 0 and citation_count == 0:
        checks.append(
            make_check(
                "claim_citation_alignment",
                "warning",
                "主张与引用对齐",
                f"参考文献章节检测到 {reference_items} 条条目，但正文未检测到 \\cite 类引用命令；请确认参考文献不是装饰性列表。",
                "low",
            )
        )
    else:
        detail = f"检测到 {citation_count} 处正文引用命令、{reference_items} 条参考文献条目。"
        if citation_count == 0 and reference_items == 0:
            detail = "未检测到正文引用命令；若赛题论文不需要外部文献，仍需保证方法来源、赛题说明和数据来源在正文或附录中交代清楚。"
        checks.append(make_check("claim_citation_alignment", "pass", "主张与引用对齐", detail))

    evidence_available = any(manifest_has_results(item) for item in [computed, specialized, baseline])
    support_files = [
        root / "results" / "computed_manifest.json",
        root / "results" / "specialized_manifest.json",
        root / "results" / "baseline_manifest.json",
        root / "artifacts" / "computed_solution_run.log",
    ]
    evidence_available = evidence_available or any(path.exists() for path in support_files)
    claim_text = "\n".join(
        [
            extract_abstract(tex),
            section_body(tex, "模型求解"),
            section_body(tex, "模型检验"),
            section_body(tex, "模型评价"),
            section_body(tex, "结论"),
        ]
    )
    numeric_claims = count_key_numeric_claims(claim_text)
    if numeric_claims >= 12 and not evidence_available:
        checks.append(
            make_check(
                "numeric_claim_traceability",
                "warning",
                "数值主张可追溯性",
                f"摘要、求解或结论区域检测到约 {numeric_claims} 个精确数字，但未检测到结果 manifest 或运行日志；请避免把 LLM 草稿数值当作计算结果。",
                "high",
            )
        )
    elif numeric_claims > 0:
        source_note = "已检测到结果清单或运行日志。" if evidence_available else "数字数量不高，但仍建议人工核对来源。"
        checks.append(make_check("numeric_claim_traceability", "pass", "数值主张可追溯性", f"检测到约 {numeric_claims} 个关键数字；{source_note}"))
    else:
        checks.append(make_check("numeric_claim_traceability", "pass", "数值主张可追溯性", "摘要、求解和结论区域未检测到大量精确数值。"))

    appendix_plain = strip_latex(section_body(tex, "附录"))
    material_terms = ["支撑材料", "manifest", "运行日志", "代码", "程序", "复现", "人工复核", "AI 工具"]
    material_hits = [term for term in material_terms if term in appendix_plain or term in plain]
    if evidence_available or len(material_hits) >= 3:
        checks.append(make_check("material_passport", "pass", "过程记录与材料护照", "已检测到结果清单、运行日志或支撑材料说明。"))
    else:
        checks.append(
            make_check(
                "material_passport",
                "warning",
                "过程记录与材料护照",
                "未充分检测到 manifest、运行日志、代码、复现或人工复核说明；建议在附录和支撑材料包中保留过程记录。",
                "medium",
            )
        )
    return checks


def manifest_has_results(manifest: dict[str, Any]) -> bool:
    if not isinstance(manifest, dict) or not manifest:
        return False
    if manifest.get("tables") or manifest.get("figures") or manifest.get("metrics"):
        return True
    for item in manifest.get("per_problem_results", []) or []:
        if isinstance(item, dict) and (item.get("tables") or item.get("figures") or item.get("metrics")):
            return True
    return False


def count_key_numeric_claims(text: str) -> int:
    plain = strip_latex(text)
    count = 0
    for match in NUMERIC_CLAIM_RE.finditer(plain):
        token = match.group(0).strip()
        number_match = re.match(r"[-+]?\d+(?:\.\d+)?", token)
        if not number_match:
            continue
        value_text = number_match.group(0)
        if re.fullmatch(r"(?:19|20)\d{2}", value_text) and token == value_text:
            continue
        count += 1
    return count


def check_compile_log(log: str, log_path: Path) -> list[Check]:
    if not log_path.exists():
        return []
    checks: list[Check] = []
    fatal_patterns = ["Fatal error", "Undefined control sequence", "LaTeX Error", "Emergency stop"]
    fatal_hits = [pattern for pattern in fatal_patterns if pattern.lower() in log.lower()]
    if fatal_hits:
        checks.append(make_check("latex_fatal", "fail", "LaTeX 致命错误", "日志中检测到：" + "、".join(fatal_hits), "high"))
    else:
        checks.append(make_check("latex_fatal", "pass", "LaTeX 致命错误", "未检测到 Fatal error、Undefined control sequence 或 LaTeX Error。"))

    undefined_refs = len(re.findall(r"Reference .* undefined|undefined references|Citation .* undefined", log, flags=re.I))
    overfull = len(re.findall(r"Overfull \\hbox", log))
    warning_bits = []
    if undefined_refs:
        warning_bits.append(f"{undefined_refs} 条交叉引用/引用未定义")
    if overfull:
        warning_bits.append(f"{overfull} 条 Overfull hbox")
    if warning_bits:
        checks.append(make_check("latex_warnings", "warning", "LaTeX 警告", "；".join(warning_bits), "medium"))
    else:
        checks.append(make_check("latex_warnings", "pass", "LaTeX 警告", "未检测到未定义引用或 Overfull hbox。"))
    return checks


def check_pdf(pdf_path: Path) -> list[Check]:
    if not pdf_path.exists():
        return []
    info = read_pdf_info(pdf_path)
    if info.get("error"):
        return [make_check("pdf_info", "warning", "PDF 信息", f"无法读取 PDF 信息：{info['error']}", "medium")]
    checks = []
    pages = safe_int(info.get("Pages"))
    encrypted = str(info.get("Encrypted", "")).lower()
    page_size = str(info.get("Page size", ""))
    if pages and pages > 0:
        checks.append(make_check("pdf_pages", "pass", "PDF 页数", f"PDF 共 {pages} 页。"))
    else:
        checks.append(make_check("pdf_pages", "fail", "PDF 页数", "未能识别有效页数。", "high"))
    if encrypted == "no":
        checks.append(make_check("pdf_encryption", "pass", "PDF 加密", "PDF 未加密。"))
    else:
        checks.append(make_check("pdf_encryption", "fail", "PDF 加密", f"PDF 加密状态为 {info.get('Encrypted', '未知')}。", "high"))
    if "A4" in page_size or "595" in page_size:
        checks.append(make_check("pdf_page_size", "pass", "PDF 页面尺寸", f"页面尺寸：{page_size}。"))
    else:
        checks.append(make_check("pdf_page_size", "warning", "PDF 页面尺寸", f"页面尺寸为 {page_size or '未知'}，请确认是否符合模板。", "medium"))
    return checks


def check_body_page_target(root: Path, metadata: dict[str, Any]) -> list[Check]:
    options = metadata.get("paper_options", {}) if isinstance(metadata, dict) else {}
    target = safe_int(options.get("target_body_pages"))
    if not target:
        return [
            make_check(
                "body_page_target",
                "pass",
                "正文目标页数",
                "未设置正文目标页数，审查器不执行正文下限约束。",
            )
        ]
    info = compute_body_page_info(root, metadata)
    if info.get("error"):
        return [
            make_check(
                "body_page_target",
                "fail",
                "正文目标页数",
                f"目标正文不少于 {target} 页，但无法计算正文页数：{info['error']}。请先回填论文、编译两次，并确保模板含有 page:body-start 与 page:appendix-start 标签。",
                "high",
            )
        ]
    body_pages = safe_int(info.get("body_pages"))
    status = "pass" if body_pages >= target else "fail"
    detail = (
        f"目标正文不少于 {target} 页；检测到正文 {body_pages} 页。"
        f"统计范围为第 {info.get('body_start_page')} 页标签到第 {info.get('appendix_start_page')} 页附录标签之间，"
        "不包含摘要和附录。"
    )
    if status == "fail":
        detail += " 当前正文未达到目标页数，请扩写模型建立、模型求解、图表分析和模型检验等正文内容。"
    return [make_check("body_page_target", status, "正文目标页数", detail, "high" if status == "fail" else "low")]


def check_template_configuration(metadata: dict[str, Any]) -> list[Check]:
    options = metadata.get("paper_options", {}) if isinstance(metadata, dict) else {}
    template_id = options.get("template_id") or DEFAULT_TEMPLATE_ID
    if template_id == DEFAULT_TEMPLATE_ID:
        return [make_check("template_configuration", "pass", "论文模板设置", "当前使用内置 LaTeX 模板。")]
    try:
        selected = get_template(template_id)
    except FileNotFoundError as exc:
        return [make_check("template_configuration", "fail", "论文模板设置", f"所选模板不存在：{exc}", "high")]
    if selected and selected.get("mode") == "rules":
        has_summary = bool(metadata.get("artifacts", {}).get("format_rules_summary")) if isinstance(metadata, dict) else False
        summary_note = "已生成格式规则摘要文件。" if has_summary else "尚未生成格式规则摘要文件，建议先执行一次论文回填。"
        detail = (
            f"当前选择的是格式说明文档“{selected.get('name', template_id)}”，"
            "系统会使用内置 LaTeX 模板生成论文，并把提取出的官方规则写入回填摘要与 LaTeX 注释；"
            f"{summary_note}提交前仍需人工核对 Word/PDF 官方格式细节。"
        )
        return [make_check("template_configuration", "warning", "论文模板设置", detail, "low")]
    detail = f"当前使用自定义 LaTeX 模板“{selected.get('name', template_id) if selected else template_id}”。"
    return [make_check("template_configuration", "pass", "论文模板设置", detail)]


def compute_body_page_info(root: Path, metadata: dict[str, Any]) -> dict[str, Any]:
    aux_path = root / "paper" / "main.aux"
    if not aux_path.exists():
        return {"error": "缺少 paper/main.aux"}
    aux = read_text(aux_path)
    start_page = parse_aux_label_page(aux, "page:body-start")
    appendix_page = parse_aux_label_page(aux, "page:appendix-start")
    if not start_page:
        return {"error": "缺少 page:body-start 标签"}
    if not appendix_page:
        return {"error": "缺少 page:appendix-start 标签"}
    body_pages = max(0, appendix_page - start_page)
    options = metadata.get("paper_options", {}) if isinstance(metadata, dict) else {}
    return {
        "target_body_pages": options.get("target_body_pages"),
        "body_start_page": start_page,
        "appendix_start_page": appendix_page,
        "body_pages": body_pages,
    }


def parse_aux_label_page(aux: str, label: str) -> int:
    pattern = re.compile(rf"\\newlabel\{{{re.escape(label)}\}}\{{\{{[^{{}}]*\}}\{{([^{{}}]+)\}}")
    match = pattern.search(aux)
    if not match:
        return 0
    return safe_int(match.group(1))


def check_traceability(
    root: Path,
    specialized: dict[str, Any],
    baseline: dict[str, Any],
    computed: dict[str, Any],
    metadata: dict[str, Any],
) -> list[Check]:
    checks: list[Check] = []
    if isinstance(metadata, dict) and metadata.get("auto_workflow_mode") == "llm_only":
        checks.append(
            make_check(
                "llm_only_traceability",
                "pass",
                "LLM-only 可追溯性",
                "当前项目使用 LLM-only 自动流程，审查器不要求基线或专项模型 manifest；题解、LaTeX、审查报告和支撑包作为主要可追溯文件。",
            )
        )
        return checks
    if isinstance(metadata, dict) and metadata.get("auto_workflow_mode") == "llm_code_results":
        if not computed:
            checks.append(
                make_check(
                    "computed_manifest_presence",
                    "fail",
                    "代码计算结果清单",
                    "当前项目使用 LLM 规划代码求解流程，但缺少 results/computed_manifest.json。",
                    "high",
                )
            )
            return checks
        checks.append(make_check("computed_manifest_presence", "pass", "代码计算结果清单", "已找到 results/computed_manifest.json。"))

        missing_outputs = []
        table_count = 0
        figure_count = 0
        for table in computed.get("tables", []) or []:
            relative = table.get("path") if isinstance(table, dict) else table
            if relative:
                table_count += 1
                if not (root / relative).exists():
                    missing_outputs.append(relative)
        for figure in computed.get("figures", []) or []:
            relative = figure.get("path") if isinstance(figure, dict) else figure
            if relative:
                figure_count += 1
                if not (root / relative).exists():
                    missing_outputs.append(relative)
        summary = computed.get("summary_markdown")
        if summary and not (root / summary).exists():
            missing_outputs.append(summary)
        if missing_outputs:
            checks.append(make_check("computed_manifest_outputs", "fail", "代码结果文件可追溯性", "清单中缺少实际文件：" + "、".join(missing_outputs[:12]), "high"))
        else:
            checks.append(make_check("computed_manifest_outputs", "pass", "代码结果文件可追溯性", f"清单记录的 {table_count} 个表格文件和 {figure_count} 个图片文件均存在。"))

        per_problem = computed.get("per_problem_results", []) or []
        solved = [item for item in per_problem if item.get("tables") or item.get("figures") or item.get("metrics")]
        if solved:
            checks.append(make_check("computed_problem_results", "pass", "分问题代码结果", f"检测到 {len(solved)} 个子问题具有代码生成的表格、图片或指标。"))
        else:
            checks.append(make_check("computed_problem_results", "warning", "分问题代码结果", "未检测到分问题表格、图片或指标；请检查字段映射或附件数据。", "medium"))
        return checks
    manifest_missing = []
    if not specialized:
        manifest_missing.append("results/specialized_manifest.json")
    if not baseline:
        manifest_missing.append("results/baseline_manifest.json")
    if manifest_missing:
        checks.append(make_check("manifest_presence", "warning", "结果清单", "缺少：" + "、".join(manifest_missing), "medium"))
    else:
        checks.append(make_check("manifest_presence", "pass", "结果清单", "专项与基线结果清单均存在。"))

    missing_outputs = []
    for manifest in [specialized, baseline]:
        for key in ["tables", "figures"]:
            for relative in manifest.get(key, []) or []:
                if not (root / relative).exists():
                    missing_outputs.append(relative)
        summary = manifest.get("summary_markdown")
        if summary and not (root / summary).exists():
            missing_outputs.append(summary)

    if missing_outputs:
        checks.append(make_check("manifest_outputs", "fail", "结果文件可追溯性", "清单中缺少实际文件：" + "、".join(missing_outputs[:12]), "high"))
    elif specialized or baseline:
        table_count = sum(len((manifest.get("tables") or [])) for manifest in [specialized, baseline])
        figure_count = sum(len((manifest.get("figures") or [])) for manifest in [specialized, baseline])
        checks.append(make_check("manifest_outputs", "pass", "结果文件可追溯性", f"清单记录的 {table_count} 个表格文件和 {figure_count} 个图片文件均存在。"))
    return checks


def render_markdown(report: dict[str, Any]) -> str:
    overall = report["overall"]
    status_label = {"pass": "通过", "warning": "需注意", "fail": "需修订"}.get(overall["status"], overall["status"])
    lines = [
        "# 论文质量审查报告",
        "",
        f"- 生成时间：{report['generated_at']}",
        f"- 总体状态：{status_label}",
        f"- 质量评分：{overall['score']}/100",
        f"- 检查统计：通过 {overall['pass_count']} 项，警告 {overall['warning_count']} 项，失败 {overall['fail_count']} 项",
        "",
    ]
    pdf_info = report.get("pdf_info") or {}
    if pdf_info and not pdf_info.get("error"):
        lines.extend(
            [
                "## PDF 信息",
                f"- 页数：{pdf_info.get('Pages', '-')}",
                f"- 加密：{pdf_info.get('Encrypted', '-')}",
                f"- 页面尺寸：{pdf_info.get('Page size', '-')}",
                "",
            ]
        )
    body_info = report.get("body_page_info") or {}
    if body_info and not body_info.get("error"):
        lines.extend(
            [
                "## 正文页数",
                f"- 目标正文页数：{body_info.get('target_body_pages') or '-'}",
                f"- 检测正文页数：{body_info.get('body_pages', '-')}",
                f"- 统计边界：page:body-start={body_info.get('body_start_page', '-')}，page:appendix-start={body_info.get('appendix_start_page', '-')}",
                "",
            ]
        )

    grouped = {
        "fail": [item for item in report["checks"] if item["status"] == "fail"],
        "warning": [item for item in report["checks"] if item["status"] == "warning"],
        "pass": [item for item in report["checks"] if item["status"] == "pass"],
    }
    lines.extend(render_check_group("## 高优先级问题", grouped["fail"], "未发现失败项。"))
    lines.extend(render_check_group("## 警告项", grouped["warning"], "未发现警告项。"))
    lines.extend(render_check_group("## 已通过检查", grouped["pass"], "暂无通过项。"))

    lines.append("## 建议修订顺序")
    if report["recommendations"]:
        for item in report["recommendations"]:
            lines.append(f"- {item}")
    else:
        lines.append("- 当前静态审查未发现必须修订的问题，可进入人工通读和格式核对。")
    lines.append("")

    lines.append("## 可追溯文件")
    for label, relative in report["traceability_files"].items():
        if relative:
            lines.append(f"- {label}: `{relative}`")
    lines.append("")
    return "\n".join(lines)


def render_check_group(title: str, checks: list[Check], empty: str) -> list[str]:
    lines = [title]
    if not checks:
        lines.append(f"- {empty}")
    else:
        for item in checks:
            lines.append(f"- **{item['title']}**：{item['detail']}")
    lines.append("")
    return lines


def build_recommendations(checks: list[Check]) -> list[str]:
    recommendations = []
    for item in checks:
        if item["status"] == "pass":
            continue
        if item["id"] == "section_structure":
            recommendations.append("先补齐标准章节、参考文献和附录结构，再进行内容润色。")
        elif item["id"] in {"restatement_by_problem", "analysis_by_problem", "solving_by_problem"}:
            recommendations.append("将问题重述、问题分析和模型求解按每个子问题分别组织。")
        elif item["id"] == "model_building_boundary":
            recommendations.append("把模型建立中的数值结果、图表解释和最终结论移动到模型求解或模型检验。")
        elif item["id"] in {"figure_table_analysis", "figure_table_captions", "figure_table_narrative"}:
            recommendations.append("逐个图表补充自然判读段落，说明表图内容、关键现象和对应子问题的结论，并放在对应求解段落附近。")
        elif item["id"] in {"latex_fatal", "latex_warnings"}:
            recommendations.append("先处理 LaTeX 编译日志中的错误、引用警告或版面溢出提示，并重新编译两次。")
        elif item["id"] == "claim_citation_alignment":
            recommendations.append("逐条核对文献性主张与正文引用，删除无法确认来源或不能支撑对应主张的参考文献。")
        elif item["id"] == "numeric_claim_traceability":
            recommendations.append("复核摘要、求解和结论中的精确数字，确保每个关键数值都来自 manifest、结果表、图形或运行日志。")
        elif item["id"] == "material_passport":
            recommendations.append("在附录和支撑材料中保留代码、结果清单、运行日志、AI 工具说明和人工复核点。")
        elif item["id"].startswith("pdf_"):
            recommendations.append("重新生成并检查 PDF，确认页数、A4 页面和未加密状态。")
        elif item["id"] == "body_page_target":
            recommendations.append("围绕模型建立、逐问题求解、图表自然判读和模型检验扩写正文；重新生成、编译两次后复查正文页数。")
        elif item["id"].startswith("computed_"):
            recommendations.append("重新运行一键自动流程中的代码求解步骤，确认 computed manifest、结果表、图片和运行日志完整生成。")
        elif item["id"].startswith("manifest"):
            recommendations.append("重新运行建模脚本，确保结果 manifest、图片和表格文件完整存在。")
    seen = set()
    unique = []
    for item in recommendations:
        if item not in seen:
            unique.append(item)
            seen.add(item)
    return unique


def make_check(check_id: str, status: str, title: str, detail: str, severity: str = "low") -> Check:
    return {
        "id": check_id,
        "status": status,
        "severity": severity,
        "title": title,
        "detail": detail,
    }


def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def load_json_if_exists(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def read_pdf_info(pdf_path: Path) -> dict[str, str]:
    if not pdf_path.exists():
        return {}
    pdfinfo = shutil.which("pdfinfo")
    if pdfinfo:
        try:
            result = subprocess.run(
                [pdfinfo, str(pdf_path)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
                check=False,
            )
            if result.returncode == 0:
                return parse_pdfinfo(result.stdout)
            return {"error": result.stderr.strip() or result.stdout.strip() or f"pdfinfo exited {result.returncode}"}
        except Exception as exc:
            return {"error": f"{type(exc).__name__}: {exc}"}
    return fallback_pdf_info(pdf_path)


def fallback_pdf_info(pdf_path: Path) -> dict[str, str]:
    for module_name in ["pypdf", "PyPDF2"]:
        try:
            module = __import__(module_name)
            reader = module.PdfReader(str(pdf_path))
            encrypted = "yes" if getattr(reader, "is_encrypted", False) else "no"
            page_size = ""
            if reader.pages:
                mediabox = reader.pages[0].mediabox
                page_size = f"{float(mediabox.width):.2f} x {float(mediabox.height):.2f} pts"
            return {"Pages": str(len(reader.pages)), "Encrypted": encrypted, "Page size": page_size}
        except Exception:
            continue
    return {"error": "未找到 pdfinfo，且无法使用 pypdf/PyPDF2 读取 PDF。"}


def parse_pdfinfo(output: str) -> dict[str, str]:
    info: dict[str, str] = {}
    for line in output.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        info[key.strip()] = value.strip()
    return info


def extract_section_titles(tex: str) -> list[str]:
    return [strip_latex(match.group(1)).strip() for match in re.finditer(r"\\section\*?\{([^{}]+)\}", tex)]


def has_section(section_titles: list[str], required: str) -> bool:
    return any(required in title for title in section_titles)


def section_body(tex: str, title: str) -> str:
    pattern = re.compile(r"\\section\*?\{([^{}]+)\}")
    matches = list(pattern.finditer(tex))
    for index, match in enumerate(matches):
        section_title = strip_latex(match.group(1))
        if title in section_title:
            start = match.end()
            end = matches[index + 1].start() if index + 1 < len(matches) else len(tex)
            appendix_match = re.search(r"\\appendix", tex[start:end])
            if appendix_match:
                end = start + appendix_match.start()
            return tex[start:end]
    return ""


def expected_problem_count(analysis: dict[str, Any], tex: str) -> int:
    tasks = analysis.get("recommended_problem", {}).get("tasks", []) if analysis else []
    if tasks:
        return len(tasks)
    hits = re.findall(r"\\subsection\{[^{}]*问题\s*(\d+)", tex)
    numbers = [safe_int(item) for item in hits]
    numbers = [item for item in numbers if item]
    return max(numbers) if numbers else 0


def problem_subsection_check(check_id: str, title: str, body: str, expected_count: int, suffix: str) -> Check:
    missing = []
    for index in range(1, expected_count + 1):
        if suffix:
            pattern = rf"\\subsection\{{[^}}]*问题\s*{index}[^}}]*{suffix}[^}}]*\}}"
        else:
            pattern = rf"\\subsection\{{[^}}]*问题\s*{index}[^}}]*\}}"
        paragraph_labels = [
            rf"问题\s*{index}\s*{suffix}\s*[：:]",
            rf"问题\s*{index}\s*[：:]",
        ]
        has_paragraph_label = any(re.search(label, body) for label in paragraph_labels)
        if not re.search(pattern, body) and not has_paragraph_label:
            missing.append(str(index))
    if missing:
        return make_check(check_id, "warning", title, "缺少子问题：" + "、".join(missing), "medium")
    return make_check(check_id, "pass", title, f"已按 {expected_count} 个子问题分别组织。")


def extract_abstract(tex: str) -> str:
    patterns = [
        r"\\textbf\{摘要[:：]\}\s*(.*?)\s*\\noindent\\textbf\{关键词",
        r"\\begin\{abstract\}(.*?)\\end\{abstract\}",
    ]
    for pattern in patterns:
        match = re.search(pattern, tex, flags=re.S)
        if match:
            return match.group(1).strip()
    return ""


def extract_environments(tex: str, name: str) -> list[dict[str, Any]]:
    pattern = re.compile(rf"\\begin\{{{name}\}}(.*?)\\end\{{{name}\}}", flags=re.S)
    return [{"content": match.group(1), "start": match.start(), "end": match.end()} for match in pattern.finditer(tex)]


def resolve_graphic(root: Path, graphic: str) -> bool:
    raw = graphic.strip()
    candidates = [
        root / "paper" / raw,
        root / raw,
        root / "results" / "figures" / raw,
        root / "results" / raw,
    ]
    extensions = ["", ".png", ".jpg", ".jpeg", ".pdf"]
    for candidate in candidates:
        if candidate.suffix:
            if candidate.exists():
                return True
        else:
            for extension in extensions:
                if (candidate.with_suffix(extension) if extension else candidate).exists():
                    return True
    return False


def strip_latex(text: str) -> str:
    text = re.sub(r"\\[a-zA-Z]+\*?(?:\[[^\]]*\])?", "", text)
    text = re.sub(r"[{}]", "", text)
    return text


def safe_int(value: Any) -> int:
    try:
        return int(str(value).strip())
    except Exception:
        return 0
