from __future__ import annotations

from pathlib import Path
from typing import Any


def write_artifacts(root: Path, analysis: dict[str, Any]) -> dict[str, str]:
    artifacts = root / "artifacts"
    paper_dir = root / "paper"
    artifacts.mkdir(parents=True, exist_ok=True)
    paper_dir.mkdir(parents=True, exist_ok=True)

    report_md = artifacts / "analysis_report.md"
    outline_md = artifacts / "outline.md"
    model_plan_md = artifacts / "model_plan.md"
    tex_path = paper_dir / "main.tex"

    report_md.write_text(render_report(analysis), encoding="utf-8")
    outline_md.write_text(render_outline(analysis), encoding="utf-8")
    model_plan_md.write_text(render_model_plan(analysis), encoding="utf-8")
    tex_path.write_text(render_latex_skeleton(analysis), encoding="utf-8")
    return {
        "analysis_report": "artifacts/analysis_report.md",
        "outline": "artifacts/outline.md",
        "model_plan": "artifacts/model_plan.md",
        "latex_skeleton": "paper/main.tex",
    }


def render_report(analysis: dict[str, Any]) -> str:
    lines = ["# 赛题分析报告\n"]
    notes = analysis["contest_summary"].get("format_notes", {})
    lines.append("## 格式与提交要点")
    for key, value in notes.items():
        if value:
            lines.append(f"- {value}")
    lines.append("\n## 选题比较")
    lines.append("综合评分按数据适配、任务清晰、模型空间、计算适配、论文可写五个维度累计，并折算为百分制后扣除风险项。")
    for p in analysis["problems"]:
        lines.append(f"### {p['id']} 题：{p['title']}")
        lines.append(f"- 模型类型：{'、'.join(p['model_types'])}")
        lines.append(f"- 附件数量：{p['data_file_count']}，子问题数量：{p['task_count']}")
        lines.append(f"- AI 适配度：{p['ai_fit']}，可行性：{p['feasibility']}，综合得分：{p['fit_score']}")
        breakdown = format_score_breakdown(p.get("score_breakdown"))
        if breakdown:
            lines.append(f"- 评分拆解：{breakdown}")
        lines.append(f"- 建议方法：{'；'.join(p['suggested_methods'])}")
        lines.append(f"- 主要风险：{'；'.join(p['risk_items'])}")
    rec = analysis["recommended_problem"]
    selected = analysis.get("selected_problem") or {}
    if selected.get("source") == "user":
        lines.append(f"\n## 选题结论\n用户已确认选择 **{rec['id']} 题：{rec['title']}**，后续自动求解、结果整合和论文生成均以该题为准。")
        system_rec = analysis.get("system_recommended_problem") or {}
        if system_rec.get("id") and system_rec.get("id") != rec.get("id"):
            lines.append(f"系统原始评分推荐为 **{system_rec['id']} 题：{system_rec.get('title', '')}**，可作为人工选择时的参考。")
    else:
        lines.append(f"\n## 推荐结论\n系统评分推荐优先选择 **{rec['id']} 题：{rec['title']}**；正式运行一键流程前仍需用户在界面中点击确认。")
    return "\n".join(lines)


def format_score_breakdown(breakdown: dict[str, Any] | None) -> str:
    if not breakdown:
        return ""
    labels = [
        ("data", "数据适配"),
        ("task", "任务清晰"),
        ("model", "模型空间"),
        ("computation", "计算适配"),
        ("paper", "论文可写"),
        ("risk_penalty", "风险扣分"),
    ]
    parts = []
    for key, label in labels:
        if key in breakdown:
            parts.append(f"{label} {breakdown[key]}")
    return "；".join(parts)


def render_outline(analysis: dict[str, Any]) -> str:
    rec = analysis["recommended_problem"]
    lines = [f"# {rec['id']} 题论文提纲\n"]
    sections = [
        "摘要",
        "问题重述",
        "问题分析",
        "模型假设",
        "符号说明",
        "模型建立",
        "模型求解",
        "模型检验",
        "模型评价与推广",
        "参考文献",
        "附录",
    ]
    for idx, section in enumerate(sections, 1):
        lines.append(f"{idx}. {section}")
    lines.append("\n## 子问题")
    for task in rec.get("tasks", []):
        lines.append(f"- {task}")
    return "\n".join(lines)


def render_model_plan(analysis: dict[str, Any]) -> str:
    rec = analysis["recommended_problem"]
    lines = [f"# {rec['id']} 题模型计划\n"]
    lines.append("## 总体路线")
    lines.append("按“数据清洗—基线模型—高级模型—验证—论文整合”的顺序推进，所有数值结果必须由代码输出。")
    lines.append("\n## 推荐方法")
    for method in rec.get("suggested_methods", []):
        lines.append(f"- {method}")
    lines.append("\n## 工作流任务")
    for item in analysis["workflow"]:
        lines.append(f"- {item['stage']}：{item['owner']} 输出 {item['output']}")
    return "\n".join(lines)


def render_latex_skeleton(analysis: dict[str, Any]) -> str:
    rec = analysis["recommended_problem"]
    tasks = rec.get("tasks", [])
    task_restatements = "\n".join(
        f"\\subsection{{问题 {idx} 重述}}\n{latex_escape(task)}\n" for idx, task in enumerate(tasks, 1)
    ) or "待补充。"
    task_analysis = "\n".join(
        f"\\subsection{{问题 {idx} 分析}}\n本问题拟采用 {latex_escape('、'.join(rec.get('suggested_methods', [])[:3]))} 等方法建立模型，并在模型求解部分给出可复现结果。\n"
        for idx, _ in enumerate(tasks, 1)
    ) or "待补充。"
    template = r"""\documentclass[UTF8,a4paper,zihao=-4]{ctexart}
\usepackage[margin=2.2cm]{geometry}
\usepackage{amsmath,amssymb,booktabs,longtable,graphicx,float,hyperref}
\usepackage{setspace}
\setstretch{1.0}
\setcounter{secnumdepth}{3}
\pagestyle{plain}
\hypersetup{hidelinks}
\title{__TITLE__}
\author{}
\date{}

\begin{document}
\thispagestyle{empty}
\begin{center}
{\zihao{3}\heiti __TITLE__}
\end{center}

\noindent\textbf{摘要：} 本文围绕__TITLE__展开建模。当前文件为自动生成的论文骨架，后续应由建模脚本产生结果表、图和指标后再填写摘要中的关键数值。

\noindent\textbf{关键词：} 数学建模；__MODEL_TYPES__；可复现分析

\newpage
\setcounter{page}{1}
\phantomsection\label{page:body-start}

\section{问题重述}
__TASK_RESTATEMENTS__

\section{问题分析}
__TASK_ANALYSIS__

\section{模型假设}
\begin{enumerate}
  \item 原始交易、监测或业务数据经清洗后可代表研究对象的主要规律。
  \item 缺失、重复和明显异常记录可通过规则识别并在附录中说明处理方式。
  \item 模型参数在预测或优化周期内保持相对稳定。
\end{enumerate}

\section{符号说明}
\begin{table}[H]
\centering
\caption{主要符号说明}
\begin{tabular}{cl}
\toprule
符号 & 含义 \\
\midrule
$x_i$ & 第 $i$ 个样本或对象的特征向量 \\
$y_i$ & 第 $i$ 个样本的目标变量 \\
$\hat y_i$ & 模型预测值 \\
$L(\cdot)$ & 损失函数或优化目标 \\
\bottomrule
\end{tabular}
\end{table}

\section{模型建立}
\subsection{数据预处理模型}
定义原始数据集为 $D=\{(x_i,y_i)\}_{i=1}^n$。首先对重复记录、缺失记录和异常记录建立规则集合 $\mathcal{R}$，得到清洗后数据集
$$
D^\ast = \mathcal{R}(D).
$$
若问题包含时间序列，则构造滞后项、滚动统计量和周期特征；若问题包含组合优化，则进一步建立目标函数与约束集合。

\subsection{预测或评价模型}
对监督预测问题，采用训练集最小化经验风险：
$$
\min_\theta \frac1n\sum_{i=1}^n L\left(y_i, f_\theta(x_i)\right)+\lambda \Omega(\theta),
$$
并通过滚动验证或交叉验证比较不同模型的泛化误差。

\subsection{优化模型}
对资源配置或方案选择问题，设决策变量为 $z$，建立
$$
\min_z C(z),\quad \text{s.t.}\quad g_j(z)\leq b_j,\ j=1,\ldots,m,
$$
其中 $C(z)$ 为成本、损失或负收益函数，$g_j(z)$ 表示业务约束、容量约束或营养约束。

\section{模型求解}
本节应按每个子问题分别给出求解过程、图表、分析与结论。所有图片和表格均应由代码生成，并与对应结果放置在同一小节。

\section{模型检验}
采用 RMSE、MAE、MAPE、$R^2$ 或优化目标变化率等指标检验模型，并进行敏感性分析与稳定性分析。

\section{模型评价与推广}
总结模型优点、局限和可推广场景。

\section{参考文献}
\begin{enumerate}
  \item 长三角高校数学建模竞赛专家组委会，第六届长三角高校数学建模竞赛赛题与格式规范，2026。
\end{enumerate}

\clearpage
\phantomsection\label{page:appendix-start}
\appendix
\section{程序代码与支撑材料说明}
核心代码、原始结果表和 AI 工具使用说明应放入支撑材料。

\end{document}
"""
    return (
        template.replace("__TITLE__", latex_escape(rec["title"]))
        .replace("__MODEL_TYPES__", latex_escape("；".join(rec.get("model_types", []))))
        .replace("__TASK_RESTATEMENTS__", task_restatements)
        .replace("__TASK_ANALYSIS__", task_analysis)
    )


def latex_escape(text: str) -> str:
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    return "".join(replacements.get(ch, ch) for ch in str(text))
