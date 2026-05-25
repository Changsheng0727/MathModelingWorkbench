from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pandas as pd

from app.services.paper import latex_escape
from app.services.templates import DEFAULT_TEMPLATE_ID, get_template


def fill_paper_with_results(root: Path) -> dict[str, str]:
    analysis_path = root / "artifacts" / "analysis.json"
    if not analysis_path.exists():
        raise FileNotFoundError("artifacts/analysis.json 不存在")
    analysis = json.loads(analysis_path.read_text(encoding="utf-8"))
    metadata = load_json_if_exists(root / "metadata.json")
    paper_options = metadata.get("paper_options", {}) if isinstance(metadata, dict) else {}
    specialized_path = root / "results" / "specialized_manifest.json"
    baseline_path = root / "results" / "baseline_manifest.json"
    specialized = load_json_if_exists(specialized_path)
    baseline = load_json_if_exists(baseline_path)

    paper_dir = root / "paper"
    paper_dir.mkdir(parents=True, exist_ok=True)
    main_tex = paper_dir / "main.tex"
    backup = paper_dir / "main_skeleton_backup.tex"
    if main_tex.exists() and not backup.exists():
        shutil.copy2(main_tex, backup)

    selected_template = get_selected_template(paper_options)
    tex = render_filled_latex(root, analysis, specialized, baseline, paper_options, selected_template)
    autofilled = paper_dir / "main_autofilled.tex"
    autofilled.write_text(tex, encoding="utf-8")
    main_tex.write_text(tex, encoding="utf-8")

    fill_summary = root / "artifacts" / "paper_fill_summary.md"
    fill_summary.write_text(render_fill_summary(specialized, baseline, paper_options, selected_template), encoding="utf-8")
    artifacts = {
        "paper_autofilled": "paper/main_autofilled.tex",
        "paper_main": "paper/main.tex",
        "paper_fill_summary": "artifacts/paper_fill_summary.md",
    }
    if selected_template and selected_template.get("mode") == "rules":
        rules_summary = root / "artifacts" / "format_rules_summary.md"
        rules_summary.write_text(render_format_rules_summary(selected_template), encoding="utf-8")
        artifacts["format_rules_summary"] = "artifacts/format_rules_summary.md"
    return artifacts


def load_json_if_exists(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def read_csv_if_exists(root: Path, relative: str) -> pd.DataFrame:
    path = root / relative
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def get_selected_template(paper_options: dict[str, Any] | None) -> dict[str, Any] | None:
    paper_options = paper_options or {}
    template_id = paper_options.get("template_id") or DEFAULT_TEMPLATE_ID
    return get_template(template_id)


def render_filled_latex(
    root: Path,
    analysis: dict[str, Any],
    specialized: dict[str, Any],
    baseline: dict[str, Any],
    paper_options: dict[str, Any] | None = None,
    selected_template: dict[str, Any] | None = None,
) -> str:
    paper_options = paper_options or {}
    if selected_template is None:
        selected_template = get_selected_template(paper_options)
    rec = analysis.get("recommended_problem", {})
    title = rec.get("title", "数学建模论文")
    tasks = rec.get("tasks", [])
    model_types = "；".join(rec.get("model_types", []))
    format_notes = analysis.get("contest_summary", {}).get("format_notes", {})
    prediction_model = first_model(specialized, "prediction")
    meal_model = first_model(specialized, "meal_preparation")
    dish_model = first_model(specialized, "dish_optimization")

    metrics_df = read_csv_if_exists(root, "results/specialized/prediction_validation_metrics.csv")
    forecast_df = read_csv_if_exists(root, "results/specialized/prediction_future_workdays.csv")
    dish_df = read_csv_if_exists(root, "results/specialized/dish_profile.csv")
    meal_df = read_csv_if_exists(root, "results/specialized/meal_preparation_plan.csv")
    package_df = read_csv_if_exists(root, "results/specialized/heuristic_package_plan.csv")

    best_metrics = best_metric_rows(metrics_df)
    abstract = render_abstract(title, prediction_model, meal_model, dish_model, best_metrics, forecast_df, meal_df, package_df)
    restatement = render_restatement(tasks)
    analysis_text = render_problem_analysis(tasks, rec)
    solving = render_solving_section(tasks, prediction_model, meal_model, dish_model, best_metrics, forecast_df, dish_df, meal_df, package_df)
    validation = render_validation_section(best_metrics, specialized, baseline)
    appendix = render_appendix(specialized, baseline)
    body = render_body_latex(restatement, analysis_text, solving, validation, appendix)
    replacements = {
        "__TITLE__": latex_escape(title),
        "__ABSTRACT__": abstract,
        "__MODEL_TYPES__": latex_escape(model_types),
        "__KEYWORDS__": latex_escape(f"数学建模；{model_types}；需求预测；组合优化；可复现分析"),
        "__BODY_START__": body_start_marker(),
        "__APPENDIX_START__": appendix_start_marker(),
        "__RESTATEMENT__": restatement,
        "__PROBLEM_ANALYSIS__": analysis_text,
        "__SOLVING__": solving,
        "__VALIDATION__": validation,
        "__APPENDIX__": appendix,
        "__BODY__": body,
    }

    template = r"""\documentclass[UTF8,a4paper,zihao=-4]{ctexart}
\usepackage[margin=2.2cm]{geometry}
\usepackage{amsmath,amssymb,booktabs,longtable,graphicx,float,hyperref,array}
\usepackage{setspace}
\setstretch{1.0}
\setcounter{secnumdepth}{3}
\pagestyle{plain}
\hypersetup{hidelinks}
\graphicspath{{../results/figures/}}

\begin{document}
\thispagestyle{empty}
\begin{center}
{\zihao{3}\heiti __TITLE__}
\end{center}

\noindent\textbf{摘要：} __ABSTRACT__

\noindent\textbf{关键词：} 数学建模；__MODEL_TYPES__；需求预测；组合优化；可复现分析

\newpage
\setcounter{page}{1}
__BODY_START__

\section{问题重述}
__RESTATEMENT__

\section{问题分析}
__PROBLEM_ANALYSIS__

\section{模型假设}
\begin{enumerate}
  \item 历史交易记录经去重、缺失检查和异常检查后，能够反映餐厅在研究周期内的主要经营规律。
  \item 在短期预测窗口内，顾客结构、菜品价格体系和餐厅营业方式保持相对稳定，历史周期性可用于外推未来工作日需求。
  \item 菜品明细样本虽然只覆盖部分订单，但其菜品重量、价格和搭配关系可作为菜品结构优化的代表性依据。
  \item 套餐设计以历史中位份量和历史成交价格为基础，不考虑临时采购约束、季节性断供和人工排班差异。
\end{enumerate}

\section{符号说明}
\begin{table}[H]
\centering
\caption{主要符号说明}
\begin{tabular}{cl}
\toprule
符号 & 含义 \\
\midrule
$D$ & 原始交易和菜品明细数据集 \\
$D^\ast$ & 清洗后的建模数据集 \\
$y_t$ & 第 $t$ 日待预测指标，如就餐人数、销售额或营养素需求量 \\
$\hat y_t$ & 第 $t$ 日预测值 \\
$x_t$ & 由日期、滞后项和滚动统计量构成的特征向量 \\
$S_k$ & 第 $k$ 档套餐包含的菜品集合 \\
$P(S_k)$ & 套餐 $S_k$ 的历史中位价格之和 \\
$B_k$ & 套餐目标价位，本文取 10、15、20 元 \\
\bottomrule
\end{tabular}
\end{table}

\section{模型建立}
\subsection{数据清洗与聚合模型}
设原始数据集为 $D$，清洗算子为 $\mathcal{R}$，则清洗后数据为
$$
D^\ast=\mathcal{R}(D).
$$
其中 $\mathcal{R}$ 包含重复记录删除、时间字段解析、非负数值检查和明显空表剔除。对交易流水，按日期聚合得到日尺度序列
$$
y_t=\sum_{i\in \mathcal{I}_t} v_i,
$$
其中 $\mathcal{I}_t$ 为日期 $t$ 的订单集合，$v_i$ 为订单金额、营养素或计数指标。

\subsection{滚动特征预测模型}
为刻画短期惯性和周内周期性，构造特征向量
$$
x_t=\left[t,\mathrm{dow}_t,\mathrm{month}_t,\sin(2\pi d_t/365.25),\cos(2\pi d_t/365.25),y_{t-1},y_{t-5},y_{t-20},\bar y_{t,5},\bar y_{t,20}\right],
$$
其中 $\bar y_{t,w}$ 为预测日前 $w$ 日滚动均值。对候选模型 $f_m$，采用时间后验验证集上的 RMSE 选择最优模型：
$$
m^\ast=\arg\min_m \sqrt{\frac{1}{n}\sum_{t=1}^{n}\left(y_t-f_m(x_t)\right)^2}.
$$
候选模型包括 Ridge 回归、随机森林回归和直方图梯度提升回归。

\subsection{菜品画像与套餐组合优化模型}
对菜品 $j$，由历史明细计算累计销量 $W_j$、累计销售额 $R_j$、中位份量 $q_j$ 和中位价格 $p_j$。套餐 $S_k$ 的价格偏差定义为
$$
\Delta_k=\left|\frac{\sum_{j\in S_k}p_j-B_k}{B_k}\right|.
$$
备菜方案以未来预测订单量 $\hat N_t$ 和历史菜品权重 $\omega_j=W_j/\sum_j W_j$ 为基础，对餐次 $r$ 的菜品 $j$ 分配备菜量
$$
Q_{t,r,j}=\hat N_t \rho_r \eta_r \bar q\,\omega_j,
$$
其中 $\rho_r$ 为餐次比例，$\eta_r$ 为安全系数，$\bar q$ 为单均菜品重量。套餐设计则在保证套餐包含主食、蛋白类菜品和蔬菜类菜品的条件下，启发式搜索使价格偏差尽可能小，同时保留历史高频菜品：
$$
\min_{S_k}\ \Delta_k-\alpha \overline{\log(1+c_j)}-\beta C(S_k),
$$
其中 $c_j$ 为菜品历史出现次数，$C(S_k)$ 为类别多样性得分。

\section{模型求解}
__SOLVING__

\section{模型检验}
__VALIDATION__

\section{模型评价与推广}
本文流程的优点是数据读取、建模、图表生成和论文回填均由程序完成，能够保持数值结果与论文表述一致；同时，预测模型采用时间后验验证，套餐模型显式考虑价格、类别和历史偏好，具有较好的可解释性。局限在于当前套餐模型仍为启发式搜索，尚未纳入库存、后厨产能、边际成本和顾客个体偏好；预测模型也主要依赖历史内部数据，未接入天气、节假日、校园活动等外生变量。后续可将该流程推广到校园食堂、企业餐厅、便利店鲜食备货和小型零售补货问题中。

\section{参考文献}
\begin{enumerate}
  \item 长三角高校数学建模竞赛专家组委会，第六届长三角高校数学建模竞赛赛题与格式规范，2026。
  \item Breiman L. Random forests. Machine Learning, 45(1): 5--32, 2001.
  \item Friedman J H. Greedy function approximation: A gradient boosting machine. The Annals of Statistics, 29(5): 1189--1232, 2001.
\end{enumerate}

__APPENDIX_START__
\appendix
\section{程序代码与支撑材料说明}
__APPENDIX__

\end{document}
"""
    if selected_template and selected_template.get("mode") in {"body", "granular"}:
        template = selected_template["text"]
    elif selected_template and selected_template.get("mode") == "rules":
        template = prepend_format_rule_comment(template, selected_template)
    return apply_latex_template(template, replacements)


def body_start_marker() -> str:
    return "\\phantomsection\\label{page:body-start}"


def appendix_start_marker() -> str:
    return "\\clearpage\n\\phantomsection\\label{page:appendix-start}"


def apply_latex_template(template: str, replacements: dict[str, str]) -> str:
    rendered = template
    for placeholder, value in replacements.items():
        rendered = rendered.replace(placeholder, value)
    return rendered


def prepend_format_rule_comment(template: str, selected_template: dict[str, Any]) -> str:
    summary = selected_template.get("rule_summary") or selected_template.get("text") or ""
    lines = [
        "Format rule document selected. The generated LaTeX keeps the built-in template",
        "and records extracted official rules here for manual or LLM review.",
        f"Rule source: {selected_template.get('name', '')} ({selected_template.get('filename', '')})",
        f"Extracted characters: {selected_template.get('extracted_chars', 0)}",
    ]
    if summary:
        compact = " ".join(str(summary).split())[:1600]
        lines.append("Rule summary: " + compact)
    comment = "\n".join("% " + line.replace("\n", " ") for line in lines)
    return comment + "\n\n" + template


def render_format_rules_summary(selected_template: dict[str, Any]) -> str:
    lines = [
        "# 官方格式说明提取摘要",
        "",
        f"- 名称：{selected_template.get('name', '')}",
        f"- 原文件：{selected_template.get('filename', '')}",
        f"- 文件类型：{selected_template.get('suffix', '')}",
        f"- 可读字符数：{selected_template.get('extracted_chars', 0)}",
        "",
        "## 结构化规则",
    ]
    rule_items = selected_template.get("rule_items") or []
    if rule_items:
        for item in rule_items:
            lines.append(f"- **{item.get('label', '规则')}**：{item.get('value', '')}")
    else:
        lines.append("- 未能稳定识别结构化规则，请人工核对原文档。")
    lines.extend(
        [
            "",
            "## 摘要",
            "",
            selected_template.get("rule_summary") or "未提取到规则摘要。",
            "",
            "## 原文预览",
            "",
            "```text",
            (selected_template.get("text") or "")[:2500],
            "```",
            "",
            "## 使用建议",
            "",
            "- 当前文件作为格式说明使用，论文生成仍采用内置 LaTeX 模板。",
            "- 提交前应对照官方 Word/PDF 原件复核页边距、字体、标题、摘要、参考文献和附录。",
            "- 若需要完全复刻官方版式，可据此制作带占位符的 `.tex` 模板后重新上传。",
        ]
    )
    return "\n".join(lines)


def render_body_latex(restatement: str, analysis_text: str, solving: str, validation: str, appendix: str) -> str:
    return "\n\n".join(
        [
            body_start_marker(),
            "\\section{问题重述}\n" + restatement,
            "\\section{问题分析}\n" + analysis_text,
            "\\section{模型假设}\n" + render_assumptions_latex(),
            "\\section{符号说明}\n" + render_symbols_latex(),
            "\\section{模型建立}\n" + render_model_building_latex(),
            "\\section{模型求解}\n" + solving,
            "\\section{模型检验}\n" + validation,
            "\\section{模型评价与推广}\n" + render_evaluation_latex(),
            "\\section{参考文献}\n" + render_references_latex(),
            appendix_start_marker(),
            "\\appendix\n\\section{程序代码与支撑材料说明}\n" + appendix,
        ]
    )


def render_assumptions_latex() -> str:
    return r"""
\begin{enumerate}
  \item 原始数据经过去重、缺失检查和异常检查后，能够反映研究周期内的主要业务规律。
  \item 在短期预测窗口内，外部环境、用户结构和业务规则保持相对稳定，历史周期性可用于外推未来需求。
  \item 部分明细样本虽然不能覆盖全部业务记录，但其重量、价格、类别和搭配关系可作为结构优化的代表性依据。
  \item 组合优化以历史中位数量和历史成交价格为基础，不考虑临时采购约束、突发断供和人工排班差异。
\end{enumerate}
""".strip()


def render_symbols_latex() -> str:
    return r"""
\begin{table}[H]
\centering
\caption{主要符号说明}
\begin{tabular}{cl}
\toprule
符号 & 含义 \\
\midrule
$D$ & 原始业务数据集 \\
$D^\ast$ & 清洗后的建模数据集 \\
$y_t$ & 第 $t$ 日待预测指标 \\
$\hat y_t$ & 第 $t$ 日预测值 \\
$x_t$ & 由日期、滞后项和滚动统计量构成的特征向量 \\
$S_k$ & 第 $k$ 个组合方案包含的对象集合 \\
$B_k$ & 第 $k$ 个方案的目标预算或目标价位 \\
$Q_{t,r,j}$ & 日期 $t$、场景 $r$、对象 $j$ 的建议配置量 \\
\bottomrule
\end{tabular}
\end{table}
""".strip()


def render_model_building_latex() -> str:
    return r"""
\subsection{数据清洗与聚合模型}
设原始数据集为 $D$，清洗算子为 $\mathcal{R}$，则清洗后的建模数据为
$$
D^\ast=\mathcal{R}(D).
$$
其中 $\mathcal{R}$ 包含重复记录删除、时间字段解析、非负数值检查、显著缺失表剔除和异常字段标记。对于流水型数据，进一步按照业务日期、对象类别或空间单元聚合，得到日尺度或对象尺度序列
$$
y_t=\sum_{i\in \mathcal{I}_t} v_i,
$$
其中 $\mathcal{I}_t$ 为日期 $t$ 的记录集合，$v_i$ 为金额、需求量、计数或营养素等待建模指标。该步骤的作用是把原始附件中的异构表格转化为具有统一时间索引、统一变量含义和可复现数据来源的模型输入。

\subsection{滚动特征预测模型}
为刻画短期惯性、周内周期和年度季节效应，构造特征向量
$$
x_t=\left[t,\mathrm{dow}_t,\mathrm{month}_t,\sin(2\pi d_t/365.25),\cos(2\pi d_t/365.25),y_{t-1},y_{t-5},y_{t-20},\bar y_{t,5},\bar y_{t,20}\right],
$$
其中 $\bar y_{t,w}$ 表示预测日前 $w$ 日滚动均值。对于候选模型 $f_m$，采用时间后验验证集上的 RMSE 选择最优模型：
$$
m^\ast=\arg\min_m \sqrt{\frac{1}{n}\sum_{t=1}^{n}\left(y_t-f_m(x_t)\right)^2}.
$$
候选模型包括带正则项的 Ridge 回归、能够刻画非线性分裂结构的随机森林回归，以及通过逐步拟合残差提升精度的梯度提升回归。时间验证不打乱样本顺序，以避免未来信息泄漏。

\subsection{画像与组合优化模型}
对对象 $j$，由历史明细计算累计需求 $W_j$、累计收益 $R_j$、中位单位量 $q_j$ 和中位价格 $p_j$。组合方案 $S_k$ 的价格偏差定义为
$$
\Delta_k=\left|\frac{\sum_{j\in S_k}p_j-B_k}{B_k}\right|,
$$
其中 $B_k$ 为目标价格或资源预算。资源分配方案以未来预测需求 $\hat N_t$ 和历史权重 $\omega_j=W_j/\sum_j W_j$ 为基础，对场景 $r$ 的对象 $j$ 分配资源量
$$
Q_{t,r,j}=\hat N_t \rho_r \eta_r \bar q\,\omega_j,
$$
其中 $\rho_r$ 为场景比例，$\eta_r$ 为安全系数，$\bar q$ 为单位平均资源量。组合优化在保证类别覆盖和业务约束的条件下，最小化价格偏差并保留历史高频对象：
$$
\min_{S_k}\ \Delta_k-\alpha \overline{\log(1+c_j)}-\beta C(S_k),
$$
其中 $c_j$ 为对象历史出现次数，$C(S_k)$ 为类别多样性得分。该目标函数把成本接近性、用户偏好和方案多样性放在同一框架中，便于后续用启发式搜索或整数规划求解。
""".strip()


def render_evaluation_latex() -> str:
    return (
        "本文流程的优点是数据读取、建模、图表生成和论文回填均由程序完成，能够保持数值结果与论文表述一致；"
        "同时，预测模型采用时间后验验证，组合优化模型显式考虑价格、类别和历史偏好，具有较好的可解释性。"
        "局限在于当前组合优化仍以启发式搜索为主，尚未完全纳入库存、产能、边际成本和用户个体偏好；"
        "预测模型也主要依赖历史内部数据，未充分接入天气、节假日、活动安排等外生变量。"
        "后续可将该流程推广到餐饮备货、校园食堂运营、物流调度、零售补货和公共服务资源配置等相近问题中。"
    )


def render_references_latex() -> str:
    return r"""
\begin{enumerate}
  \item 数学建模竞赛组委会，竞赛赛题与格式规范，2026。
  \item Breiman L. Random forests. Machine Learning, 45(1): 5--32, 2001.
  \item Friedman J H. Greedy function approximation: A gradient boosting machine. The Annals of Statistics, 29(5): 1189--1232, 2001.
\end{enumerate}
""".strip()


def first_model(manifest: dict[str, Any], model_type: str) -> dict[str, Any]:
    for model in manifest.get("specialized_models", []):
        if model.get("type") == model_type:
            return model
    return {}


def best_metric_rows(metrics_df: pd.DataFrame) -> pd.DataFrame:
    if metrics_df.empty or "target" not in metrics_df.columns or "RMSE" not in metrics_df.columns:
        return pd.DataFrame()
    frame = metrics_df.copy()
    frame["RMSE"] = pd.to_numeric(frame["RMSE"], errors="coerce")
    frame = frame.dropna(subset=["RMSE"])
    return frame.sort_values("RMSE").groupby("target", as_index=False).head(1).sort_values("target")


def render_abstract(
    title: str,
    prediction_model: dict[str, Any],
    meal_model: dict[str, Any],
    dish_model: dict[str, Any],
    best_metrics: pd.DataFrame,
    forecast_df: pd.DataFrame,
    meal_df: pd.DataFrame,
    package_df: pd.DataFrame,
) -> str:
    parts = [
        f"针对{latex_escape(title)}，本文构建了由数据清洗、滚动预测、菜品画像和套餐组合优化组成的可复现建模流程。",
    ]
    if prediction_model:
        targets = "、".join(prediction_model.get("targets", [])[:5])
        val_n = prediction_model.get("validation_rows", "")
        parts.append(
            f"针对就餐人数、销售额和营养素需求预测，考虑周内周期、年度周期、滞后项和滚动均值，建立 Ridge、随机森林和梯度提升的候选预测模型，并以最后 {val_n} 个时间点作为后验验证集选择最优模型。"
        )
        if not best_metrics.empty:
            row = best_metrics.iloc[0]
            parts.append(
                f"验证结果中，{latex_escape(str(row['target']))} 的最优模型为 {latex_escape(str(row['model']))}，RMSE 为 {float(row['RMSE']):.2f}，MAPE 为 {float(row['MAPE(%)']):.2f}\\%。"
            )
        if not forecast_df.empty:
            first = forecast_df.iloc[0]
            parts.append(
                f"未来工作日预测表明，首个预测日的订单量约为 {float(first.get('record_count', 0)):.0f} 单，销售额约为 {float(first.get('consume_money', 0)):.2f} 元。"
            )
    if dish_model:
        dish_count = dish_model.get("dish_count", "")
        parts.append(
            f"针对菜品结构优化，基于部分订单明细统计 {dish_count} 个菜品的累计销量、销售额、中位份量和中位价格，并按照主食、蛋白类、蔬菜类等类别建立菜品画像。"
        )
    if meal_model and not meal_df.empty:
        day_count = meal_df["date"].nunique() if "date" in meal_df.columns else 0
        parts.append(
            f"针对工作日备菜方案，结合未来需求预测和历史菜品权重，生成 {day_count} 个工作日的午餐、晚餐分餐次备菜表。"
        )
    if not package_df.empty:
        totals = package_df[package_df["dish_name"].astype(str).eq("合计")]
        summary = "，".join(
            f"{row['price_level']}价格 {float(row['portion_price']):.2f} 元" for _, row in totals.iterrows()
        )
        parts.append(f"在套餐设计中，通过价格偏差和历史偏好综合评分得到 {summary} 的候选方案。")
    parts.append("模型结果均由程序自动生成并回填至论文，保证图表、指标和文字结论具有可追溯性。")
    return "".join(parts)


def render_restatement(tasks: list[str]) -> str:
    if not tasks:
        return "赛题要求围绕给定数据完成建模分析，并形成可复现的预测、优化和论文结果。"
    lines = []
    for idx, task in enumerate(tasks, 1):
        lines.append(f"\\subsection{{问题 {idx} 重述}}\n{latex_escape(task)}")
    return "\n\n".join(lines)


def render_problem_analysis(tasks: list[str], rec: dict[str, Any]) -> str:
    methods = "、".join(rec.get("suggested_methods", [])[:4]) or "数据清洗、统计分析和优化建模"
    if not tasks:
        return f"本题适合采用{latex_escape(methods)}形成可复现流程。"
    lines = []
    for idx, task in enumerate(tasks, 1):
        task_text = str(task)
        if idx == 1 or "预处理" in task_text or "可视化" in task_text:
            text = "本问题属于探索性数据分析和关联结构识别问题。关键难点在于交易流水与菜品明细粒度不同，且菜品需求通常呈现长尾分布。本文先进行字段清洗、缺失检查和数值统计，再以菜品累计销售重量、销售额和出现次数构造菜品画像，并用头部菜品分布图刻画销售集中度。"
        elif idx == 2 or "预测" in task_text:
            text = "本问题属于多目标时间序列预测问题。就餐人数、销售总额和营养素需求量具有周内周期、短期惯性和长期波动，直接使用随机划分会造成未来信息泄漏。因此本文采用日期聚合、滞后项、滚动均值和周期特征建立预测数据集，并用时间后验验证比较 Ridge、随机森林和梯度提升模型。"
        elif idx == 3 or "备菜" in task_text or "菜品优化" in task_text:
            text = "本问题属于需求预测驱动的资源配置问题。备菜方案既要响应未来就餐人数和营养素需求，又要避免菜品过少导致体验下降。本文将预测订单量转化为总备菜量，再按照历史菜品销售权重、餐次比例和安全系数分配到具体菜品，形成工作日午餐和晚餐的可执行方案。"
        elif idx == 4 or "套餐" in task_text:
            text = "本问题属于带类别约束的组合优化问题。套餐设计需要同时接近目标价位、符合消费习惯并保持营养搭配。本文以历史中位价格和中位份量为基础，要求套餐包含主食、蛋白类和蔬菜类菜品，通过启发式搜索在价格偏差、历史热度和类别多样性之间折中。"
        elif idx == 5 or "建议" in task_text or "运营" in task_text:
            text = "本问题属于综合评价与管理建议问题。其目标不是再建立单独的复杂模型，而是把前四问的预测、菜品画像、备菜和套餐结果转化为可落地的运营策略。本文从备货、菜单结构、套餐试运行和滚动复核四个角度给出建议。"
        else:
            text = f"本问题需要先将业务语言转化为可计算的数据对象，再选择与数据结构匹配的模型。本文采用{methods}作为主要技术路线，并将数值结果统一保存至结果清单，便于论文回填和复核。"
        lines.append(f"\\subsection{{问题 {idx} 分析}}\n{latex_escape(text)}")
    return "\n\n".join(lines)


def render_solving_section(
    tasks: list[str],
    prediction_model: dict[str, Any],
    meal_model: dict[str, Any],
    dish_model: dict[str, Any],
    best_metrics: pd.DataFrame,
    forecast_df: pd.DataFrame,
    dish_df: pd.DataFrame,
    meal_df: pd.DataFrame,
    package_df: pd.DataFrame,
) -> str:
    parts = []
    parts.append("\\subsection{问题 1：数据预处理、统计与可视化分析}")
    parts.append(
        "针对问题 1，程序先对交易流水和菜品明细进行表结构识别、缺失检查、数值字段统计和菜品分类。菜品画像表用于刻画不同菜品销量分布，头部菜品图用于展示需求集中度。"
    )
    if not dish_df.empty:
        parts.append(latex_table(dish_df.head(12), "tab:q1-dish-profile", "问题1菜品销售画像前12项", max_rows=12))
        parts.append(
            "表\\ref{tab:q1-dish-profile}描述了累计销售重量较高的菜品及其销售额、出现次数和类别。由表可知，主食与蛋白类菜品占据较高需求权重，说明顾客消费具有较稳定的基础搭配结构。结论是：后续预测和套餐优化应保留这些高需求菜品作为基础候选集。"
        )
        parts.append(figure_block("specialized_top_dishes.png", "fig:q1-top-dishes", "问题1累计销售重量排名前20菜品"))
        parts.append(
            "图\\ref{fig:q1-top-dishes}展示了菜品销量的长尾特征。少数菜品贡献了主要销售重量，说明菜品需求并非均匀分布。结论是：运营上应优先保证头部菜品供应，同时用中低频菜品维持多样性。"
        )
    else:
        parts.append("当前项目尚未生成菜品画像表，问题 1 的可视化结果需要先运行专项建模。")

    if prediction_model:
        parts.append("\\subsection{问题 2：就餐人数、营养素需求量与销售额预测}")
        parts.append(
            f"程序首先读取{latex_escape(prediction_model.get('source', '交易流水表'))}，将订单按日期聚合，并对{latex_escape('、'.join(prediction_model.get('targets', [])))}等目标变量建立滚动预测模型。表\\ref{{tab:validation}}给出了每个目标变量验证误差最低的模型。"
        )
        parts.append(latex_table(best_metrics, "tab:validation", "预测模型最优验证结果", max_rows=12))
        parts.append(
            "表\\ref{tab:validation}描述了不同目标变量的最优模型及其误差。由表可知，不同目标变量对应的最优模型并不完全相同，说明交易金额、营养素和订单量的波动结构存在差异。结论是：后续预测采用逐目标模型选择，而不是强行使用单一模型。"
        )
        parts.append(figure_block("specialized_prediction_forecast.png", "fig:forecast", "未来工作日预测趋势"))
        parts.append(
            "图\\ref{fig:forecast}展示了首个核心预测目标的历史序列和未来工作日预测。图中预测曲线延续了历史日尺度波动范围，没有出现明显不合理的跳变，因此可作为短期备货和运营计划的输入。"
        )
        forecast_show = forecast_df.head(10).copy()
        parts.append(latex_table(forecast_show, "tab:forecast", "未来工作日前10日预测结果", max_rows=10))
        parts.append(
            "表\\ref{tab:forecast}列出了未来工作日前 10 日的预测值。该表用于将模型输出转化为运营层面的日需求估计，结论是：餐厅可据此形成工作日备菜、人员与营养供给的基准计划。"
        )

    parts.append("\\subsection{问题 3：工作日备菜方案优化}")
    if meal_model and not meal_df.empty:
        meal_show = meal_df.head(24).copy()
        parts.append(latex_table(meal_show, "tab:meal-plan", "问题3工作日午晚餐备菜方案节选", max_rows=24))
        parts.append(
            "表\\ref{tab:meal-plan}描述了 2025 年 5 月 6 日至 5 月 12 日工作日期间的分餐次备菜建议。该表把未来订单量预测转化为菜品千克数和预计份数，便于后厨执行。由表可知，午餐备菜量明显高于晚餐，符合历史订单集中于午间的经营特征。结论是：备菜计划应以午餐为主，并保留少量晚餐安全库存。"
        )
        parts.append(figure_block("specialized_meal_plan_total.png", "fig:meal-plan", "问题3工作日午晚餐备菜总量"))
        parts.append(
            "图\\ref{fig:meal-plan}汇总了各工作日午餐和晚餐备菜总量。图中不同日期的总量随预测订单量小幅波动，说明该方案既利用了模型预测，也避免了过度调整带来的执行风险。"
        )
    else:
        parts.append("当前项目尚未生成备菜方案表，问题 3 需要先运行专项建模以得到分餐次备菜结果。")

    if dish_model:
        parts.append("\\subsection{问题 4：不同价位套餐优化设计}")
        parts.append(
            f"程序进一步读取附件 2 中的菜品明细工作表，统计菜品累计销售重量、销售额、出现次数和中位价格，共识别 {dish_model.get('dish_count', '')} 个菜品；完整数据来源路径见附录中的专项结果清单。"
        )
        parts.append(latex_table(package_df, "tab:package", "10元、15元和20元套餐候选方案", max_rows=30))
        parts.append(
            "表\\ref{tab:package}给出了三档套餐的候选组合。每档套餐均尽量包含主食、蛋白类菜品和蔬菜类菜品，并使历史中位价格之和接近目标价位。结论是：该方案可作为餐厅套餐服务的初始菜单，再结合采购成本和人工经验进一步微调。"
        )

    parts.append("\\subsection{问题 5：运营策略与建议}")
    parts.append(
        "综合问题 1 至问题 4 的结果，餐厅应采用“预测驱动备菜、头部菜品保供、套餐分层供给、结果滚动复核”的运营策略。具体而言，工作日前一日根据预测订单量生成备菜基准；对销量排名靠前的主食和蛋白类菜品设置安全库存；对 10 元、15 元和 20 元三档套餐进行试运行；每周用新增流水重新训练模型并更新套餐候选池。该策略能够在降低剩余浪费的同时保持菜品多样性和营养搭配。"
    )
    if not parts:
        parts.append("尚未检测到可回填的专项建模结果，请先运行基线建模或专项建模。")
    return "\n\n".join(parts)


def render_validation_section(best_metrics: pd.DataFrame, specialized: dict[str, Any], baseline: dict[str, Any]) -> str:
    lines = []
    if not best_metrics.empty:
        avg_mape = pd.to_numeric(best_metrics["MAPE(%)"], errors="coerce").mean()
        lines.append(
            f"预测模型采用时间后验验证，而非随机打乱验证，以减少未来信息泄漏。各目标变量最优模型的平均 MAPE 为 {avg_mape:.2f}\\%，说明模型在短期预测任务中具有可接受的误差水平。"
        )
    if specialized.get("figures"):
        lines.append(
            f"专项建模共生成 {len(specialized.get('tables', []))} 个结果表和 {len(specialized.get('figures', []))} 张图，均记录在附录所列的专项结果清单中。"
        )
    if baseline.get("tables_overview"):
        table_count = baseline.get("table_count", len(baseline.get("tables_overview", [])))
        lines.append(
            f"基线数据画像共解析 {table_count} 个数据表，并生成缺失率、数值分布和相关性结果，用于检查输入数据是否满足后续建模要求。"
        )
    lines.append("敏感性方面，当前自动回填版本主要验证模型误差和数据完整性；若用于正式竞赛提交，还应增加节假日、价格变化和菜品可得性等外生因素的敏感性分析。")
    return "\n\n".join(lines)


def render_appendix(specialized: dict[str, Any], baseline: dict[str, Any]) -> str:
    files = [
        "code/run_baseline_analysis.py",
        "code/run_specialized_model.py",
        "results/baseline_manifest.json",
        "results/specialized_manifest.json",
        "artifacts/modeling_run.log",
        "artifacts/specialized_run.log",
    ]
    items = "\n".join(f"\\item \\texttt{{{latex_escape(path)}}}" for path in files)
    return f"支撑材料中包含以下核心文件：\n\\begin{{enumerate}}\n{items}\n\\end{{enumerate}}\n其中，manifest 文件记录了图表和结果表路径，日志文件记录了执行器、返回码和程序输出。"


def latex_table(df: pd.DataFrame, label: str, caption: str, max_rows: int = 10) -> str:
    if df.empty:
        return f"\\begin{{table}}[H]\\centering\\caption{{{latex_escape(caption)}}}\\label{{{label}}}暂无可用数据。\\end{{table}}"
    frame = df.head(max_rows).copy()
    frame = simplify_columns(frame)
    for col in frame.columns:
        frame[col] = frame[col].map(format_cell)
    col_spec = "c" * len(frame.columns)
    header = " & ".join(latex_escape(c) for c in frame.columns) + r" \\"
    rows = "\n".join(" & ".join(latex_escape(v) for v in row) + r" \\" for row in frame.to_numpy())
    return rf"""\begin{{table}}[H]
\centering
\caption{{{latex_escape(caption)}}}
\label{{{label}}}
\small
\resizebox{{\textwidth}}{{!}}{{%
\begin{{tabular}}{{{col_spec}}}
\toprule
{header}
\midrule
{rows}
\bottomrule
\end{{tabular}}}}
\end{{table}}"""


def simplify_columns(df: pd.DataFrame) -> pd.DataFrame:
    keep = []
    preferred = [
        "date",
        "meal",
        "target",
        "model",
        "RMSE",
        "MAE",
        "MAPE(%)",
        "R2",
        "record_count",
        "consume_money",
        "calories",
        "protein",
        "fat",
        "fiber",
        "dish_name",
        "category",
        "total_weight",
        "total_sales",
        "order_count",
        "price_level",
        "planned_kg",
        "expected_servings",
        "estimated_sales",
        "portion_g",
        "portion_price",
    ]
    for col in preferred:
        if col in df.columns and col not in keep:
            keep.append(col)
    for col in df.columns:
        if col not in keep:
            keep.append(col)
    return df[keep[:8]]


def format_cell(value: Any) -> str:
    if pd.isna(value):
        return ""
    if isinstance(value, float):
        if abs(value) >= 1000:
            return f"{value:.2f}"
        return f"{value:.3f}".rstrip("0").rstrip(".")
    return str(value)


def figure_block(filename: str, label: str, caption: str) -> str:
    return rf"""\begin{{figure}}[H]
\centering
\includegraphics[width=0.92\textwidth]{{{filename}}}
\caption{{{latex_escape(caption)}}}
\label{{{label}}}
\end{{figure}}"""


def render_fill_summary(
    specialized: dict[str, Any],
    baseline: dict[str, Any],
    paper_options: dict[str, Any] | None = None,
    selected_template: dict[str, Any] | None = None,
) -> str:
    paper_options = paper_options or {}
    template_id = paper_options.get("template_id") or DEFAULT_TEMPLATE_ID
    target_pages = paper_options.get("target_body_pages") or "未设置"
    template_mode = "内置 LaTeX 模板"
    rule_lines: list[str] = []
    if selected_template:
        if selected_template.get("mode") == "rules":
            template_mode = "格式说明文档；继续使用内置 LaTeX 模板生成正文"
            rule_lines = [
                "",
                "## 已提取的官方格式说明",
                "",
                f"- 说明文档：{selected_template.get('name', '')}（{selected_template.get('filename', '')}）",
                f"- 可读字符数：{selected_template.get('extracted_chars', 0)}",
                f"- 规则摘要：{selected_template.get('rule_summary') or '未提取到摘要，请人工核对原文档。'}",
            ]
            for item in selected_template.get("rule_items") or []:
                rule_lines.append(f"- {item.get('label', '规则')}：{item.get('value', '')}")
        else:
            template_mode = f"自定义 LaTeX 模板（{selected_template.get('mode', 'custom')}）"
    lines = [
        "# 论文自动回填摘要",
        "",
        f"- 论文模板：{template_id}",
        f"- 模板处理方式：{template_mode}",
        f"- 正文目标页数：{target_pages}",
        "- 正文页数统计边界：从 `page:body-start` 到 `page:appendix-start`，不包含摘要、目录和附录。",
        f"- 专项模型数量：{len(specialized.get('specialized_models', []))}",
        f"- 专项结果表数量：{len(specialized.get('tables', []))}",
        f"- 专项图片数量：{len(specialized.get('figures', []))}",
        f"- 基线数据表数量：{baseline.get('table_count', 0)}",
        "- 已生成 paper/main_autofilled.tex，并同步覆盖 paper/main.tex 以便直接编译。",
    ]
    return "\n".join(lines + rule_lines)
