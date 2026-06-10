from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from app.services.llm_solution import (
    STANDALONE_FORMULA_SKIP_ENVIRONMENTS,
    is_standalone_inline_formula_line,
)
from app.services.process_utils import find_external_command, run_external_command
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

FIGURE_TABLE_ANALYSIS_TERMS.extend(["展示", "列出", "包含", "给出", "由表", "由图", "可知", "说明", "表明", "趋势", "差异", "异常", "误差", "变化", "影响", "支持", "依据"])
FIGURE_TABLE_CONTEXT_TERMS.extend(["展示", "列出", "包含", "给出", "汇总", "横轴", "纵轴", "指标", "变量", "样本"])
FIGURE_TABLE_REASONING_TERMS.extend(["比较", "趋势", "差异", "异常", "误差", "变化", "影响", "集中", "偏离", "阈值", "高值", "复核", "追踪", "来源", "确认"])
FIGURE_TABLE_DECISION_TERMS.extend(["表明", "说明", "可知", "回答", "最终", "支持", "依据", "因此", "由此", "用于", "支撑", "给出", "记录", "追踪", "确认", "避免"])

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
        checks.extend(check_abstract(tex, analysis, metadata, computed))
        checks.extend(check_model_building(tex))
        checks.extend(check_formula_numbering(tex))
        checks.extend(check_figures_and_tables(root, tex))
        checks.extend(check_submission_surface(tex))
        checks.extend(check_figure_image_quality(root, tex))
        checks.extend(check_solver_figure_generation_rules(root))
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
    checks.extend(check_modeling_process_gates(root, computed, analysis, metadata, tex))

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


def check_abstract(
    tex: str,
    analysis: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
    computed: dict[str, Any] | None = None,
) -> list[Check]:
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
        pattern = rf"针对问题\s*{index}\s*[，,:：]\s*(?:考虑|围绕|建立)?[\s\S]*?建立[\s\S]*?采用[\s\S]*?得到"
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
    workflow_mode = str((metadata or {}).get("auto_workflow_mode") or "")
    if workflow_mode.startswith("llm_code_results") or computed:
        computed_status = "pass"
        computed_detail = "一键代码流程摘要接近一页，并按子问题写入可追溯数值结果。"
        computed_severity = "low"
        computed_issues: list[str] = []
        if chinese_chars < 650:
            computed_issues.append(f"摘要约 {chinese_chars} 个汉字，未达到接近一页的自动流程标准")
        missing_numeric = abstract_problem_numeric_gaps(plain, expected_count)
        if missing_numeric:
            computed_issues.append("以下子问题附近缺少数值结果：" + "、".join(missing_numeric))
        if len(numbers) < max(3, expected_count):
            computed_issues.append(f"摘要数值信息仅 {len(numbers)} 个，难以支撑逐问结果概括")
        if computed_issues:
            computed_status = "fail"
            computed_detail = "；".join(computed_issues) + "。一键流程必须在摘要中概括模型链、逐问关键数值、检验结果和最终结论。"
            computed_severity = "high"
        checks.append(
            make_check(
                "abstract_computed_results",
                computed_status,
                "摘要逐问数值结果",
                computed_detail,
                computed_severity,
            )
        )
    return checks


def abstract_problem_numeric_gaps(plain: str, expected_count: int) -> list[str]:
    gaps: list[str] = []
    for index in range(1, expected_count + 1):
        start = re.search(rf"问题\s*{index}", plain)
        if not start:
            gaps.append(str(index))
            continue
        next_match = re.search(rf"问题\s*{index + 1}", plain[start.end() :]) if index < expected_count else None
        end = start.end() + next_match.start() if next_match else min(len(plain), start.start() + 260)
        segment = plain[start.start() : end]
        if not re.search(r"\d+(?:\.\d+)?", segment):
            gaps.append(str(index))
    return gaps


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


def count_standalone_inline_formula_lines(tex: str) -> int:
    count = 0
    env_stack: list[str] = []
    in_display_math = False
    for raw_line in tex.splitlines():
        stripped = raw_line.strip()
        begin_env = re.match(r"\\begin\{([A-Za-z*]+)\}", stripped)
        end_env = re.match(r"\\end\{([A-Za-z*]+)\}", stripped)
        if begin_env:
            env_stack.append(begin_env.group(1))
            continue
        if end_env:
            if env_stack and env_stack[-1] == end_env.group(1):
                env_stack.pop()
            continue
        if "$$" in stripped:
            if stripped.count("$$") % 2 == 1:
                in_display_math = not in_display_math
            continue
        if in_display_math or any(env in STANDALONE_FORMULA_SKIP_ENVIRONMENTS for env in env_stack):
            continue
        if is_standalone_inline_formula_line(stripped):
            count += 1
    return count


def check_formula_numbering(tex: str) -> list[Check]:
    standalone_inline = count_standalone_inline_formula_lines(tex)
    if standalone_inline:
        return [
            make_check(
                "formula_numbering",
                "warning",
                "公式类型与编号",
                f"检测到 {standalone_inline} 处独占一行但仍写成段内公式的表达式，应改为居中显示并统一编号。",
                "medium",
            )
        ]

    display_blocks = re.findall(r"\$\$([\s\S]*?)\$\$", tex)
    equation_blocks = re.findall(r"\\begin\{equation\}([\s\S]*?)\\end\{equation\}", tex)
    align_blocks = re.findall(r"\\begin\{(?:align|gather|multline)\}([\s\S]*?)\\end\{(?:align|gather|multline)\}", tex)
    total = len(display_blocks) + len(equation_blocks) + len(align_blocks)
    if total == 0:
        return [make_check("formula_numbering", "warning", "公式编号", "未检测到展示公式，无法检查公式编号。", "medium")]

    numbered = 0
    unnumbered = 0
    for body in display_blocks:
        if any(marker in body for marker in [r"\eqnum", r"\eqno", r"\tag{"]):
            numbered += 1
        else:
            unnumbered += 1
    for body in [*equation_blocks, *align_blocks]:
        if any(marker in body for marker in [r"\notag", r"\nonumber"]):
            unnumbered += 1
        else:
            numbered += 1

    if unnumbered:
        return [
            make_check(
                "formula_numbering",
                "warning",
                "公式编号",
                f"检测到 {total} 处展示公式，其中 {unnumbered} 处未编号；独占一行的显式公式应统一编号。",
                "medium",
            )
        ]
    return [
        make_check(
            "formula_numbering",
            "pass",
            "公式编号",
            f"检测到 {total} 处展示公式，均已编号；段内公式仍保持内联形式。",
        )
    ]


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

    graphics = extract_graphic_paths(tex)
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


def check_submission_surface(tex: str) -> list[Check]:
    visible = paper_visible_text(tex)
    backstage_hits: list[str] = []
    backstage_patterns = [
        (r"\bmanifest\b|结果清单文件|computed_manifest|baseline_manifest|specialized_manifest", "manifest/结果清单"),
        (r"\bauto_workflow\b|\bworkflow\b|自动流程日志|后台流程", "后台流程痕迹"),
        (r"\bartifacts?[\\/]|support_materials|paper[\\/]main|results[\\/]|code[\\/]", "项目内部路径"),
        (r"[A-Za-z]:[\\/][^\s，。；：,;]+", "本机绝对路径"),
        (r"[\w\u4e00-\u9fff.-]+\.(?:json|log|csv|png|jpg|jpeg|pdf|tex|py|zip)\b", "具体文件名"),
    ]
    for pattern, label in backstage_patterns:
        if re.search(pattern, visible, flags=re.I):
            backstage_hits.append(label)
    if backstage_hits:
        return [
            make_check(
                "submission_surface_backstage_traces",
                "fail",
                "正文后台痕迹",
                "提交可见文本仍出现：" + "、".join(dict.fromkeys(backstage_hits)) + "。正文不得暴露文件名、路径、manifest、日志或后台流程痕迹。",
                "high",
            )
        ]
    return [make_check("submission_surface_backstage_traces", "pass", "正文后台痕迹", "提交可见文本未检测到文件名、路径、manifest、日志或后台流程痕迹。")]


def check_figure_image_quality(root: Path, tex: str) -> list[Check]:
    graphics = extract_graphic_paths(tex)
    paths = [resolve_graphic_path(root, graphic) for graphic in graphics]
    paths = [path for path in paths if path is not None and path.suffix.lower() in {".png", ".jpg", ".jpeg"}]
    if not paths:
        return [make_check("figure_image_quality", "warning", "图片清晰度", "未检测到可直接检查尺寸的 PNG/JPG 图片。", "low")]
    try:
        from PIL import Image
    except Exception:
        return [make_check("figure_image_quality", "warning", "图片清晰度", "未安装 Pillow，无法读取图片尺寸。", "low")]
    low_quality: list[str] = []
    for path in paths:
        try:
            with Image.open(path) as image:
                width, height = image.size
        except Exception:
            low_quality.append(path.name + " 无法读取")
            continue
        if width < 1200 and width * height < 1_000_000:
            low_quality.append(f"{path.name} {width}x{height}")
    if low_quality:
        return [
            make_check(
                "figure_image_quality",
                "fail",
                "图片清晰度",
                "以下图片分辨率偏低：" + "、".join(low_quality[:10]) + "。一键流程应生成白底、中文正常、300 dpi 以上的论文图片。",
                "high",
            )
        ]
    return [make_check("figure_image_quality", "pass", "图片清晰度", f"已检查 {len(paths)} 张 PNG/JPG 图片，尺寸满足论文阅读要求。")]


def check_solver_figure_generation_rules(root: Path) -> list[Check]:
    scripts = [
        root / "code" / "run_computed_solution.py",
        root / "code" / "run_baseline_analysis.py",
        root / "code" / "run_specialized_model.py",
    ]
    issues: list[str] = []
    for script_path in scripts:
        if not script_path.exists():
            continue
        script = read_text(script_path)
        uses_matplotlib = bool(re.search(r"matplotlib|plt\.|savefig\s*\(", script))
        if uses_matplotlib:
            if "font.sans-serif" not in script and "configure_chinese_fonts" not in script and "font_manager" not in script:
                issues.append(f"{script_path.name} 未设置中文字体")
            if "axes.unicode_minus" not in script:
                issues.append(f"{script_path.name} 未设置中文负号显示")
            white_background = re.search(
                r"(?:figure\.facecolor|axes\.facecolor|savefig\.facecolor)[\"'\]]*\s*=\s*[\"']white[\"']|"
                r"[\"'](?:figure\.facecolor|axes\.facecolor|savefig\.facecolor)[\"']\s*:\s*[\"']white[\"']|"
                r"facecolor\s*=\s*[\"']white[\"']|"
                r"set_facecolor\s*\(\s*[\"']white[\"']",
                script,
                flags=re.I,
            )
            if not white_background:
                issues.append(f"{script_path.name} 未显式设置白底图片")
        if re.search(r"\bplt\.title\s*\(|\.set_title\s*\(|\.suptitle\s*\(", script):
            issues.append(f"{script_path.name} 使用图内标题")
        for match in re.finditer(r"savefig\s*\(([^)]*)\)", script, flags=re.S):
            call = match.group(1)
            dpi_match = re.search(r"dpi\s*=\s*(\d+)", call)
            if not dpi_match:
                issues.append(f"{script_path.name} savefig 未显式设置 dpi")
            elif int(dpi_match.group(1)) < 300:
                issues.append(f"{script_path.name} savefig dpi={dpi_match.group(1)}")
    if issues:
        return [
            make_check(
                "solver_figure_generation_rules",
                "fail",
                "图片生成规则",
                "求解脚本仍可能生成不合格图片：" + "、".join(issues[:12]) + "。",
                "high",
            )
        ]
    return [make_check("solver_figure_generation_rules", "pass", "图片生成规则", "求解脚本未检测到图内标题、低 dpi、中文字体缺失或非白底图片设置。")]


def paper_visible_text(tex: str) -> str:
    body_match = re.search(r"\\begin\{document\}([\s\S]*?)\\end\{document\}", tex)
    text = body_match.group(1) if body_match else tex
    text = re.sub(r"%.*", "", text)
    text = re.sub(r"\\graphicspath\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", "", text)
    text = re.sub(r"\\includegraphics(?:\[[^\]]*\])?\{\\detokenize\{[^{}]+\}\}", "", text)
    text = re.sub(r"\\includegraphics(?:\[[^\]]*\])?\{[^{}]+\}", "", text)
    text = re.sub(r"\\(?:label|ref|pageref|cite|citep|citet)(?:\[[^\]]*\])?\{[^{}]*\}", "", text)
    text = re.sub(r"\\url\{[^{}]*\}", "", text)
    text = strip_latex(text)
    return re.sub(r"\s+", " ", text)


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
    workflow_mode = str(metadata.get("auto_workflow_mode") or "") if isinstance(metadata, dict) else ""
    if workflow_mode.startswith("llm_code_results"):
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


def check_modeling_process_gates(
    root: Path,
    computed: dict[str, Any],
    analysis: dict[str, Any],
    metadata: dict[str, Any],
    tex: str,
) -> list[Check]:
    workflow_mode = str(metadata.get("auto_workflow_mode") or "") if isinstance(metadata, dict) else ""
    if not workflow_mode.startswith("llm_code_results"):
        return []
    if not computed:
        return []

    checks: list[Check] = []
    per_problem = [item for item in (computed.get("per_problem_results", []) or []) if isinstance(item, dict)]
    expected_count = expected_problem_count(analysis or {}, tex)
    solved_indices = {
        safe_int(item.get("problem_index"))
        for item in per_problem
        if item.get("tables") or item.get("figures") or item.get("metrics")
    }
    solved_indices.discard(0)
    if expected_count:
        missing = [str(index) for index in range(1, expected_count + 1) if index not in solved_indices]
        if missing:
            checks.append(
                make_check(
                    "gate_subproblem_coverage",
                    "warning",
                    "G1/G3 分问题覆盖",
                    "代码结果未覆盖子问题：" + "、".join(missing) + "；请检查题面解析、附件字段映射或求解脚本兜底逻辑。",
                    "medium",
                )
            )
        else:
            checks.append(
                make_check(
                    "gate_subproblem_coverage",
                    "pass",
                    "G1/G3 分问题覆盖",
                    f"检测到 {expected_count} 个子问题均有表格、图片或指标输出。",
                )
            )

    if has_poc_or_baseline_evidence(computed, per_problem):
        checks.append(
            make_check(
                "gate_method_poc",
                "pass",
                "G2 方法 PoC",
                "manifest 中检测到 PoC、基线、模型比较或选择依据证据。",
            )
        )
    else:
        checks.append(
            make_check(
                "gate_method_poc",
                "warning",
                "G2 方法 PoC",
                "未检测到明显的 PoC、基线或模型比较字段；建议让求解脚本记录 baseline_model、poc_results 或 model_comparison。",
                "medium",
            )
        )

    if has_validation_gate_evidence(computed, per_problem):
        checks.append(
            make_check(
                "gate_validation_outputs",
                "pass",
                "G5 模型检验证据",
                "manifest 中检测到模型检验表、指标、图像或分问题 validation_summary。",
            )
        )
    else:
        checks.append(
            make_check(
                "gate_validation_outputs",
                "warning",
                "G5 模型检验证据",
                "未检测到具体模型检验证据；模型检验章节可能退化为文字说明。",
                "medium",
            )
        )

    frozen_path = root / "results" / "frozen_numbers.json"
    frozen_field = computed.get("frozen_numbers")
    if frozen_path.exists() or bool(frozen_field):
        source = "results/frozen_numbers.json" if frozen_path.exists() else "computed_manifest.frozen_numbers"
        checks.append(make_check("gate_result_freeze", "pass", "G4 结果冻结", f"已检测到关键结果冻结快照：{source}。"))
    else:
        checks.append(
            make_check(
                "gate_result_freeze",
                "warning",
                "G4 结果冻结",
                "未检测到 results/frozen_numbers.json 或 manifest.frozen_numbers；建议在论文回填前冻结摘要和结论会引用的关键数值。",
                "medium",
            )
        )

    gate_status = computed.get("process_gates")
    if gate_status:
        checks.append(make_check("gate_status_manifest", "pass", "G1-G6 关卡状态", "manifest 已记录 process_gates。"))
    else:
        checks.append(
            make_check(
                "gate_status_manifest",
                "warning",
                "G1-G6 关卡状态",
                "manifest 未记录 process_gates；建议求解脚本写入每个关卡的状态与证据文件。",
                "low",
            )
        )
    return checks


def has_poc_or_baseline_evidence(computed: dict[str, Any], per_problem: list[dict[str, Any]]) -> bool:
    keys = ["poc_results", "model_comparison", "baseline_results", "baseline_model"]
    if any(computed.get(key) for key in keys):
        return True
    for item in per_problem:
        if any(item.get(key) for key in ["poc_result", "poc_results", "baseline_model", "model_comparison", "selected_model"]):
            return True
        metrics = item.get("metrics")
        if isinstance(metrics, dict) and any(key in metrics for key in ["baseline", "selected_model", "model_comparison"]):
            return True
    return False


def has_validation_gate_evidence(computed: dict[str, Any], per_problem: list[dict[str, Any]]) -> bool:
    if computed.get("validation_checks"):
        return True
    validation_terms = ("validation", "检验", "验证", "敏感", "误差", "残差", "feasibility", "constraint")
    for table in computed.get("tables", []) or []:
        title = str(table.get("title") if isinstance(table, dict) else table).lower()
        if any(term.lower() in title for term in validation_terms):
            return True
    for figure in computed.get("figures", []) or []:
        title = str(figure.get("title") if isinstance(figure, dict) else figure).lower()
        if any(term.lower() in title for term in validation_terms):
            return True
    for item in per_problem:
        if item.get("validation_summary"):
            return True
        metrics = item.get("metrics")
        if isinstance(metrics, dict) and any(
            key.lower() in {"mae", "rmse", "mape", "smape", "accuracy", "f1", "auc", "silhouette"}
            or "validation" in key.lower()
            or "violation" in key.lower()
            or "constraint" in key.lower()
            for key in metrics
        ):
            return True
    return False


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
        elif item["id"].startswith("gate_"):
            recommendations.append("按 G1-G6 关卡补齐证据：分问题覆盖、PoC/基线、模型检验、结果冻结和论文回填都应写入 manifest 或支撑材料。")
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
    pdfinfo = find_external_command("pdfinfo")
    if pdfinfo:
        try:
            result = run_external_command(
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
        if title in section_title or any(alias in section_title for alias in section_title_aliases(title)):
            start = match.end()
            end = matches[index + 1].start() if index + 1 < len(matches) else len(tex)
            appendix_match = re.search(r"\\appendix", tex[start:end])
            if appendix_match:
                end = start + appendix_match.start()
            return tex[start:end]
    return ""


def section_title_aliases(title: str) -> set[str]:
    aliases = {title}
    if "重述" in title or "閲嶈堪" in title:
        aliases.update({"问题重述", "闂閲嶈堪"})
    if "分析" in title or "鍒嗘瀽" in title:
        aliases.update({"问题分析", "闂鍒嗘瀽"})
    if "建立" in title or "寤虹珛" in title:
        aliases.update({"模型建立", "妯″瀷寤虹珛"})
    if "求解" in title or "姹傝В" in title:
        aliases.update({"模型求解", "妯″瀷姹傝В"})
    return aliases


def expected_problem_count(analysis: dict[str, Any], tex: str) -> int:
    tasks = analysis.get("recommended_problem", {}).get("tasks", []) if analysis else []
    if tasks:
        grouped = grouped_problem_count_from_tasks(tasks)
        if grouped:
            return grouped
        if len(tasks) <= 5:
            return len(tasks)
        tex_count = expected_problem_count_from_tex(tex)
        if tex_count:
            return tex_count
        return len(tasks)
    return expected_problem_count_from_tex(tex)


def expected_problem_count_from_tex(tex: str) -> int:
    hits = re.findall(r"\\subsection\{[^{}]*(?:问题|闂)\s*(\d+)", tex)
    numbers = [safe_int(item) for item in hits]
    numbers = [item for item in numbers if item]
    return max(numbers) if numbers else 0


def grouped_problem_count_from_tasks(tasks: list[Any]) -> int:
    numbers: set[int] = set()
    for task in tasks:
        text = str(task or "")
        match = re.search(r"(?:问题|闂)\s*([一二三四五六七八九十\d]+)", text)
        if match:
            number = chinese_problem_number(match.group(1))
            if number:
                numbers.add(number)
    return max(numbers) if len(numbers) >= 2 else 0


def chinese_problem_number(value: str) -> int:
    value = str(value or "").strip()
    if value.isdigit():
        return safe_int(value)
    mapping = {
        "一": 1,
        "二": 2,
        "三": 3,
        "四": 4,
        "五": 5,
        "六": 6,
        "七": 7,
        "八": 8,
        "九": 9,
        "十": 10,
    }
    return mapping.get(value, 0)


def problem_subsection_check(check_id: str, title: str, body: str, expected_count: int, suffix: str) -> Check:
    missing = []
    for index in range(1, expected_count + 1):
        chinese_index = index_to_chinese_problem_number(index)
        if suffix:
            pattern = rf"\\subsection\{{[^}}]*(?:问题|闂)\s*{index}[^}}]*{subsection_suffix_pattern(suffix)}[^}}]*\}}"
        else:
            pattern = rf"\\subsection\{{[^}}]*(?:问题|闂)\s*{index}[^}}]*\}}"
        paragraph_labels = [
            rf"问题\s*{index}\s*{subsection_suffix_pattern(suffix)}\s*[：:]",
            rf"问题\s*{chinese_index}\s*{subsection_suffix_pattern(suffix)}\s*[：:]",
            rf"问题\s*{index}\s*{suffix}\s*[：:]",
            rf"问题\s*{chinese_index}\s*{suffix}\s*[：:]",
            rf"问题\s*{index}\s*[：:]",
            rf"问题\s*{chinese_index}\s*[：:]",
        ]
        has_paragraph_label = any(re.search(label, body) for label in paragraph_labels)
        if not re.search(pattern, body) and not has_paragraph_label:
            missing.append(str(index))
    if missing:
        return make_check(check_id, "warning", title, "缺少子问题：" + "、".join(missing), "medium")
    return make_check(check_id, "pass", title, f"已按 {expected_count} 个子问题分别组织。")


def index_to_chinese_problem_number(index: int) -> str:
    mapping = {
        1: "一",
        2: "二",
        3: "三",
        4: "四",
        5: "五",
        6: "六",
        7: "七",
        8: "八",
        9: "九",
        10: "十",
    }
    return mapping.get(index, str(index))


def subsection_suffix_pattern(suffix: str) -> str:
    if not suffix:
        return ""
    aliases = [re.escape(suffix)]
    if "重述" in suffix or "閲嶈堪" in suffix:
        aliases.append("重述")
    if "分析" in suffix or "鍒嗘瀽" in suffix:
        aliases.append("分析")
    if "建立" in suffix or "寤虹珛" in suffix:
        aliases.append("模型建立")
    return "(?:" + "|".join(dict.fromkeys(aliases)) + ")"


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


def extract_graphic_paths(tex: str) -> list[str]:
    paths: list[str] = []
    pattern = re.compile(r"\\includegraphics(?:\[[^\]]*\])?\{(?:\\detokenize\{([^{}]+)\}|([^{}]+))\}")
    for match in pattern.finditer(tex):
        paths.append((match.group(1) or match.group(2) or "").strip())
    return paths


def resolve_graphic(root: Path, graphic: str) -> bool:
    return resolve_graphic_path(root, graphic) is not None


def resolve_graphic_path(root: Path, graphic: str) -> Path | None:
    raw = graphic.strip()
    detokenized = re.fullmatch(r"\\detokenize\{([^{}]+)\}", raw)
    if detokenized:
        raw = detokenized.group(1).strip()
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
                return candidate
        else:
            for extension in extensions:
                target = candidate.with_suffix(extension) if extension else candidate
                if target.exists():
                    return target
    return None


def strip_latex(text: str) -> str:
    text = re.sub(r"\\[a-zA-Z]+\*?(?:\[[^\]]*\])?", "", text)
    text = re.sub(r"[{}]", "", text)
    return text


def safe_int(value: Any) -> int:
    try:
        return int(str(value).strip())
    except Exception:
        return 0
