from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from app.services.store import save_json


STANDARD_PAPER_WORKFLOW: list[dict[str, Any]] = [
    {
        "stage": "题包盘点与选题",
        "rules": [
            "盘点题面、附件数据、格式模板、提交限制、是否允许 AI 工具以及需要回答的全部子问题。",
            "由 LLM 当场比较各题的数据完整性、模型难度、创新空间、可验证性和论文可写性，再给出最终选题。",
            "选题结论必须包含子问题列表、模型链、数据需求、风险点和不可编造的数值清单。",
            "当用户补充的研究目标、模型方向或题目理解仍然模糊时，先用苏格拉底式问题澄清输出、约束和证据来源，再进入自动生成。",
        ],
    },
    {
        "stage": "建模方案设计",
        "rules": [
            "每个子问题都要明确输入、输出、目标函数、约束、候选模型、评价指标和与前后问题的依赖关系。",
            "正式生成求解脚本前先设计小样本 PoC 或基线方案：用真实附件数据验证字段映射、目标函数、约束和评价指标是否能跑通。",
            "模型建立只写数学原理、变量定义、公式、算法流程和伪代码，不写任何实验结果、图表分析或最终数值。",
            "复杂模型必须说明为什么比简单可解释模型更适合；若证据不足，优先使用可解释、稳健、易复现的方法。",
            "建模方案要同步规划材料护照：原始数据、清洗表、脚本、参数、结果图表、运行日志和人工复核点应在支撑材料中可追踪。",
        ],
    },
    {
        "stage": "求解与图表组织",
        "rules": [
            "模型求解按子问题分别组织，每个子问题都说明数据如何进入模型、参数如何确定、程序应输出哪些表格和图形。",
            "计算脚本应先跑基线或 PoC，再跑最终模型，并把模型选择依据、失败兜底、验证指标和关键中间结果写入 manifest。",
            "表格和图片必须紧跟对应结果出现，不集中放置；每个图表后都要写自然判读段落，同时交代表图内容、关键现象和子问题结论。",
            "摘要、结论和正文中的精确数值必须来自附件数据、程序输出或审查报告；未运行得到的数值只能写成待计算项目。摘要不得暴露A题/B题/C题等题号字母、具体文件名、路径或Sheet名。",
            "论文回填前冻结最终使用的关键数值、表格和图片；后续摘要、结论和模型检验只能引用冻结快照或 manifest 中的同一批结果。",
            "正文中的关键主张必须能对应到附件数据、代码结果、图表、公式推导或真实引用；不能让参考文献只停留在列表里而不支撑具体表述。",
        ],
    },
    {
        "stage": "论文撰写与格式",
        "rules": [
            "论文正文采用摘要、问题重述、问题分析、模型假设、符号说明、模型建立、模型求解、模型检验、评价与推广、参考文献、附录的标准结构。",
            "问题重述和问题分析必须按每个子问题分别叙述，而不是整段泛写。",
            "用户设置正文目标页数时，正文页数不包含摘要、目录和附录；目标为 25 页时正文不得少于 25 页。",
            "官方只给 Word、PDF 或文字格式说明时，将其作为格式规则文档提取要求，继续用可编译 LaTeX 模板生成正文。",
            "摘要遵循历年优秀论文的高密度写法：真实对象与目标开头、具体方法链承接、每个子问题形成“模型+算法+结果”句、只保留决定性数值、最后写可靠性检验。",
        ],
    },
    {
        "stage": "审稿闭环",
        "rules": [
            "编译 LaTeX 后检查 PDF 页数、A4、未加密、目录、参考文献、附录、匿名要求和交叉引用。",
            "审查摘要是否严格包含背景目标、首先/随后/再/最后的方法链、逐问题固定句式、可靠性检验和最终结论。",
            "审查模型建立与模型求解边界、分问题结构、图表自然判读、引用与附录、AI 工具披露和数值可追溯性。",
            "最终输出前执行学术诚信门禁：核对引用真实性、主张-证据对齐、数值来源、过程记录和支撑材料完整性。",
            "审稿应包含方法论审查、领域合理性审查和最强反方挑战，避免只做格式检查或无条件接受生成内容。",
            "审稿器应额外检查 G1-G6 建模关卡：题面解析、PoC 可行性、代码运行、结果冻结、论文回填和终稿审查是否留下证据。",
        ],
    },
]


STANDARD_PAPER_CHECKLIST: list[str] = [
    "摘要为一段式，接近一页但不过度堆砌，顺序为背景目标、方法链、逐问题结果、可靠性、结论。",
    "摘要中的逐问题句式为：针对问题X，考虑……因素，建立……模型，采用……算法，得到……结果；每个问题的计算结果必须紧跟在该句“得到”之后。",
    "摘要不得写题号字母、具体附件文件名、Sheet 名、路径、manifest 或日志；只写问题主题、模型算法和关键结果。",
    "摘要数值只保留能决定答案的参数、节点、目标值、误差、分类指标、阈值、排序或最终方案，避免把所有中间指标堆入摘要。",
    "问题重述逐个子问题改写题意，说明实际意义、输入输出和子问题逻辑关系。",
    "问题分析逐个子问题说明模型类别、难点、算法路线和为什么选择该路线。",
    "模型假设分点列出，每条说明合理性和作用，不能用脱离实际的假设强行简化。",
    "符号说明用表格统一变量、参数、函数和单位，全文同一符号只表示一个含义。",
    "模型建立包含数学公式、目标函数、约束、算法原理、伪代码或算法表，不出现结果分析。",
    "模型求解按模型或子问题分小节，包含可复现求解过程、程序工具、应生成的图表和结果解释。",
    "每个子问题至少保留一个基线或 PoC 证据：字段读取成功、约束可计算、目标值可算、评价指标可得或清楚说明数据不足。",
    "每张图表都有标题、位置靠近对应结果，并在图表后用一段自然文字完成内容交代、结果判读和结论落点。",
    "模型检验包含误差、稳定性、敏感性、对照实验或交叉验证，不只用一句话声称可靠。",
    "评价与推广客观写优点、不足、改进方向和可迁移场景。",
    "参考文献只列正文真实引用来源；附录放代码、原始数据、中间表、长推导和 AI 工具使用说明。",
    "正文关键主张、摘要精确数值和结论性判断必须能追溯到附件、manifest、结果表、图形、公式推导或真实引用。",
    "最终论文使用的关键数值应有冻结快照或等价 manifest 字段，避免修复脚本后正文仍引用旧数值。",
    "引用不只检查格式，还要检查主张与引用内容是否对齐；无法确认来源的文献不得作为最终论文依据。",
    "审稿至少覆盖方法论、领域解释、跨视角可迁移性和最强反方意见；重要反方问题必须进入修订建议。",
    "支撑材料包应保留过程记录、代码、运行日志、结果清单和人工复核点，便于赛后复现与追责。",
]

MODEL_METHOD_ROUTES: list[dict[str, Any]] = [
    {
        "id": "prediction_time_series",
        "name": "预测与时间序列类问题",
        "problem_signals": [
            "预测",
            "趋势",
            "时间序列",
            "销量",
            "需求",
            "客流",
            "水位",
            "价格",
            "未来",
            "predict",
            "forecast",
            "trend",
            "time series",
            "demand",
            "future",
            "early warning",
        ],
        "model_families": ["趋势分解/指数平滑", "ARIMA/SARIMA", "随机森林/梯度提升回归", "LSTM/Transformer（数据量充足时）"],
        "solver_outputs": ["训练/验证误差表", "预测结果表", "真实值-预测值对比图", "残差诊断图"],
        "validation": ["滚动时间窗验证", "MAE/RMSE/MAPE", "残差自相关检验", "关键窗口敏感性分析"],
        "paper_guidance": [
            "模型建立应说明时间粒度、滞后特征、外生变量和验证窗口，不直接写预测数值。",
            "模型求解必须给出误差指标、预测表和趋势图，并说明预测结论的适用时间范围。",
        ],
    },
    {
        "id": "optimization_resource_allocation",
        "name": "资源配置、调度与路径优化类问题",
        "problem_signals": [
            "优化",
            "最优",
            "调度",
            "路径",
            "运输",
            "选址",
            "分配",
            "成本",
            "利润",
            "容量",
            "约束",
            "optimization",
            "optimal",
            "minimum",
            "shortest",
            "scheduling",
            "schedule",
            "routing",
            "allocation",
            "cost",
            "budget",
            "constraint",
            "capacity",
        ],
        "model_families": ["线性/整数规划", "多目标规划", "网络流/最短路", "启发式搜索/遗传算法/模拟退火", "CP-SAT/约束规划"],
        "solver_outputs": ["决策变量取值表", "目标函数值与约束满足表", "资源利用率图", "敏感性分析表"],
        "validation": ["约束可行性检查", "目标值对比", "参数扰动敏感性", "求解时间和最优性缺口记录"],
        "paper_guidance": [
            "模型建立必须明确决策变量、目标函数、硬约束、软约束和线性化方式。",
            "代码求解优先使用可复现的开源求解器或启发式兜底，并输出可行性证明或约束检查表。",
        ],
    },
    {
        "id": "evaluation_decision",
        "name": "综合评价与多指标决策类问题",
        "problem_signals": [
            "评价",
            "指标",
            "排名",
            "优劣",
            "水平",
            "指数",
            "权重",
            "综合得分",
            "方案选择",
            "evaluate",
            "assessment",
            "indicator",
            "index",
            "weight",
            "score",
            "contribution",
            "performance",
        ],
        "model_families": ["熵权法", "AHP/层次分析", "TOPSIS", "灰色关联分析", "主成分分析/因子分析"],
        "solver_outputs": ["指标标准化表", "权重表", "综合得分/排序表", "指标贡献度图"],
        "validation": ["权重扰动敏感性", "不同评价方法排序一致性", "异常指标剔除对比"],
        "paper_guidance": [
            "模型建立应区分正向、逆向和区间型指标，并说明标准化与权重来源。",
            "模型求解需要同时解释排序结果和关键驱动指标，避免只给总分。",
        ],
    },
    {
        "id": "classification_clustering",
        "name": "分类、聚类与模式识别类问题",
        "problem_signals": [
            "分类",
            "识别",
            "聚类",
            "分群",
            "画像",
            "类别",
            "异常",
            "模式",
            "标签",
            "classification",
            "identify",
            "recognition",
            "clustering",
            "cluster",
            "anomaly",
            "pattern",
            "label",
        ],
        "model_families": ["K-means/层次聚类/DBSCAN", "逻辑回归/SVM/随机森林", "XGBoost/LightGBM", "孤立森林/局部异常因子"],
        "solver_outputs": ["样本类别表", "混淆矩阵或轮廓系数表", "特征重要性图", "二维降维可视化"],
        "validation": ["交叉验证", "Accuracy/F1/AUC", "轮廓系数/CH 指数", "异常样本人工复核清单"],
        "paper_guidance": [
            "模型建立要说明特征构造、类别定义、训练/测试划分或无监督聚类依据。",
            "图表分析必须解释每类样本的实际含义和对后续决策的影响。",
        ],
    },
    {
        "id": "mechanism_simulation",
        "name": "机理方程、仿真与物理约束类问题",
        "problem_signals": [
            "微分",
            "机理",
            "物理",
            "动力学",
            "仿真",
            "扩散",
            "传播",
            "力学",
            "热",
            "流体",
            "differential",
            "mechanism",
            "physical",
            "dynamics",
            "simulation",
            "mechanics",
            "stress",
            "torque",
            "preload",
            "deformation",
            "failure",
        ],
        "model_families": ["常微分/偏微分方程", "状态空间模型", "元胞自动机/蒙特卡洛仿真", "参数估计与数值积分"],
        "solver_outputs": ["参数估计表", "状态演化曲线", "仿真场景对比表", "敏感性分析图"],
        "validation": ["守恒量或边界条件检查", "参数置信区间", "步长敏感性", "与已知数据/极端情形对照"],
        "paper_guidance": [
            "模型建立要从物理量、边界条件和守恒关系推导公式，避免黑箱化。",
            "模型求解需说明数值方法、步长、初值、边界和稳定性检查。",
        ],
    },
    {
        "id": "grey_small_sample",
        "name": "小样本、灰色系统与不确定性类问题",
        "problem_signals": ["小样本", "样本较少", "缺失", "不确定", "灰色", "短期", "有限数据", "small sample", "missing", "uncertain", "uncertainty", "limited data"],
        "model_families": ["GM(1,1)/灰色预测", "Bootstrap 重采样", "贝叶斯估计", "区间估计/情景分析"],
        "solver_outputs": ["小样本描述表", "区间估计表", "情景结果表", "不确定性传播图"],
        "validation": ["后验检验", "Bootstrap 置信区间", "情景边界测试", "留一验证"],
        "paper_guidance": [
            "模型建立必须承认样本量限制，用区间或情景表达不确定性。",
            "摘要和结论不得把小样本结果写成确定性强结论。",
        ],
    },
    {
        "id": "network_graph",
        "name": "网络、图论与关系结构类问题",
        "problem_signals": ["网络", "节点", "边", "关系", "连通", "中心性", "传播", "社交", "道路", "network", "node", "edge", "relationship", "connectivity", "centrality", "road"],
        "model_families": ["图指标分析", "最短路/最大流/最小割", "社区发现", "PageRank/中心性分析"],
        "solver_outputs": ["节点/边指标表", "网络结构图", "关键节点排序表", "路径或流量方案表"],
        "validation": ["连通性检查", "关键节点删除敏感性", "不同中心性指标对比", "路径可行性检查"],
        "paper_guidance": [
            "模型建立要定义图的节点、边、权重和方向，说明它们与实际对象的对应关系。",
            "模型求解应把关键节点、路径或网络分区与题目决策目标联系起来。",
        ],
    },
]

MODEL_SELECTION_RUBRIC: list[dict[str, Any]] = [
    {"item": "数据适配", "question": "模型输入是否能由题包附件直接得到，缺失字段是否有可解释处理方式。"},
    {"item": "数学可解释性", "question": "目标函数、约束、指标或概率假设能否在模型建立中清晰表达。"},
    {"item": "计算可复现", "question": "是否能由项目内脚本生成结果表、图片、日志和 manifest。"},
    {"item": "PoC 可行性", "question": "是否已经用真实附件数据跑通小样本或基线模型，并记录失败兜底。"},
    {"item": "检验可完成", "question": "是否存在误差、敏感性、稳定性、约束可行性或对照实验。"},
    {"item": "结果冻结", "question": "论文回填前关键数值、表格、图像是否已经形成冻结快照，后续文字是否引用同一批结果。"},
    {"item": "论文可写性", "question": "是否能支持摘要、模型链、图表分析和评价推广，而不是只有一个黑箱结论。"},
    {"item": "证据主张对齐", "question": "摘要、结论和关键引用是否都能对应到真实数据、程序输出、图表或可信来源。"},
]


MODELING_PROCESS_GATES: list[dict[str, Any]] = [
    {
        "id": "G1_problem_parse",
        "name": "题面解析关",
        "purpose": "确认题目、子问题、附件、单位、约束和目标输出已经被结构化识别。",
        "pass_criteria": [
            "每个子问题都有输入、输出、目标和附件来源。",
            "缺失字段或歧义参数被列入风险清单，而不是被静默忽略。",
        ],
        "artifacts": ["artifacts/analysis.json", "artifacts/llm_problem_analysis.md"],
    },
    {
        "id": "G2_method_poc",
        "name": "方法 PoC 关",
        "purpose": "在完整建模前用真实附件数据跑通小样本或基线模型，验证方法不是纸面设想。",
        "pass_criteria": [
            "每个子问题至少有基线、PoC、字段映射检查或数据不足证明之一。",
            "复杂模型必须与简单可解释基线比较，并记录选择依据。",
        ],
        "artifacts": ["artifacts/computed_solver_spec.json", "results/computed_manifest.json"],
    },
    {
        "id": "G3_code_execution",
        "name": "代码执行关",
        "purpose": "确认 LLM 当场生成的脚本可在本地项目目录复现运行，并生成标准结果清单。",
        "pass_criteria": [
            "脚本安全校验通过，运行日志可查看。",
            "manifest 至少包含表格、图像、指标、分问题结果、模型依据和检验记录。",
        ],
        "artifacts": ["code/run_computed_solution.py", "artifacts/computed_solution_run.log", "results/computed_manifest.json"],
    },
    {
        "id": "G4_result_freeze",
        "name": "结果冻结关",
        "purpose": "在论文回填前冻结关键数值、图表和方法选择，防止摘要与正文数字漂移。",
        "pass_criteria": [
            "冻结快照或 manifest 明确记录最终引用的关键数值、表格、图片和生成时间。",
            "后续修复若改变结果，需要重新生成快照并保留原因。",
        ],
        "artifacts": ["results/frozen_numbers.json", "results/computed_manifest.json"],
    },
    {
        "id": "G5_paper_backfill",
        "name": "论文回填关",
        "purpose": "把真实计算结果嵌入对应子问题的模型求解与模型检验部分。",
        "pass_criteria": [
            "图表紧跟对应子问题，并有基于实际含义的自然判读。",
            "模型检验章节引用具体表格、数值和图像，而不是只写检验计划。",
        ],
        "artifacts": ["paper/main.tex", "artifacts/computed_result_prose.json"],
    },
    {
        "id": "G6_final_review",
        "name": "终稿审查关",
        "purpose": "在导出前检查格式、公式、图表、摘要、引用、可追溯性和支撑材料。",
        "pass_criteria": [
            "LaTeX 编译无致命错误，PDF、Word 和支撑材料包生成成功。",
            "审稿报告没有高严重失败项；警告项给出可执行修订建议。",
        ],
        "artifacts": ["artifacts/paper_review.json", "support_materials.zip"],
    },
]


BACKEND_SKILLS: list[dict[str, Any]] = [
    {
        "id": "official-mcm-icm-submission-rules",
        "name": "COMAP MCM/ICM 官方提交与摘要页规则",
        "category": "contest_rules",
        "source": "COMAP Contest Rules, Registration and Instructions",
        "source_url": "https://contest.comap.com/undergraduate/contests/mcm/instructions.html",
        "license_note": "官方规则页面，仅吸收提交边界、摘要页、匿名和 PDF 要求，不复制官方文档正文。",
        "why_selected": "官方规则明确 MCM/ICM 论文提交必须使用 PDF、第一页为 Summary Sheet、不能出现队员或学校身份信息，并给出页数与提交限制。",
        "backend_guidance": [
            "模板与审稿器必须支持摘要页、目录、参考文献、附录和匿名风险检查。",
            "当题包来自 MCM/ICM 时优先按官方页数口径审查；当用户另设正文页数目标时保留用户目标作为额外约束。",
            "AI 工具使用应在附录或提交说明中披露，具体写法服从当年官方赛题和规则。",
        ],
    },
    {
        "id": "mm-agent-four-stage-workflow",
        "name": "MM-Agent 四阶段数学建模工作流",
        "category": "math_modeling_workflow",
        "source": "usail-hkust/LLM-MM-Agent",
        "source_url": "https://github.com/usail-hkust/LLM-MM-Agent",
        "license_note": "GitHub 页面标注 GPL-3.0；README 同时提示源代码 CC BY-NC 4.0，后端仅做方法论引用，不复制代码。",
        "why_selected": "该项目面向真实数学建模问题，强调问题分析、数学建模、计算求解、报告生成的端到端流程。",
        "backend_guidance": [
            "将自动流程拆成问题分析、结构化模型建立、计算求解、报告生成四个阶段。",
            "在 LLM 选题与论文生成提示中要求先明确目标、约束、可用数据、子问题依赖关系。",
            "对模型建立加入假设、变量、目标函数、约束、算法和检验方案，不把结果写进模型建立。",
            "把代码生成、图表、误差检验和报告解释作为求解阶段的可追溯输出。",
        ],
    },
    {
        "id": "mathmodelagent-auto-paper-workflow",
        "name": "MathModelAgent 自动解题与论文生成流程",
        "category": "math_modeling_agent",
        "source": "jihe520/MathModelAgent",
        "source_url": "https://github.com/jihe520/MathModelAgent",
        "license_note": "项目 README 写明个人免费使用、商业用途需联系作者；后端仅总结公开工作流，不复制实现。",
        "why_selected": "该项目专门针对数学建模竞赛，包含上传赛题、配置 API Key、自动建模、生成论文和支撑文件等产品化思路。",
        "backend_guidance": [
            "保持 BYOK：没有 API Key 时禁止 LLM 自动解题和代码求解流程。",
            "自动流程输出题解 Markdown、代码求解规范、计算结果 manifest、LaTeX、PDF、审查报告和支撑材料包。",
            "引入模板、RAG、Web Search、HIL 与 Evaluator/Feedback 思路时必须以用户可控方式逐步开启。",
            "报告中明确哪些数值需要由数据计算得到，避免把 LLM 草稿当作最终数值结论。",
        ],
    },
    {
        "id": "modelingagent-role-routing",
        "name": "ModelingAgent 角色化建模路由",
        "category": "agent_orchestration",
        "source": "qiancheng0/ModelingAgent paper and project",
        "source_url": "https://github.com/qiancheng0/ModelingAgent",
        "license_note": "未把仓库代码并入本项目；仅吸收公开描述中的角色分工思想。",
        "why_selected": "多角色协作思路可转化为单次 LLM 流程中的自检步骤：提想法、查数据、建模型、写报告、审稿。",
        "backend_guidance": [
            "在单模型 LLM 流程中模拟多角色检查：先提想法，再检查数据，再给模型和代码求解规范，再写报告，最后审查。",
            "指定模型辅助模块检索资料时，应产出原理、适配性、伪代码、图表和论文落点。",
            "审查阶段像 Critic 一样检查结果边界、页数、图表说明、引用和可追溯性。",
        ],
    },
    {
        "id": "latexstudio-cumcmthesis-format-awareness",
        "name": "CUMCMThesis 国赛 LaTeX 模板规范意识",
        "category": "latex_template",
        "source": "latexstudio/CUMCMThesis",
        "source_url": "https://github.com/latexstudio/CUMCMThesis",
        "license_note": "模板仓库用于参考格式意识；本项目不复制 cls、示例 PDF 或模板源码。",
        "why_selected": "该模板面向全国大学生数学建模竞赛，强调让写作者专注论文内容而减少格式调整。",
        "backend_guidance": [
            "内置模板保持 A4、中文、摘要、关键词、目录、标准章节、参考文献和附录的稳定结构。",
            "用户上传 Word/PDF 格式说明时，提取页边距、标题、图表、参考文献和匿名规则，而不是强制转换模板。",
            "正式论文生成后必须运行 LaTeX 编译和静态审查，避免只生成不可编译的文本。",
        ],
    },
    {
        "id": "mcmthesis-template-awareness",
        "name": "MCM/ICM LaTeX 模板与 Summary Sheet 结构",
        "category": "latex_template",
        "source": "latexstudio-org/mcmthesis",
        "source_url": "https://github.com/latexstudio-org/mcmthesis",
        "license_note": "仓库说明为 LaTeX Project Public License v1.3c or later；后端仅吸收 MCM/ICM 模板结构意识，不复制模板文件。",
        "why_selected": "该模板专为 MCM/ICM 设计，可用于提醒后端区分 Summary Sheet、正文、参考文献和附录。",
        "backend_guidance": [
            "英文或美赛场景下应把 Summary Sheet 作为第一页，并检查摘要是否足够独立地说明方法与结论。",
            "模板层面保留 problem chosen、title、summary、solution body、references、appendix 等占位能力。",
            "当官方页数口径与用户目标页数不一致时，在审稿报告中同时列出两个口径，避免误提交。",
        ],
    },
    {
        "id": "split-latex-automation",
        "name": "分文件 LaTeX 与自动化编译工作流",
        "category": "latex_workflow",
        "source": "chenboshuo/cumcm_template",
        "source_url": "https://github.com/chenboshuo/cumcm_template",
        "license_note": "该仓库基于 CUMCMThesis 做分文件与脚本改良；后端只吸收分章节组织和自动化编译思想。",
        "why_selected": "长篇数模论文容易超长，分文件/分阶段生成可减少上下文失败，也便于以后扩展协作编辑。",
        "backend_guidance": [
            "长论文生成优先分阶段生成摘要、前置章节、模型建立、模型求解、检验和附录，再由本地程序拼接。",
            "正文页数较高时将模型建立、模型求解和模型检验作为主要扩写对象，不用附录凑页数。",
            "支撑材料包保留 LaTeX、日志、图表、JSON 结构化题解和审稿报告。",
        ],
    },
    {
        "id": "datawhale-method-map",
        "name": "Datawhale 数学建模算法体系",
        "category": "method_bank",
        "source": "datawhalechina/intro-mathmodel",
        "source_url": "https://github.com/datawhalechina/intro-mathmodel",
        "license_note": "教程型公开仓库；后端仅吸收模型类别索引与学习路线，不搬运教程内容。",
        "why_selected": "该项目整理数学建模模型与算法教程，可用于把赛题路由到优化、统计、预测、评价、图论、仿真等候选模型类别。",
        "backend_guidance": [
            "LLM 选题后先根据数据形态和目标输出选择模型类别，再选择具体算法。",
            "指定模型辅助模块返回模型原理、适用条件、输入输出、伪代码、图表建议和检验指标。",
            "模型建立章节要解释算法选择理由，不能只堆算法名。",
        ],
    },
    {
        "id": "or-llm-agent-formulation-execution-debug",
        "name": "OR-LLM-Agent 运筹优化建模-求解-调试闭环",
        "category": "optimization_agent",
        "source": "bwz96sco/or_llm_agent and OR-LLM-Agent paper",
        "source_url": "https://github.com/bwz96sco/or_llm_agent",
        "license_note": "仅吸收公开论文和仓库描述中的流程思想，不复制数据集、代码或求解器实现。",
        "why_selected": "运筹优化题在数模竞赛中常见；该方向强调把自然语言问题转成形式化数学模型，再生成求解代码并通过运行结果调试。",
        "backend_guidance": [
            "优化类题目必须在求解规范中显式写出决策变量、目标函数、约束、数据到参数的映射和可行性检查。",
            "代码生成后必须输出约束满足表、目标函数值、关键变量表和求解状态，不能只写一段文字结论。",
            "若缺少商业求解器，优先使用 scipy、PuLP/HiGHS 可用能力或启发式算法，并在论文中说明最优性边界。",
        ],
    },
    {
        "id": "optimus-evaluate-and-repair-loop",
        "name": "OptiMUS 模型生成、代码调试与结果评估循环",
        "category": "optimization_agent",
        "source": "teshnizi/OptiMUS",
        "source_url": "https://github.com/teshnizi/OptiMUS",
        "license_note": "仅吸收 agent 阶段划分和评估-修正思想，不复制实现、数据集或 prompt。",
        "why_selected": "该项目把优化建模拆成模型生成、求解代码、调试、评估和改进，适合增强本项目的代码求解规范与审稿闭环。",
        "backend_guidance": [
            "代码求解失败时应保留日志，并要求下一轮修复优先检查数据字段映射、约束维度和输出 manifest。",
            "生成论文前先评估模型可行性、结果文件完整性和数值是否来自程序输出。",
            "对优化问题记录求解器状态、运行时间、目标值和约束残差，作为论文结果可信度依据。",
        ],
    },
    {
        "id": "codegraph-local-code-intelligence",
        "name": "CodeGraph 本地代码图谱与影响分析",
        "category": "code_intelligence",
        "source": "colbymchenry/codegraph",
        "source_url": "https://github.com/colbymchenry/codegraph",
        "license_note": "MIT；本项目不打包上游 Node/Tree-sitter/MCP 实现，只吸收本地 AST 图谱、符号关系、调用图和影响分析思想，并实现轻量 Python 适配。",
        "why_selected": "自动生成求解代码后，用户需要快速理解入口函数、依赖导入、调用关系和失败影响范围；CodeGraph 的本地图谱思想适合降低盲目读文件和调试成本。",
        "backend_guidance": [
            "生成或修复求解脚本后，优先产出本地代码图谱，列出文件、符号、入口点、导入依赖、调用关系和 Mermaid 概览。",
            "代码调试提示应先参考图谱中的入口函数、调用较多函数和未解析边，再结合运行日志定位字段读取、结果写入和 manifest 生成问题。",
            "代码图谱只提供代码上下文和影响半径，不替代实际运行、数据校验、约束检查或用户业务判断。",
            "所有代码图谱分析在本地完成，不把用户赛题附件或生成代码发送给第三方服务。",
            "若未来引入完整 CodeGraph CLI/MCP，应作为可选安装项并保留 MIT 许可证说明，而不是默认强依赖。",
        ],
    },
    {
        "id": "mathmodel-resource-and-rubric-bank",
        "name": "数模资源库、优秀论文与评阅要点索引",
        "category": "paper_rubric",
        "source": "zhanwen/MathModel and personqianduixue/Math_Model",
        "source_url": "https://github.com/zhanwen/MathModel",
        "license_note": "资源合集包含论文、模板、算法和资料；后端不复制原文、代码或论文，只吸收优秀论文阅读与评阅维度。",
        "why_selected": "这些仓库覆盖国赛、美赛、研究生数模、论文模板、优秀论文和常见算法，适合转化为审稿清单。",
        "backend_guidance": [
            "审稿器关注摘要完整性、模型创新性、结果可追溯性、图表表达、灵敏度分析和推广价值。",
            "优秀论文只作为结构和评价维度参考，不把其中结果、公式或段落迁移到用户论文。",
            "参考文献列表必须来自用户题包、检索结果或通用真实资料，不生成不存在的论文条目。",
        ],
    },
    {
        "id": "mcm-icm-outstanding-paper-reading",
        "name": "MCM/ICM O 奖论文阅读规则",
        "category": "paper_rubric",
        "source": "dick20/MCM-ICM",
        "source_url": "https://github.com/dick20/MCM-ICM",
        "license_note": "优秀论文归档版权归原作者/竞赛方；后端只吸收论文阅读检查思路，不复制论文内容。",
        "why_selected": "O 奖论文可提示系统关注摘要自洽、模型链清晰、图表服务结论、检验充分和叙事紧凑。",
        "backend_guidance": [
            "论文应让读者不运行代码也能理解模型链、关键假设、结果证据和结论边界。",
            "图表不应只作装饰，必须服务于一个明确子问题或检验结论。",
            "结论和评价要承认模型局限，不夸大适用范围。",
        ],
    },
    {
        "id": "academic-research-skills-integrity-pipeline",
        "name": "Academic Research Skills 人机协作与诚信门禁",
        "category": "academic_research_pipeline",
        "source": "Imbad0202/academic-research-skills",
        "source_url": "https://github.com/Imbad0202/academic-research-skills",
        "license_note": "CC BY-NC 4.0；后端仅总结人机协作、研究流程、诚信门禁和审稿思想，不复制第三方代码、模板、agent 文件或 prompt 原文。",
        "why_selected": "该仓库把深度研究、论文写作、多视角审稿和完整学术 pipeline 组织成带人工确认、引用核查、主张对齐、材料护照和最终诚信检查的闭环，适合增强数学建模自动论文的可信度。",
        "backend_guidance": [
            "目标或模型意图不清时先进入引导澄清，确认研究问题、输出、约束、证据来源和不可自动判断的人工复核点。",
            "自动论文流程采用研究/建模、写作、诚信检查、审稿、修订、最终诚信检查和过程记录的阶段意识；关键边界不把草稿直接当成最终答案。",
            "在论文生成和结果回填中执行主张-证据对齐：摘要数值、结论判断、引用支撑和图表解释都必须能追溯到真实来源或程序输出。",
            "审查阶段模拟多视角评审，包括方法论、领域解释、跨视角影响和 Devil's Advocate 反方挑战；严重逻辑或证据问题不能被格式通过掩盖。",
            "支撑材料包保留材料护照式记录：输入材料、清洗与计算脚本、manifest、图表、日志、审查报告、AI 工具披露和人工复核清单。",
            "引用资料采用 verified-only 思路进入最终论文：检索结果只作为候选来源，未核实真实性或不能支撑对应主张的文献不得写入最终参考文献。",
        ],
    },
    {
        "id": "mathmodeling-skills-gated-delivery",
        "name": "MathModeling-skills 关卡化数模交付流程",
        "category": "math_modeling_workflow",
        "source": "KyrieZhang329/MathModeling-skills",
        "source_url": "https://github.com/KyrieZhang329/MathModeling-skills",
        "license_note": "MIT；本项目仅吸收关卡化流程、PoC、结果冻结和多层审查思想，不复制 skill 文件、提示词或项目文本。",
        "why_selected": "该仓库把数模协作拆成若干专用技能与 G1-G6 交付关卡，强调先用真实数据验证方法、再冻结结果、最后审查论文，适合提升本项目自动求解成功率。",
        "backend_guidance": [
            "在题目结构化后建立 G1-G6 关卡：题面解析、方法 PoC、代码执行、结果冻结、论文回填、终稿审查。",
            "LLM 生成求解规范时必须写出每个子问题的基线或 PoC 方案、候选模型、评价指标、失败兜底和应冻结的关键输出。",
            "代码求解脚本应把基线比较、模型选择依据、字段读取检查、验证指标、关键结果和限制写入 manifest。",
            "论文回填前优先生成或识别 frozen_numbers 快照；摘要和结论不使用未冻结、未验证或仅存在于草稿中的精确数值。",
            "审稿器增加关卡证据检查：分问题覆盖、PoC/基线证据、检验输出、冻结快照、图表回填和支撑材料是否齐全。",
        ],
    },
    {
        "id": "taste-skill-anti-template-frontend",
        "name": "Taste Skill 反模板化前端审查规则",
        "category": "frontend_client_experience",
        "source": "Leonxlnx/taste-skill",
        "source_url": "https://github.com/Leonxlnx/taste-skill",
        "license_note": "MIT；本项目仅吸收前端审查方法、信息密度、动效约束和反模板化原则，不复制 skill 文件、提示词、图片资产或实现代码。",
        "why_selected": "该仓库强调根据产品语境设置布局变化、动效强度和信息密度，避免泛用 AI 风格界面，适合把建模工作台从装饰性页面优化为高密度任务界面。",
        "backend_guidance": [
            "前端改动前先判断产品语境：本软件是数据与论文生产工作台，应优先使用可扫描、可重复操作、信息密度适中的布局。",
            "避免把所有内容都做成相同卡片；状态、输出文件、流程步骤和表单应根据用途采用不同层级、间距和强调方式。",
            "动效只服务状态变化、加载反馈和按钮响应；所有动画必须尊重 prefers-reduced-motion，避免无意义循环动画。",
            "按钮、状态、标签和文件类型使用稳定的语义色，不使用泛紫蓝渐变作为默认装饰，也不让颜色意义在不同模块里漂移。",
            "每次构建前端后要检查长中文路径、长项目名、空状态、失败状态、移动窄屏和高密度文件列表是否仍能正常阅读。",
        ],
    },
    {
        "id": "impeccable-product-ui-hardening",
        "name": "Impeccable 产品界面打磨与硬化规则",
        "category": "frontend_client_experience",
        "source": "pbakaus/impeccable",
        "source_url": "https://github.com/pbakaus/impeccable",
        "license_note": "Apache 2.0；本项目仅吸收交互状态、布局、文案、可访问性和硬化检查思想，不复制命令实现、脚本、素材或 skill 文本。",
        "why_selected": "该仓库把前端质量拆成 typography、color、layout、interaction、responsive、UX writing 和 hardening 等检查维度，适合提升桌面客户端与本地 Web UI 的稳定体验。",
        "backend_guidance": [
            "每个交互元素至少覆盖默认、悬停、键盘焦点、按下、禁用、加载、错误和成功状态；不能只设计鼠标悬停。",
            "错误和加载文案必须说明正在做什么、哪里失败、下一步怎么恢复；长流程要显示进度、当前阶段和可查看日志。",
            "标签页、文件按钮、上传入口和流程控制应能通过键盘访问，并用 aria-live 或等价机制提示动态状态变化。",
            "桌面客户端启动失败不能静默退出，应写入日志并显示可理解的错误窗口；重复启动时优先复用已运行的本地后端。",
            "使用 UTF-8、可换行文本、最小触控目标和 reduced-motion 兜底来处理中文路径、长文件名、慢网络和旧依赖环境。",
        ],
    },
    {
        "id": "research-writing-skill-engineering",
        "name": "科研写作工程化 Skill",
        "category": "scientific_writing",
        "source": "Norman-bury/research-writing-skill",
        "source_url": "https://github.com/Norman-bury/research-writing-skill",
        "license_note": "MIT；本项目不复制模板和脚本，只吸收工程化写作流程。",
        "why_selected": "该 skill 强调论文写作的目标对齐、章节拆分、LaTeX 输出、图表脚本和可恢复写作流程。",
        "backend_guidance": [
            "论文写作先对齐任务、文档类型、章节目标、证据和长度约束。",
            "长论文采用分章生成与本地拼接，避免单次 LLM 响应过长导致失败。",
            "图表标题和自然判读段落必须跟随对应结果，不能集中堆到单独图表区。",
            "输出 LaTeX 时保留正文页数标签，便于自动审查正文页数。",
        ],
    },
    {
        "id": "awesome-ai-research-writing-routing",
        "name": "Codex 研究写作路由 Skill",
        "category": "scientific_writing",
        "source": "zengrong233/awesome-ai-research-writing-skill",
        "source_url": "https://github.com/zengrong233/awesome-ai-research-writing-skill",
        "license_note": "仓库包含对上游 prompt 思路的适配整理；本项目仅集成路由思想与来源链接。",
        "why_selected": "该仓库将论文写作、论文分析、审稿、翻译、科研绘图等任务转换为 Codex skill 包结构。",
        "backend_guidance": [
            "把论文任务按阅读分析、写作改写、严格审稿、图示建模和翻译润色路由。",
            "后端提示应根据当前阶段只注入必要规则，避免把所有 prompt 全量塞入上下文。",
            "审稿模块用规则化检查输出分数、失败项、警告项和建议修订顺序。",
        ],
    },
]


def list_backend_skills() -> list[dict[str, Any]]:
    return json.loads(json.dumps(BACKEND_SKILLS, ensure_ascii=False))


def list_model_method_routes() -> list[dict[str, Any]]:
    return json.loads(json.dumps(MODEL_METHOD_ROUTES, ensure_ascii=False))


def list_model_selection_rubric() -> list[dict[str, Any]]:
    return json.loads(json.dumps(MODEL_SELECTION_RUBRIC, ensure_ascii=False))


def list_modeling_process_gates() -> list[dict[str, Any]]:
    return json.loads(json.dumps(MODELING_PROCESS_GATES, ensure_ascii=False))


def list_standard_paper_workflow() -> list[dict[str, Any]]:
    return json.loads(json.dumps(STANDARD_PAPER_WORKFLOW, ensure_ascii=False))


def list_standard_paper_checklist() -> list[str]:
    return json.loads(json.dumps(STANDARD_PAPER_CHECKLIST, ensure_ascii=False))


def render_standard_paper_rules() -> str:
    lines = ["标准数学建模论文生成规则："]
    for index, stage in enumerate(STANDARD_PAPER_WORKFLOW, 1):
        lines.append(f"{index}. {stage['stage']}")
        for rule in stage["rules"]:
            lines.append(f"  - {rule}")
    lines.append("")
    lines.append("标准论文审查清单：")
    for index, rule in enumerate(STANDARD_PAPER_CHECKLIST, 1):
        lines.append(f"{index}. {rule}")
    return "\n".join(lines)


def classify_model_routes(text: str, limit: int = 4) -> list[dict[str, Any]]:
    scored: list[tuple[int, dict[str, Any]]] = []
    haystack = text.lower()
    for route in MODEL_METHOD_ROUTES:
        score = sum(1 for signal in route["problem_signals"] if signal and signal.lower() in haystack)
        if score:
            scored.append((score, route))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [
        {
            "id": route["id"],
            "name": route["name"],
            "score": score,
            "model_families": route["model_families"],
            "solver_outputs": route["solver_outputs"],
            "validation": route["validation"],
        }
        for score, route in scored[:limit]
    ]


def suggested_methods_for_text(text: str, limit: int = 8) -> list[str]:
    methods: list[str] = []
    for route in classify_model_routes(text, limit=4):
        methods.extend(route.get("model_families", [])[:3])
    return list(dict.fromkeys(methods))[:limit]


def render_model_method_routes(max_chars: int = 9000) -> str:
    lines = ["数学建模题型-模型-结果-检验路由表："]
    for route in MODEL_METHOD_ROUTES:
        lines.extend(
            [
                f"【{route['id']}】{route['name']}",
                "- 触发信号：" + "、".join(route["problem_signals"]),
                "- 候选模型：" + "、".join(route["model_families"]),
                "- 程序输出：" + "、".join(route["solver_outputs"]),
                "- 检验方式：" + "、".join(route["validation"]),
                "- 论文落点：" + "；".join(route["paper_guidance"]),
                "",
            ]
        )
        if len("\n".join(lines)) > max_chars:
            lines.append("...（路由表已截断）")
            break
    lines.append("模型选择评分维度：" + "；".join(f"{item['item']}：{item['question']}" for item in MODEL_SELECTION_RUBRIC))
    return "\n".join(lines)


def render_modeling_process_gates(max_chars: int = 6000) -> str:
    lines = ["数学建模自动交付 G1-G6 关卡："]
    for gate in MODELING_PROCESS_GATES:
        lines.extend(
            [
                f"【{gate['id']}】{gate['name']}",
                f"- 目的：{gate['purpose']}",
                "- 通过标准：" + "；".join(gate["pass_criteria"]),
                "- 证据文件：" + "、".join(gate["artifacts"]),
                "",
            ]
        )
        if len("\n".join(lines)) > max_chars:
            lines.append("...（关卡列表已截断）")
            break
    return "\n".join(lines)


def render_backend_skill_context(max_chars: int = 12000) -> str:
    lines = [
        "后端已集成的数学建模与科研写作技能库要求如下：",
        "1. 仅吸收公开项目的方法论与流程，不复制第三方代码、模板、论文或大段文本。",
        "2. 所有精确数值必须来自上传附件、程序运行结果、检索到的真实资料或审查报告；不能由 LLM 编造。",
        "3. 自动流程默认采用 LLM 当场分析、代码求解执行和论文结果整合，必须保留可追溯输出、LaTeX 编译、论文审查和支撑材料包。",
        "4. 自动求解采用 G1-G6 关卡：题面解析、方法 PoC、代码执行、结果冻结、论文回填、终稿审查；每关都要留下证据。",
        "5. 最终论文要通过学术诚信门禁：主张-证据对齐、引用真实可核、数值来源明确、过程记录完整、人工复核点清楚。",
        "",
        render_modeling_process_gates(max_chars=3500),
        "",
        render_standard_paper_rules(),
        "",
        render_model_method_routes(max_chars=5000),
        "",
        "已吸收来源与后端执行规则：",
    ]
    text = "\n".join(lines)
    for item in BACKEND_SKILLS:
        block_lines = [
            f"【{item['id']}】{item['name']}",
            f"- 来源：{item['source']} ({item['source_url']})",
            f"- 集成理由：{item['why_selected']}",
            "- 后端执行规则：",
            *[f"  - {rule}" for rule in item["backend_guidance"]],
            "",
        ]
        block = "\n".join(block_lines)
        if len(text) + len(block) > max_chars:
            text += "\n...（技能来源列表已截断，标准论文规则已完整保留）"
            break
        text += "\n" + block
    return text


def write_backend_skill_report(root: Path) -> dict[str, str]:
    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_policy": "Summarize workflow ideas from public GitHub and official contest sources; do not vendor third-party code, templates, papers, prompts, agents, UI assets, scripts, or long text into the backend. Academic-research-skills, MathModeling-skills, taste-skill, and impeccable are integrated as methodology, process-gate, UX-quality, hardening, and integrity-review guidance only.",
        "standard_paper_workflow": list_standard_paper_workflow(),
        "standard_paper_checklist": list_standard_paper_checklist(),
        "model_method_routes": list_model_method_routes(),
        "model_selection_rubric": list_model_selection_rubric(),
        "modeling_process_gates": list_modeling_process_gates(),
        "skills": list_backend_skills(),
    }
    artifacts_dir = root / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    json_path = artifacts_dir / "backend_skill_research.json"
    md_path = artifacts_dir / "backend_skill_research.md"
    save_json(json_path, payload)
    md_path.write_text(render_backend_skill_report(payload), encoding="utf-8")
    return {
        "backend_skill_research": "artifacts/backend_skill_research.md",
        "backend_skill_research_json": "artifacts/backend_skill_research.json",
    }


def render_backend_skill_report(payload: dict[str, Any]) -> str:
    lines = [
        "# GitHub 数学建模、科研写作与诚信门禁 Skill 集成报告",
        "",
        f"- 生成时间：{payload.get('generated_at')}",
        f"- 集成策略：{payload.get('source_policy')}",
        "",
        "## 标准论文工作流",
    ]
    for stage in payload.get("standard_paper_workflow", []):
        lines.append(f"### {stage.get('stage')}")
        for rule in stage.get("rules", []):
            lines.append(f"- {rule}")
        lines.append("")

    lines.append("## 标准论文审查清单")
    for index, rule in enumerate(payload.get("standard_paper_checklist", []), 1):
        lines.append(f"{index}. {rule}")
    lines.extend(["", "## G1-G6 建模交付关卡"])
    for gate in payload.get("modeling_process_gates", []):
        lines.append(f"### {gate.get('id')} {gate.get('name')}")
        lines.append(f"- 目的：{gate.get('purpose')}")
        lines.append("- 通过标准：" + "；".join(gate.get("pass_criteria", [])))
        lines.append("- 证据文件：" + "、".join(gate.get("artifacts", [])))
        lines.append("")

    lines.extend(["", "## 题型-模型-结果路由"])
    for route in payload.get("model_method_routes", []):
        lines.extend(
            [
                f"### {route.get('name')}",
                f"- ID：`{route.get('id')}`",
                "- 触发信号：" + "、".join(route.get("problem_signals", [])),
                "- 候选模型：" + "、".join(route.get("model_families", [])),
                "- 程序输出：" + "、".join(route.get("solver_outputs", [])),
                "- 检验方式：" + "、".join(route.get("validation", [])),
                "",
            ]
        )
    lines.append("## 模型选择评分维度")
    for item in payload.get("model_selection_rubric", []):
        lines.append(f"- **{item.get('item')}**：{item.get('question')}")
    lines.extend(["", "## 已集成后端技能"])

    for index, item in enumerate(payload.get("skills", []), 1):
        lines.extend(
            [
                f"### {index}. {item.get('name')}",
                f"- ID：`{item.get('id')}`",
                f"- 分类：`{item.get('category')}`",
                f"- 来源：{item.get('source_url')}",
                f"- 授权说明：{item.get('license_note')}",
                f"- 选择理由：{item.get('why_selected')}",
                "- 后端落地规则：",
            ]
        )
        for rule in item.get("backend_guidance", []):
            lines.append(f"  - {rule}")
        lines.append("")
    lines.extend(
        [
            "## 后端使用方式",
            "- 自动解题时，`llm_solution` 会把标准论文规则和技能库摘要注入 LLM 上下文，用于选题、建模链、论文结构、摘要格式、图表说明、主张证据对齐和审查边界。",
            "- 自动流程会输出本报告，便于追踪使用了哪些公开来源和哪些规则。",
            "- 若以后要真正下载第三方 skill 或模板，应先检查许可证，并作为用户可选安装项，而不是默认打包进项目。",
            "",
        ]
    )
    return "\n".join(lines)
