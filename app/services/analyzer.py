from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from app.services.backend_skills import classify_model_routes, suggested_methods_for_text


PROBLEM_PATTERN = re.compile(
    r"(?:赛题|Problem|problem|题目)\s*[-_:：]?\s*([A-ZＡ-Ｚ])|([A-ZＡ-Ｚ])\s*题|题\s*([A-ZＡ-Ｚ])"
)
QUESTION_PATTERN = re.compile(
    r"(问题\s*[一二三四五六七八九十\d]+[\s\S]*?)(?=\n\s*问题\s*[一二三四五六七八九十\d]+|\Z)"
)
ENGLISH_QUESTION_PATTERN = re.compile(
    r"((?:Problem|Question)\s*\d+(?:\.\d+)?\s*[:.][\s\S]*?)(?=\n\s*(?:Problem|Question)\s*\d+(?:\.\d+)?\s*[:.]|\Z)",
    re.IGNORECASE,
)


def build_analysis(inventory: list[dict[str, Any]], docs: list[dict[str, str]]) -> dict[str, Any]:
    problem_docs = detect_problem_documents(docs)
    format_notes = detect_format_notes(docs)
    data_by_problem = map_data_to_problems(inventory)
    problems = []
    for problem_id, doc in sorted(problem_docs.items()):
        tasks = extract_questions(doc["text"])
        data_files = data_by_problem.get(problem_id, [])
        problem = {
            "id": problem_id,
            "title": extract_title(doc["text"], doc["name"], problem_id),
            "document": doc["path"],
            "task_count": len(tasks),
            "tasks": tasks,
            "data_files": data_files,
            "data_file_count": len(data_files),
        }
        problem.update(score_problem(problem, format_notes, source_text=doc["text"][:6000]))
        problems.append(problem)
    if not problems:
        problems.append(build_generic_problem(inventory, docs))

    recommended = choose_problem(problems)
    workflow = build_workflow(recommended, problems)
    return {
        "contest_summary": {
            "document_count": len([f for f in inventory if f["kind"] == "document"]),
            "data_count": len([f for f in inventory if f["kind"] == "data"]),
            "format_notes": format_notes,
        },
        "problems": problems,
        "recommended_problem": recommended,
        "workflow": workflow,
    }


def detect_problem_documents(docs: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    problem_docs: dict[str, dict[str, str]] = {}
    for doc in docs:
        candidate = doc["name"] + "\n" + doc["text"][:500]
        pid = normalize_problem_id(candidate)
        if not pid:
            continue
        if "格式" in doc["name"] or "提交" in doc["name"] or "承诺" in doc["name"] or "Tips" in doc["name"]:
            continue
        current = problem_docs.get(pid)
        if current is None or document_selection_score(doc) > document_selection_score(current):
            problem_docs[pid] = doc
    return problem_docs


def document_selection_score(doc: dict[str, str]) -> int:
    name = doc.get("name", "")
    text = doc.get("text", "")
    score = len(text)
    if "english" not in name.lower():
        score += 20000
    if re.search(r"[\u4e00-\u9fff]", text[:3000]):
        score += 5000
    if re.search(r"问题\s*\d", text):
        score += 3000
    return score


def normalize_problem_id(text: str) -> str | None:
    match = PROBLEM_PATTERN.search(text)
    if not match:
        return None
    raw = next(group for group in match.groups() if group)
    raw = raw.upper().replace("Ａ", "A").replace("Ｂ", "B").replace("Ｃ", "C")
    return raw


def extract_title(text: str, fallback_name: str, problem_id: str) -> str:
    for line in text.splitlines()[:20]:
        clean = line.strip()
        if "赛题" in clean and problem_id in clean:
            return clean
        if re.search(rf"\bProblem\s+{re.escape(problem_id)}\b", clean, flags=re.IGNORECASE):
            return clean
        if clean.startswith(f"{problem_id}题"):
            return clean
    return fallback_name.rsplit(".", 1)[0]


def extract_questions(text: str) -> list[str]:
    matches = [clean_question(m.group(1)) for m in QUESTION_PATTERN.finditer(text)]
    if matches:
        return matches[:8]
    english_matches = [clean_question(m.group(1)) for m in ENGLISH_QUESTION_PATTERN.finditer(text)]
    if english_matches:
        return english_matches[:8]
    lines = [line.strip() for line in text.splitlines() if line.strip().startswith("问题")]
    if lines:
        return [clean_question(line) for line in lines[:8]]
    english_lines = [
        line.strip()
        for line in text.splitlines()
        if re.match(r"^(Problem|Question)\s*\d+(?:\.\d+)?\s*[:.]", line.strip(), flags=re.IGNORECASE)
    ]
    return [clean_question(line) for line in english_lines[:8]]


def clean_question(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()[:600]


def detect_format_notes(docs: list[dict[str, str]]) -> dict[str, Any]:
    joined = "\n".join(doc["text"] for doc in docs)
    compact = re.sub(r"\s+", "", joined)
    notes = {
        "abstract_limit": "摘要一般不超过一页" if "摘要" in joined and "不超过一页" in joined else "",
        "body_page_start": "正文从第三页开始，正文页码从1开始" if "第三页" in joined and "页码" in joined else "",
        "identity_rule": "论文不得包含学校或个人身份信息" if "公平" in joined or "学校或个人信息" in joined else "",
        "submission_deadline": extract_deadline(joined),
        "eligibility_hint": "",
    }
    if "本科生和研究生可选择A，B" in compact or "本科生和研究生可选择A,B" in compact:
        notes["eligibility_hint"] = "本科生和研究生通常选择 A、B 题；C 题可能面向专科赛道。"
    return notes


def extract_deadline(text: str) -> str:
    for pattern in [
        r"电子档提交截止[^\n]*(20\d{2}\s*年\s*\d+\s*月\s*\d+\s*日\s*\d+\s*[:：]\s*\d+)",
        r"电子档提交结束[^\n]*(20\d{2}\s*年\s*\d+\s*月\s*\d+\s*日\s*\d+\s*[:：]\s*\d+)",
        r"(20\d{2}\s*年\s*\d+\s*月\s*\d+\s*日\s*10\s*[:：]\s*00)",
        r"20\d{2}\s*年\s*\d+\s*月\s*\d+\s*日\s*\d+\s*[:：]\s*\d+",
    ]:
        match = re.search(pattern, text)
        if match:
            return match.group(1) if match.lastindex else match.group(0)
    return ""


def map_data_to_problems(inventory: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in inventory:
        if record["kind"] != "data":
            continue
        pid = normalize_problem_id(record["path"]) or infer_problem_from_path(record["path"])
        if pid:
            grouped[pid].append(record)
    return grouped


def infer_problem_from_path(path: str) -> str | None:
    parts = re.split(r"[\\/]+", path)
    for pid in ["A", "B", "C", "D", "E"]:
        if any(part.upper() == pid for part in parts):
            return pid
        if (
            f"赛题{pid}" in path
            or f"赛题 {pid}" in path
            or f"{pid}题" in path
            or f"{pid} 题" in path
            or f"Problem {pid}" in path
            or f"Problem-{pid}" in path
            or f"problem-{pid}" in path
            or f"题{pid}" in path
        ):
            return pid
    return None


def score_problem(problem: dict[str, Any], format_notes: dict[str, Any], source_text: str = "") -> dict[str, Any]:
    text = " ".join([problem["title"], " ".join(problem["tasks"]), source_text])
    route_matches = classify_model_routes(text)
    types = []
    if has_any(
        text,
        [
            "预测",
            "需求",
            "销量",
            "时间序列",
            "回归",
            "分类",
            "聚类",
            "关联",
            "predict",
            "forecast",
            "time series",
            "regression",
            "classification",
            "clustering",
            "correlation",
            "early warning",
        ],
    ):
        types.append("数据挖掘/预测")
    if has_any(
        text,
        [
            "优化",
            "最优",
            "调度",
            "路径",
            "设备",
            "成本",
            "利润",
            "套餐",
            "optimization",
            "optimal",
            "minimum",
            "shortest",
            "schedule",
            "scheduling",
            "allocation",
            "resource",
            "budget",
            "cost",
        ],
    ):
        types.append("运筹优化")
    if has_any(text, ["评价", "指数", "相似性", "可行性", "指标", "evaluate", "assessment", "indicator", "index", "performance", "contribution"]):
        types.append("综合评价")
    if has_any(
        text,
        [
            "微分",
            "力学",
            "支护",
            "物理",
            "仿真",
            "differential",
            "mechanics",
            "physical",
            "simulation",
            "stress",
            "preload",
            "torque",
            "deformation",
            "slope",
            "rock",
            "bolt",
            "failure",
        ],
    ):
        types.append("机理建模")
    if not types:
        types.append("综合建模")

    data_score = score_data_availability(problem)
    task_score = score_task_clarity(problem)
    model_score = score_model_richness(text, types, route_matches)
    computation_score = score_computation_fit(text, problem, route_matches)
    paper_score = score_paper_writability(text, problem, types, route_matches)
    risk_score = 0
    risks = []
    if has_any(text, ["搜集相关数据", "公开数据", "自行搜集", "collect data", "public data"]):
        risk_score += 12
        risks.append("需要外部数据源确认")
    if problem["data_file_count"] == 0:
        risk_score += 18
        risks.append("附件数据较少或没有结构化数据")
    if problem["id"] == "C" and "A、B" in str(format_notes.get("eligibility_hint", "")):
        risk_score += 18
        risks.append("赛道适配风险")
    if has_any(text, ["力学", "支护", "CT", "成像", "微分方程", "mechanics", "support", "stress", "bolt", "preload"]) and problem["data_file_count"] < 3:
        risk_score += 8
        risks.append("领域机理推导要求较高")
    if problem["task_count"] == 0:
        risk_score += 10
        risks.append("子问题未稳定识别")

    positive = data_score + task_score + model_score + computation_score + paper_score
    total = clamp(round(positive / 110 * 100 - risk_score, 1), 0, 100)
    score_breakdown = {
        "data": data_score,
        "task": task_score,
        "model": model_score,
        "computation": computation_score,
        "paper": paper_score,
        "risk_penalty": risk_score,
        "total": total,
    }
    return {
        "model_types": types,
        "fit_score": total,
        "score_breakdown": score_breakdown,
        "risk_items": risks or ["常规建模风险"],
        "ai_fit": level(computation_score, high=17, medium=10),
        "feasibility": level(data_score + task_score + model_score - risk_score, high=42, medium=25),
        "suggested_methods": suggest_methods(types, text),
        "method_routes": route_matches,
    }


def has_any(text: str, words: list[str]) -> bool:
    lowered = text.lower()
    return any(word.lower() in lowered for word in words)


def keyword_score(text: str, words: list[str], per_hit: float, cap: float) -> float:
    hits = sum(text.count(word) for word in words)
    return min(hits * per_hit, cap)


def clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def level(value: float, high: float, medium: float) -> str:
    if value >= high:
        return "高"
    if value >= medium:
        return "中"
    return "低"


def score_data_availability(problem: dict[str, Any]) -> float:
    files = problem.get("data_files") or []
    file_count = len(files)
    if file_count == 0:
        return 0
    count_score = min(4 + file_count * 3, 13)
    total_rows = 0
    max_cols = 0
    sheet_count = 0
    readable_files = 0
    suffixes = {str(item.get("suffix", "")).lower() for item in files if item.get("suffix")}
    for item in files:
        schema = item.get("schema") or {}
        if schema and not schema.get("error"):
            readable_files += 1
        rows, cols, sheets = schema_shape(schema)
        total_rows += max(rows, 0)
        max_cols = max(max_cols, cols)
        sheet_count += sheets
    row_score = 0
    if total_rows >= 1000:
        row_score = 6
    elif total_rows >= 100:
        row_score = 4
    elif total_rows >= 10:
        row_score = 2
    col_score = 0
    if max_cols >= 10:
        col_score = 4
    elif max_cols >= 4:
        col_score = 3
    elif max_cols >= 2:
        col_score = 1
    sheet_score = min(sheet_count, 3)
    diversity_score = min(len(suffixes) * 1.5, 3)
    readability_score = min(readable_files * 1.2, 4)
    return round(clamp(count_score + row_score + col_score + sheet_score + diversity_score + readability_score, 0, 25), 1)


def schema_shape(schema: dict[str, Any]) -> tuple[int, int, int]:
    if schema.get("type") == "csv":
        rows = schema.get("rows") if isinstance(schema.get("rows"), int) else 0
        cols = schema.get("cols") if isinstance(schema.get("cols"), int) else 0
        return rows, cols, 1 if rows or cols else 0
    if schema.get("type") == "excel":
        sheets = schema.get("sheets") or []
        rows = 0
        cols = 0
        for sheet in sheets:
            sheet_rows = sheet.get("rows") if isinstance(sheet.get("rows"), int) else 0
            sheet_cols = sheet.get("cols") if isinstance(sheet.get("cols"), int) else 0
            rows += max(sheet_rows - 1, 0)
            cols = max(cols, sheet_cols)
        return rows, cols, len(sheets)
    return 0, 0, 0


def score_task_clarity(problem: dict[str, Any]) -> float:
    tasks = problem.get("tasks") or []
    count_score = min(len(tasks) * 4, 16)
    detail_score = min(sum(1 for task in tasks if len(task) >= 80) * 2, 6)
    action_score = min(
        sum(
            1
            for task in tasks
            if has_any(
                task,
                [
                    "建立",
                    "求解",
                    "分析",
                    "评价",
                    "预测",
                    "优化",
                    "验证",
                    "设计",
                    "establish",
                    "develop",
                    "solve",
                    "analyze",
                    "evaluate",
                    "predict",
                    "optimize",
                    "verify",
                    "calculate",
                    "identify",
                ],
            )
        )
        * 1.5,
        5,
    )
    title_score = 3 if problem.get("title") and problem.get("title") != "未识别到标准赛题编号" else 0
    return round(clamp(count_score + detail_score + action_score + title_score, 0, 25), 1)


def score_model_richness(text: str, types: list[str], routes: list[dict[str, Any]]) -> float:
    route_score = min(len(routes) * 4, 12)
    type_score = min(len(set(types)) * 3, 9)
    formula_signals = keyword_score(
        text,
        ["约束", "目标", "指标", "概率", "路径", "权重", "距离", "周期", "时间", "constraint", "objective", "indicator", "probability", "distance", "time"],
        1,
        6,
    )
    return clamp(route_score + type_score + formula_signals, 0, 20)


def score_computation_fit(text: str, problem: dict[str, Any], routes: list[dict[str, Any]]) -> float:
    data_factor = min(problem.get("data_file_count", 0) * 2, 6)
    code_signals = keyword_score(
        text,
        [
            "预测",
            "优化",
            "分类",
            "聚类",
            "回归",
            "路径",
            "调度",
            "评价",
            "仿真",
            "可视化",
            "敏感性",
            "predict",
            "optimize",
            "classify",
            "cluster",
            "regression",
            "path",
            "schedule",
            "evaluate",
            "simulate",
            "visualize",
            "sensitivity",
        ],
        2,
        10,
    )
    route_factor = min(len(routes) * 2, 4)
    return clamp(data_factor + code_signals + route_factor, 0, 20)


def score_paper_writability(text: str, problem: dict[str, Any], types: list[str], routes: list[dict[str, Any]]) -> float:
    task_factor = min(problem.get("task_count", 0) * 2, 6)
    narrative_factor = keyword_score(
        text,
        [
            "背景",
            "原因",
            "影响",
            "比较",
            "评价",
            "推广",
            "方案",
            "效果",
            "规律",
            "机制",
            "background",
            "cause",
            "influence",
            "compare",
            "evaluate",
            "solution",
            "effect",
            "mechanism",
        ],
        1.5,
        7,
    )
    method_factor = min((len(types) + len(routes)) * 1.5, 5)
    return clamp(task_factor + narrative_factor + method_factor, 0, 20)


def suggest_methods(types: list[str], text: str) -> list[str]:
    methods: list[str] = []
    methods.extend(suggested_methods_for_text(text))
    if "数据挖掘/预测" in types:
        methods.extend(["时间序列特征工程", "随机森林/梯度提升预测", "滚动验证"])
    if "运筹优化" in types:
        methods.extend(["整数规划", "启发式搜索", "约束满足与敏感性分析"])
    if "综合评价" in types:
        methods.extend(["熵权法/AHP", "TOPSIS", "聚类与相似度度量"])
    if "机理建模" in types:
        methods.extend(["机理方程推导", "参数拟合", "约束优化"])
    if "套餐" in text:
        methods.append("营养约束组合优化")
    return list(dict.fromkeys(methods))


def choose_problem(problems: list[dict[str, Any]]) -> dict[str, Any]:
    return max(problems, key=lambda p: p.get("fit_score", 0))


def apply_problem_selection(analysis: dict[str, Any], problem_id: str, source: str = "user") -> dict[str, Any]:
    problem = find_problem(analysis, problem_id)
    if not problem:
        raise ValueError(f"未找到 {problem_id} 题。")
    if "system_recommended_problem" not in analysis:
        analysis["system_recommended_problem"] = analysis.get("recommended_problem", {})
    selected = dict(problem)
    analysis["recommended_problem"] = selected
    analysis["selected_problem"] = {
        "id": selected.get("id", ""),
        "title": selected.get("title", ""),
        "source": source,
    }
    analysis["workflow"] = build_workflow(selected, analysis.get("problems", []))
    return selected


def find_problem(analysis: dict[str, Any], problem_id: str) -> dict[str, Any] | None:
    wanted = str(problem_id or "").strip().upper()
    for problem in analysis.get("problems", []) or []:
        if str(problem.get("id", "")).strip().upper() == wanted:
            return problem
    return None


def build_workflow(recommended: dict[str, Any], problems: list[dict[str, Any]]) -> list[dict[str, Any]]:
    pid = recommended["id"]
    title = recommended["title"]
    return [
        {"stage": "01 赛题确认", "owner": "ProblemAnalyzer", "output": f"确认选择 {pid} 题：{title}"},
        {"stage": "02 数据盘点", "owner": "DataInspector", "output": "字段说明、缺失值、异常值、时间范围和附件映射表"},
        {"stage": "03 模型方案", "owner": "ModelPlanner", "output": "每个子问题的模型、变量、目标函数、约束和验证指标"},
        {"stage": "04 代码实现", "owner": "CodeRunner", "output": "可复现脚本、结果表、图片和运行日志"},
        {"stage": "05 结果检验", "owner": "ResultValidator", "output": "误差指标、敏感性分析、稳定性分析和结果来源检查"},
        {"stage": "06 论文撰写", "owner": "PaperWriter", "output": "符合竞赛格式的 LaTeX 初稿"},
        {"stage": "07 论文审查", "owner": "PaperReviewer", "output": "摘要、图表说明、引用、页码和身份信息检查"},
        {"stage": "08 提交打包", "owner": "Packager", "output": "论文 PDF、结果表、支撑材料和 AI 工具说明"},
    ]


def build_generic_problem(inventory: list[dict[str, Any]], docs: list[dict[str, str]]) -> dict[str, Any]:
    text = " ".join((doc.get("name", "") + " " + doc.get("text", "")) for doc in docs)
    problem = {
        "id": "Unknown",
        "title": "未识别到标准赛题编号",
        "document": docs[0]["path"] if docs else "",
        "task_count": 0,
        "tasks": [],
        "data_files": [f for f in inventory if f["kind"] == "data"],
        "data_file_count": len([f for f in inventory if f["kind"] == "data"]),
    }
    problem.update(score_problem(problem, {}, source_text=text[:10000]))
    problem["risk_items"] = list(dict.fromkeys(["需要人工确认赛题结构", *problem.get("risk_items", [])]))
    if not problem.get("suggested_methods"):
        problem["suggested_methods"] = ["数据清洗", "探索性分析", "基线模型"]
    return problem
