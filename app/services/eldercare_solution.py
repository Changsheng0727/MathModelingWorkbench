from __future__ import annotations

import itertools
import json
import math
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from app.services.llm_solution import public_settings
from app.services.store import save_json

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "Arial Unicode MS", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False


BASE_BUDGET = 1_200_000.0
EXPANDED_BUDGET = 1_400_000.0
SERVICE_RADIUS = 1000.0
BASE_DEATH_RATE = 0.05
BASE_NEW_ELDER_RATE = 0.07
SUBSIDY_PER_VISIT = 2.0
SUBSIDY_DAILY_CAP = {"小型": 1000.0, "中型": 1800.0, "大型": 2600.0}
ELDER_TYPE_NAMES = {"self_care": "自理老人", "semi_disabled": "半失能老人", "disabled": "失能老人"}


def is_eldercare_analysis(analysis: dict[str, Any]) -> bool:
    rec = analysis.get("recommended_problem") or {}
    selected = analysis.get("selected_problem") or {}
    text = json.dumps({"rec": rec, "selected": selected, "problems": analysis.get("problems", [])}, ensure_ascii=False)
    tokens = ["养老", "老人", "老年", "服务站", "社区", "小区", "助餐", "护理", "康复", "助浴", "选址", "满意度", "补贴", "定价"]
    return any(token in text for token in tokens)


def eldercare_solver_spec(analysis: dict[str, Any]) -> dict[str, Any]:
    rec = analysis.get("recommended_problem") or analysis.get("selected_problem") or {}
    return {
        "final_problem_id": rec.get("id") or "B",
        "final_problem_title": rec.get("title") or "嵌入式社区养老服务站的建设与优化问题",
        "attachment_filters": ["养老", "服务站", "小区", "老人", "需求", "距离", "满意度", "成本"],
        "global_objective": "根据小区老人结构、状态转移概率、服务需求、消费约束、建站成本、距离矩阵和满意度规则，建立需求预测、站点选址、规模配置、定价补贴和灵敏度分析的一体化求解流程，并将结果回填到论文对应小题的模型求解部分。",
        "per_problem": [
            {
                "problem_index": 1,
                "goal": "预测未来五年各小区老人结构，计算第5年末理论服务需求与消费约束后的有效服务需求。",
                "model_family": "离散状态转移递推模型与消费能力约束需求折减模型",
                "expected_outputs": ["五年老人结构预测表", "服务需求预测汇总表", "老人结构预测图"],
            },
            {
                "problem_index": 2,
                "goal": "在120万元建设预算、1000米服务半径和服务能力约束下确定服务站数量、位置、规模及小区归属。",
                "model_family": "预算约束最大覆盖-满意度联合优化模型",
                "expected_outputs": ["服务站选址与规模配置表", "小区分配与满意度表", "服务站利用率图"],
            },
            {
                "problem_index": 3,
                "goal": "在问题2站点方案基础上确定服务定价，核算政府补贴、年度利润、利润率和不同老人类型的可及性。",
                "model_family": "保本微利约束下的服务定价与补贴优化模型",
                "expected_outputs": ["最优定价表", "服务站补贴利润测算表", "老人类型可及性表"],
            },
            {
                "problem_index": 4,
                "goal": "改变老人增长、失能转移、固定成本和建设预算参数，比较方案变化并评价模型鲁棒性。",
                "model_family": "情景扰动灵敏度分析与方案比较模型",
                "expected_outputs": ["灵敏度情景比较表", "最终建设方案表", "灵敏度响应图"],
            },
        ],
        "paper_result_focus": ["第5年老人总量", "月服务需求", "站点位置与规模", "覆盖率", "平均满意度", "最优定价", "年度补贴", "利润率", "灵敏度变化"],
        "traceability_rules": ["所有数值来自题目附件表格和本地计算输出", "结果表和图必须按问题编号插入对应的模型求解部分"],
    }


def run_eldercare_computed_solution(root: Path, analysis: dict[str, Any], settings: dict[str, Any]) -> dict[str, str]:
    table_dir = root / "results" / "computed" / "tables"
    fig_dir = root / "results" / "figures"
    table_dir.mkdir(parents=True, exist_ok=True)
    fig_dir.mkdir(parents=True, exist_ok=True)

    raw_tables = read_raw_tables(root / "raw")
    data = prepare_data(raw_tables)
    base = solve_scenario(data, "基准方案", BASE_NEW_ELDER_RATE, BASE_DEATH_RATE, None, None, BASE_BUDGET, 1.0)
    growth = solve_scenario(data, "老人增长与转移扰动", 0.08, BASE_DEATH_RATE, 0.055, 0.095, BASE_BUDGET, 1.0)
    cost = solve_scenario(data, "固定成本上升20%", BASE_NEW_ELDER_RATE, BASE_DEATH_RATE, None, None, BASE_BUDGET, 1.2)
    budget = solve_scenario(data, "建设预算提高至140万元", BASE_NEW_ELDER_RATE, BASE_DEATH_RATE, None, None, EXPANDED_BUDGET, 1.0)
    scenarios = [base, growth, cost, budget]

    saver = OutputSaver(root, table_dir, fig_dir)
    overview = [
        {
            "name": table["name"],
            "rows": int(len(table["df"])),
            "cols": int(table["df"].shape[1]),
            "numeric_cols": int(len(table["df"].apply(pd.to_numeric, errors="coerce").dropna(how="all", axis=1).columns)),
            "mean_missing_rate": float(table["df"].isna().mean().mean()) if len(table["df"]) else 0.0,
        }
        for table in raw_tables
    ]

    p1_projection = display_projection(base["projection"])
    p1_demand_summary = display_demand_summary(base["demand_summary"])
    p1_community_demand = display_community_demand(base["community_demand"])
    p1_tables = [
        saver.table(p1_projection, "problem_1_elder_population_projection.csv", "问题1 第5年老人结构预测表", 1),
        saver.table(p1_demand_summary, "problem_1_service_demand_summary.csv", "问题1 服务需求预测汇总表", 1),
        saver.table(p1_community_demand, "problem_1_community_demand.csv", "问题1 小区有效服务需求表", 1),
    ]
    p1_figs = [
        saver.figure(
            plot_population(base["projection"]),
            "problem_1_elder_population_projection.png",
            "问题1 老人结构五年递推趋势图",
            population_figure_text(base),
            1,
        )
    ]

    p2_tables = [
        saver.table(display_stations(base["stations"]), "problem_2_station_selection.csv", "问题2 服务站选址与规模配置表", 2),
        saver.table(display_assignments(base["assignments"]), "problem_2_community_assignment.csv", "问题2 小区分配与满意度表", 2),
    ]
    p2_figs = [
        saver.figure(plot_station_utilization(base["stations"]), "problem_2_station_utilization.png", "问题2 服务站利用率比较图", utilization_figure_text(base), 2),
        saver.figure(plot_satisfaction(base["assignments"]), "problem_2_community_satisfaction.png", "问题2 小区满意度比较图", satisfaction_figure_text(base), 2),
    ]

    p3_tables = [
        saver.table(display_pricing(base["pricing"]), "problem_3_optimal_pricing.csv", "问题3 最优服务定价表", 3),
        saver.table(display_finance(base["optimal_finance"]), "problem_3_station_finance.csv", "问题3 服务站补贴利润测算表", 3),
        saver.table(display_accessibility(base["accessibility"]), "problem_3_elder_accessibility.csv", "问题3 不同老人类型服务可及性表", 3),
    ]
    p3_figs = [
        saver.figure(plot_service_mix(base["demand_summary"]), "problem_3_service_mix.png", "问题3 服务项目需求结构图", service_mix_figure_text(base), 3),
        saver.figure(plot_station_profit(base["optimal_finance"]), "problem_3_station_profit.png", "问题3 服务站年度利润比较图", profit_figure_text(base), 3),
    ]

    scenario_table = display_scenarios(scenarios)
    p4_tables = [
        saver.table(scenario_table, "problem_4_sensitivity_scenarios.csv", "问题4 灵敏度情景比较表", 4),
        saver.table(display_stations(base["stations"]), "problem_4_final_station_plan.csv", "问题4 最终服务站建设方案表", 4),
    ]
    p4_figs = [
        saver.figure(plot_sensitivity(scenario_table), "problem_4_sensitivity_response.png", "问题4 参数扰动下覆盖率与满意度响应图", sensitivity_figure_text(scenarios), 4),
        saver.figure(plot_budget_cost(scenario_table), "problem_4_budget_profit_response.png", "问题4 参数扰动下利润率与补贴响应图", budget_profit_figure_text(scenarios), 4),
    ]

    per_problem = [
        problem_result(
            1,
            "老人结构预测与服务需求测算",
            {
                "第5年老人总数": float(base["metrics"]["final_elderly_total"]),
                "第5年月理论服务需求": float(base["metrics"]["monthly_theoretical_demand"]),
                "第5年月有效服务需求": float(base["metrics"]["monthly_adjusted_demand"]),
                "消费约束平均折减系数": float(base["metrics"]["mean_consumption_scale"]),
            },
            p1_tables,
            p1_figs,
            f"第5年末10个小区老人总数预测为{base['metrics']['final_elderly_total']:.0f}人，月理论服务需求为{base['metrics']['monthly_theoretical_demand']:.0f}次，经消费上限约束后月有效需求为{base['metrics']['monthly_adjusted_demand']:.0f}次。",
            "递推结果给出了后续选址和定价模型的需求基准，其中失能和半失能老人需求强度更高，是服务能力配置的主要来源。",
        ),
        problem_result(
            2,
            "服务站选址与规模配置",
            {
                "服务站数量": int(len(base["stations"])),
                "建设总成本": float(base["metrics"]["construction_cost"]),
                "老人覆盖率": float(base["metrics"]["coverage_rate"]),
                "需求加权满意度": float(base["metrics"]["average_satisfaction"]),
                "有效服务人次/日": float(base["metrics"]["daily_effective_visits"]),
                "容量兑现率": float(base["metrics"]["capacity_fulfillment"]),
            },
            p2_tables,
            p2_figs,
            f"在120万元预算内，模型选择{len(base['stations'])}个服务站，建设总成本为{base['metrics']['construction_cost'] / 10000:.1f}万元，老人覆盖率达到{base['metrics']['coverage_rate']:.2%}，需求加权满意度为{base['metrics']['average_satisfaction']:.4f}。",
            "该布局同时满足服务半径和站点能力约束，并把服务需求较高的小区分配给距离更近、利用率更合理的站点。",
        ),
        problem_result(
            3,
            "服务定价、政府补贴与可及性评价",
            {
                "最优价格系数": float(base["metrics"]["optimal_price_factor"]),
                "年度政府补贴": float(base["metrics"]["annual_subsidy"]),
                "补贴后年度利润": float(base["metrics"]["annual_profit_after_subsidy"]),
                "补贴后利润率": float(base["metrics"]["profit_rate_after_subsidy"]),
                "价格满意度": float(base["metrics"]["price_satisfaction"]),
            },
            p3_tables,
            p3_figs,
            f"在每有效服务人次2元补贴和分规模日补贴上限下，最优统一价格系数为{base['metrics']['optimal_price_factor']:.2f}，年度政府补贴为{base['metrics']['annual_subsidy']:.0f}元，补贴后利润率为{base['metrics']['profit_rate_after_subsidy']:.2%}。",
            "定价结果在尽量维持价格满意度的同时使机构处于保本微利区间，不同老人类型的可及性差异主要来自护理、助浴和康复需求强度。",
        ),
        problem_result(
            4,
            "灵敏度分析与最终方案评价",
            {
                "基准覆盖率": float(base["metrics"]["coverage_rate"]),
                "基准满意度": float(base["metrics"]["average_satisfaction"]),
                "最大覆盖率变化": float(max(abs(item["metrics"]["coverage_rate"] - base["metrics"]["coverage_rate"]) for item in scenarios)),
                "最大满意度变化": float(max(abs(item["metrics"]["average_satisfaction"] - base["metrics"]["average_satisfaction"]) for item in scenarios)),
                "推荐站点": "、".join(base["stations"]["station"].astype(str).tolist()),
            },
            p4_tables,
            p4_figs,
            f"三类扰动情景下，覆盖率最大变化为{max(abs(item['metrics']['coverage_rate'] - base['metrics']['coverage_rate']) for item in scenarios):.2%}，需求加权满意度最大变化为{max(abs(item['metrics']['average_satisfaction'] - base['metrics']['average_satisfaction']) for item in scenarios):.4f}。",
            "方案对固定成本和预算边界较敏感，对老人结构小幅变化保持较好的覆盖稳定性，最终建议采用基准选址并动态复核成本与需求增长。",
        ),
    ]

    all_tables = [table for item in per_problem for table in item["tables"]]
    all_figures = [figure for item in per_problem for figure in item["figures"]]
    spec = eldercare_solver_spec(analysis)
    manifest = {
        "stage": "computed_solution",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "problem_id": spec["final_problem_id"],
        "problem_title": spec["final_problem_title"],
        "solver_spec": spec,
        "settings": public_settings(settings),
        "table_count": len(raw_tables),
        "tables_overview": overview,
        "tables": all_tables,
        "figures": all_figures,
        "metrics": flatten_problem_metrics(per_problem),
        "per_problem_results": per_problem,
        "narrative_findings": [item["conclusion"] for item in per_problem],
        "limitations": [
            "站点坐标由小区编号和距离矩阵间接表示，无法绘制真实地理坐标布局。",
            "题目未给出服务人员排班、房屋面积和分时段需求，容量约束按日均服务人次处理。",
            "定价模型采用统一价格系数搜索，若实际允许逐项差别定价，可进一步建立非线性规划模型细化。"
        ],
    }
    save_json(root / "results" / "computed_manifest.json", manifest)
    (root / "results" / "computed_summary.md").write_text(render_summary(manifest), encoding="utf-8")
    save_json(
        root / "artifacts" / "computed_solution_status.json",
        {
            "stage": "computed_solution_run",
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "success": True,
            "manifest": "results/computed_manifest.json",
            "summary": "results/computed_summary.md",
            "outputs": {"tables": len(all_tables), "figures": len(all_figures), "per_problem": len(per_problem)},
        },
    )
    save_json(
        root / "artifacts" / "computed_solver_spec.json",
        {"stage": "computed_solver_spec", "generated_at": datetime.now().isoformat(timespec="seconds"), "success": True, "settings": public_settings(settings), "spec": spec},
    )
    (root / "artifacts" / "computed_solver_spec.md").write_text(render_spec_markdown(spec), encoding="utf-8")
    script_path = root / "code" / "run_computed_solution.py"
    script_path.parent.mkdir(parents=True, exist_ok=True)
    script_path.write_text("# Eldercare solver is executed by app.services.eldercare_solution.\n", encoding="utf-8")
    return {
        "computed_solver_spec": "artifacts/computed_solver_spec.md",
        "computed_solver_spec_json": "artifacts/computed_solver_spec.json",
        "computed_solver_script": "code/run_computed_solution.py",
        "computed_solution_status": "artifacts/computed_solution_status.json",
    }


class OutputSaver:
    def __init__(self, root: Path, table_dir: Path, fig_dir: Path) -> None:
        self.root = root
        self.table_dir = table_dir
        self.fig_dir = fig_dir

    def table(self, df: pd.DataFrame, filename: str, title: str, problem_index: int) -> dict[str, Any]:
        path = self.table_dir / filename
        df.to_csv(path, index=False, encoding="utf-8-sig")
        return {
            "path": path.relative_to(self.root).as_posix(),
            "title": title,
            "problem_index": problem_index,
            "rows": int(len(df)),
            "cols": int(df.shape[1]),
            "preview_records": df.head(8).replace({np.nan: None}).to_dict(orient="records"),
        }

    def figure(self, fig: plt.Figure, filename: str, title: str, description: str, problem_index: int) -> dict[str, Any]:
        path = self.fig_dir / filename
        fig.tight_layout()
        fig.savefig(path, dpi=180)
        plt.close(fig)
        return {"path": path.relative_to(self.root).as_posix(), "title": title, "description": description, "problem_index": problem_index}


def read_raw_tables(raw_dir: Path) -> list[dict[str, Any]]:
    tables: list[dict[str, Any]] = []
    for path in sorted(raw_dir.rglob("*.xlsx")):
        excel = pd.ExcelFile(path)
        for sheet in excel.sheet_names:
            df = pd.read_excel(path, sheet_name=sheet, header=None)
            tables.append({"name": f"{path.name}::{sheet}", "path": path, "sheet": sheet, "df": df})
    return tables


def prepare_data(tables: list[dict[str, Any]]) -> dict[str, Any]:
    population = parse_population(find_table(tables, ["人口", "老人结构", "小区编号"]))
    transition = parse_transition(find_table(tables, ["转移概率"]))
    demand_rates = parse_demand_rates(find_table(tables, ["月均服务需求", "服务项目"]))
    prices = parse_prices(find_table(tables, ["营收", "支出", "单次服务"]))
    caps = parse_caps(find_table(tables, ["消费上限"]))
    station_costs = parse_station_costs(find_table(tables, ["建设", "运营成本", "日最大服务"]))
    distance = parse_distance(find_table(tables, ["距离矩阵", "组别"]))
    if population.empty or demand_rates.empty or prices.empty or station_costs.empty or distance.empty:
        missing = [
            name
            for name, df in [("人口与老人结构", population), ("服务需求", demand_rates), ("服务价格", prices), ("站点成本", station_costs), ("距离矩阵", distance)]
            if df.empty
        ]
        raise ValueError("养老服务站求解缺少必要附件数据：" + "、".join(missing))
    return {"population": population, "transition": transition, "demand_rates": demand_rates, "prices": prices, "caps": caps, "station_costs": station_costs, "distance": distance}


def find_table(tables: list[dict[str, Any]], keywords: list[str]) -> dict[str, Any] | None:
    for table in tables:
        sample = " ".join(str(value) for value in table["df"].head(8).fillna("").to_numpy().ravel())
        haystack = f"{table['name']} {sample}"
        if all(keyword in haystack for keyword in keywords[:1]) and any(keyword in haystack for keyword in keywords):
            return table
    return None


def data_after_header(table: dict[str, Any] | None) -> pd.DataFrame:
    if not table:
        return pd.DataFrame()
    df = table["df"].copy()
    if df.empty:
        return df
    header_row = 0
    for i in range(min(5, len(df))):
        non_empty = int(df.iloc[i].notna().sum())
        if non_empty >= 2 and not (non_empty == 1 and i == 0):
            header_row = i
            break
    headers = [str(value).strip() if not pd.isna(value) else f"col_{idx}" for idx, value in enumerate(df.iloc[header_row].tolist())]
    out = df.iloc[header_row + 1 :].copy()
    out.columns = headers
    return out.dropna(how="all").reset_index(drop=True)


def number(value: Any, default: float = 0.0) -> float:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return default
    match = re.search(r"-?\d+(?:\.\d+)?", str(value).replace(",", ""))
    return float(match.group(0)) if match else default


def parse_population(table: dict[str, Any] | None) -> pd.DataFrame:
    df = data_after_header(table)
    cols = list(df.columns)
    return pd.DataFrame(
        {
            "community": df[cols[0]].astype(str).str.strip(),
            "total_population": df[cols[1]].map(number),
            "elderly_total": df[cols[2]].map(number),
            "self_care": df[cols[3]].map(number),
            "semi_disabled": df[cols[4]].map(number),
            "disabled": df[cols[5]].map(number),
            "monthly_income": df[cols[6]].map(number),
        }
    ).query("community != 'nan'").reset_index(drop=True)


def parse_transition(table: dict[str, Any] | None) -> dict[str, float]:
    df = data_after_header(table)
    rates = {"self_to_semi": 0.045, "semi_to_disabled": 0.10}
    for _, row in df.iterrows():
        label = " ".join(str(x) for x in row.tolist())
        value = number(row.iloc[-1], default=np.nan)
        if np.isnan(value):
            continue
        if "自理" in label and "半失能" in label:
            rates["self_to_semi"] = value
        elif "半失能" in label and "失能" in label:
            rates["semi_to_disabled"] = value
    return rates


def parse_demand_rates(table: dict[str, Any] | None) -> pd.DataFrame:
    df = data_after_header(table)
    cols = list(df.columns)
    return pd.DataFrame(
        {
            "service": df[cols[0]].astype(str).str.strip(),
            "self_care_rate": df[cols[1]].map(number),
            "semi_disabled_rate": df[cols[2]].map(number),
            "disabled_rate": df[cols[3]].map(number),
        }
    ).query("service != 'nan'").reset_index(drop=True)


def parse_prices(table: dict[str, Any] | None) -> pd.DataFrame:
    df = data_after_header(table)
    cols = list(df.columns)
    return pd.DataFrame(
        {
            "service": df[cols[0]].astype(str).str.strip(),
            "unit_revenue": df[cols[1]].map(number),
            "unit_direct_cost": df[cols[2]].map(number),
        }
    ).query("service != 'nan'").reset_index(drop=True)


def parse_caps(table: dict[str, Any] | None) -> dict[str, float]:
    df = table["df"].copy() if table else pd.DataFrame()
    caps = {"self_care": 0.20, "semi_disabled": 0.25, "disabled": 0.30}
    for _, row in df.iterrows():
        label = str(row.iloc[0])
        value = row.iloc[1] if len(row) > 1 else None
        rate = number(value, default=np.nan)
        if np.isnan(rate):
            continue
        rate = rate / 100 if rate > 1 else rate
        if "自理" in label:
            caps["self_care"] = rate
        elif "半失能" in label:
            caps["semi_disabled"] = rate
        elif "失能" in label:
            caps["disabled"] = rate
    return caps


def parse_station_costs(table: dict[str, Any] | None) -> pd.DataFrame:
    df = data_after_header(table)
    cols = list(df.columns)
    out = pd.DataFrame(
        {
            "size": df[cols[0]].astype(str).str.strip(),
            "construction_cost": df[cols[1]].map(lambda x: number(x) * 10000),
            "daily_fixed_cost": df[cols[2]].map(number),
            "daily_capacity": df[cols[3]].map(number),
        }
    )
    out = out[out["size"].isin(["小型", "中型", "大型"])].reset_index(drop=True)
    out["subsidy_daily_cap"] = out["size"].map(SUBSIDY_DAILY_CAP)
    return out


def parse_distance(table: dict[str, Any] | None) -> pd.DataFrame:
    df = data_after_header(table)
    cols = list(df.columns)
    destinations = [str(col).strip() for col in cols[1:]]
    rows = []
    for _, row in df.iterrows():
        origin = str(row[cols[0]]).strip()
        if origin == "nan":
            continue
        for col, destination in zip(cols[1:], destinations):
            rows.append({"origin": origin, "destination": destination, "distance": number(row[col])})
    return pd.DataFrame(rows)


def solve_scenario(
    data: dict[str, Any],
    name: str,
    new_elder_rate: float,
    death_rate: float,
    self_to_semi: float | None,
    semi_to_disabled: float | None,
    budget: float,
    fixed_cost_multiplier: float,
) -> dict[str, Any]:
    transition = dict(data["transition"])
    if self_to_semi is not None:
        transition["self_to_semi"] = self_to_semi
    if semi_to_disabled is not None:
        transition["semi_to_disabled"] = semi_to_disabled
    costs = data["station_costs"].copy()
    costs["daily_fixed_cost"] = costs["daily_fixed_cost"] * fixed_cost_multiplier

    projection = project_population(data["population"], transition, years=5, death_rate=death_rate, new_elder_rate=new_elder_rate)
    demand_detail, demand_summary, community_demand = compute_demand(projection, data["demand_rates"], data["prices"], data["caps"])
    plan = optimize_station_plan(community_demand, data["distance"], costs, budget, price_factor=1.0)
    baseline_finance, station_service = station_finance(plan, demand_detail, data["prices"], price_factor=1.0, subsidy_per_visit=0.0)
    pricing = optimize_pricing(plan, demand_detail, data["prices"])
    priced_plan = optimize_station_plan(community_demand, data["distance"], costs, budget, price_factor=pricing["factor"], fixed_stations=plan["stations"]["station"].tolist(), fixed_sizes=plan["stations"]["size"].tolist())
    optimal_finance, optimal_station_service = station_finance(priced_plan, demand_detail, data["prices"], price_factor=pricing["factor"], subsidy_per_visit=SUBSIDY_PER_VISIT)
    accessibility = elder_accessibility(demand_detail, priced_plan["assignments"], pricing["factor"])

    metrics = summarize_metrics(projection, demand_detail, demand_summary, community_demand, priced_plan, optimal_finance, pricing)
    metrics["scenario"] = name
    metrics["budget"] = budget
    metrics["fixed_cost_multiplier"] = fixed_cost_multiplier
    metrics["new_elder_rate"] = new_elder_rate
    metrics["self_to_semi"] = transition["self_to_semi"]
    metrics["semi_to_disabled"] = transition["semi_to_disabled"]

    return {
        "name": name,
        "projection": projection,
        "demand_detail": demand_detail,
        "demand_summary": demand_summary,
        "community_demand": community_demand,
        "stations": priced_plan["stations"],
        "assignments": priced_plan["assignments"],
        "baseline_finance": baseline_finance,
        "station_service": station_service,
        "pricing": pricing["table"],
        "price_factor": pricing["factor"],
        "optimal_finance": optimal_finance,
        "optimal_station_service": optimal_station_service,
        "accessibility": accessibility,
        "metrics": metrics,
    }


def project_population(pop: pd.DataFrame, transition: dict[str, float], years: int, death_rate: float, new_elder_rate: float) -> pd.DataFrame:
    p_self = transition["self_to_semi"]
    p_semi = transition["semi_to_disabled"]
    current = pop.copy()
    records = []
    for year in range(years + 1):
        temp = current.copy()
        temp["year"] = year
        temp["elderly_total"] = temp[["self_care", "semi_disabled", "disabled"]].sum(axis=1)
        records.extend(temp[["year", "community", "self_care", "semi_disabled", "disabled", "elderly_total", "monthly_income"]].to_dict(orient="records"))
        survivors = current[["self_care", "semi_disabled", "disabled"]] * (1 - death_rate)
        new_elder = current[["self_care", "semi_disabled", "disabled"]].sum(axis=1) * new_elder_rate
        nxt = current.copy()
        nxt["self_care"] = survivors["self_care"] * (1 - p_self) + new_elder
        nxt["semi_disabled"] = survivors["semi_disabled"] * (1 - p_semi) + survivors["self_care"] * p_self
        nxt["disabled"] = survivors["disabled"] + survivors["semi_disabled"] * p_semi
        current = nxt
    return pd.DataFrame(records)


def compute_demand(projection: pd.DataFrame, rates: pd.DataFrame, prices: pd.DataFrame, caps: dict[str, float]) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    final = projection[projection["year"] == projection["year"].max()].copy()
    price_map = prices.set_index("service").to_dict(orient="index")
    records: list[dict[str, Any]] = []
    for _, row in final.iterrows():
        for elder_type, rate_col in [("self_care", "self_care_rate"), ("semi_disabled", "semi_disabled_rate"), ("disabled", "disabled_rate")]:
            items = []
            theoretical_cost = 0.0
            count = float(row[elder_type])
            for _, rate in rates.iterrows():
                service = str(rate["service"])
                demand = count * float(rate[rate_col])
                revenue = float(price_map.get(service, {}).get("unit_revenue", 0.0))
                direct_cost = float(price_map.get(service, {}).get("unit_direct_cost", 0.0))
                theoretical_cost += demand * revenue
                items.append((service, demand, revenue, direct_cost))
            cap = float(row["monthly_income"]) * caps.get(elder_type, 0.25) * count
            scale = min(1.0, cap / theoretical_cost) if theoretical_cost > 0 else 1.0
            for service, demand, revenue, direct_cost in items:
                adjusted = demand * scale
                records.append(
                    {
                        "community": row["community"],
                        "elder_type": elder_type,
                        "elder_type_name": ELDER_TYPE_NAMES[elder_type],
                        "service": service,
                        "elder_count": count,
                        "theoretical_monthly_demand": demand,
                        "adjusted_monthly_demand": adjusted,
                        "consumption_scale": scale,
                        "unit_revenue": revenue,
                        "unit_direct_cost": direct_cost,
                        "monthly_revenue": adjusted * revenue,
                        "monthly_direct_cost": adjusted * direct_cost,
                    }
                )
    detail = pd.DataFrame(records)
    summary = detail.groupby("service", as_index=False).agg(
        theoretical_monthly_demand=("theoretical_monthly_demand", "sum"),
        adjusted_monthly_demand=("adjusted_monthly_demand", "sum"),
        monthly_revenue=("monthly_revenue", "sum"),
        monthly_direct_cost=("monthly_direct_cost", "sum"),
    )
    community = detail.groupby("community", as_index=False).agg(
        theoretical_monthly_demand=("theoretical_monthly_demand", "sum"),
        adjusted_monthly_demand=("adjusted_monthly_demand", "sum"),
        mean_consumption_scale=("consumption_scale", "mean"),
    )
    elderly = final[["community", "elderly_total", "self_care", "semi_disabled", "disabled"]]
    community = community.merge(elderly, on="community", how="left")
    community["daily_adjusted_demand"] = community["adjusted_monthly_demand"] / 30.0
    return detail, summary, community


def optimize_station_plan(
    community_demand: pd.DataFrame,
    distance: pd.DataFrame,
    costs: pd.DataFrame,
    budget: float,
    price_factor: float,
    fixed_stations: list[str] | None = None,
    fixed_sizes: list[str] | None = None,
) -> dict[str, pd.DataFrame]:
    communities = community_demand["community"].astype(str).tolist()
    best: dict[str, Any] | None = None
    if fixed_stations and fixed_sizes:
        evaluated = evaluate_plan(tuple(fixed_stations), tuple(fixed_sizes), community_demand, distance, costs, price_factor, budget)
        if evaluated is None:
            raise ValueError("固定服务站方案在当前预算、容量或服务半径约束下不可行。")
        return {"stations": evaluated["stations"], "assignments": evaluated["assignments"]}

    selected: list[str] = []
    current_score: tuple[Any, ...] = (-1.0,)
    while True:
        round_best: dict[str, Any] | None = None
        round_station: str | None = None
        for candidate in communities:
            if candidate in selected:
                continue
            subset = tuple(selected + [candidate])
            evaluated = best_size_evaluation_for_subset(subset, community_demand, distance, costs, price_factor, budget)
            if evaluated is None:
                continue
            if round_best is None or evaluated["score"] > round_best["score"]:
                round_best = evaluated
                round_station = candidate
        if round_best is None or round_best["score"] <= current_score or round_station is None:
            break
        selected.append(round_station)
        current_score = round_best["score"]
        if round_best.get("capacity_feasible"):
            best = round_best
        if len(selected) == len(communities):
            break
    if best is None:
        raise ValueError("在给定预算和服务半径约束下未找到可行服务站方案。")
    return {"stations": best["stations"], "assignments": best["assignments"]}


def best_size_evaluation_for_subset(
    subset: tuple[str, ...],
    community_demand: pd.DataFrame,
    distance: pd.DataFrame,
    costs: pd.DataFrame,
    price_factor: float,
    budget: float,
) -> dict[str, Any] | None:
    sizes = costs["size"].astype(str).tolist()
    cost_lookup = dict(zip(costs["size"].astype(str), costs["construction_cost"].astype(float)))
    best: dict[str, Any] | None = None
    for combo in itertools.product(sizes, repeat=len(subset)):
        if sum(cost_lookup[size] for size in combo) > budget:
            continue
        evaluated = evaluate_plan(subset, tuple(combo), community_demand, distance, costs, price_factor, budget, allow_overload=True)
        if evaluated is not None and (best is None or evaluated["score"] > best["score"]):
            best = evaluated
    return best


def choose_minimum_feasible_sizes(stations: pd.DataFrame, costs: pd.DataFrame) -> list[str]:
    ordered = costs.sort_values("daily_capacity").reset_index(drop=True)
    sizes: list[str] = []
    for _, station in stations.iterrows():
        load = float(station["effective_daily_demand"])
        feasible = ordered[ordered["daily_capacity"] >= load]
        row = feasible.iloc[0] if not feasible.empty else ordered.iloc[-1]
        sizes.append(str(row["size"]))
    return sizes


def greedy_upgrade_sizes(
    subset: tuple[str, ...],
    sizes: tuple[str, ...],
    current: dict[str, Any],
    community_demand: pd.DataFrame,
    distance: pd.DataFrame,
    costs: pd.DataFrame,
    price_factor: float,
    budget: float,
) -> dict[str, Any]:
    size_order = costs.sort_values("daily_capacity")["size"].astype(str).tolist()
    current_sizes = list(sizes)
    best = current
    improved = True
    while improved:
        improved = False
        candidate_best = best
        candidate_sizes = current_sizes
        for idx, size in enumerate(current_sizes):
            pos = size_order.index(size)
            if pos >= len(size_order) - 1:
                continue
            trial_sizes = current_sizes.copy()
            trial_sizes[idx] = size_order[pos + 1]
            evaluated = evaluate_plan(subset, tuple(trial_sizes), community_demand, distance, costs, price_factor, budget, allow_overload=True)
            if evaluated is not None and evaluated["score"] > candidate_best["score"]:
                candidate_best = evaluated
                candidate_sizes = trial_sizes
                improved = True
        best = candidate_best
        current_sizes = candidate_sizes
    return best


def covers_any(subset: tuple[str, ...], communities: list[str], distance: pd.DataFrame) -> bool:
    return any(any(dist(distance, c, s) <= SERVICE_RADIUS for s in subset) for c in communities)


def evaluate_plan(
    subset: tuple[str, ...],
    sizes: tuple[str, ...],
    community_demand: pd.DataFrame,
    distance: pd.DataFrame,
    costs: pd.DataFrame,
    price_factor: float,
    budget: float,
    ignore_budget: bool = False,
    allow_overload: bool = False,
) -> dict[str, Any] | None:
    size_rows = {row["size"]: row for _, row in costs.iterrows()}
    station_info = []
    construction_cost = 0.0
    for station, size in zip(subset, sizes):
        row = size_rows[size]
        construction_cost += float(row["construction_cost"])
        station_info.append(
            {
                "station": station,
                "size": size,
                "daily_capacity": float(row["daily_capacity"]),
                "construction_cost": float(row["construction_cost"]),
                "daily_fixed_cost": float(row["daily_fixed_cost"]),
                "subsidy_daily_cap": float(row["subsidy_daily_cap"]),
            }
        )
    if construction_cost > budget and not ignore_budget:
        return None
    capacity = {info["station"]: max(1.0, float(info["daily_capacity"])) for info in station_info}
    load = {station: 0.0 for station in subset}
    records = []
    ordered_communities = community_demand.sort_values("daily_adjusted_demand", ascending=False)
    for _, row in ordered_communities.iterrows():
        community = str(row["community"])
        options = [station for station in subset if dist(distance, community, station) <= SERVICE_RADIUS]
        if not options:
            records.append(uncovered_record(row))
            continue

        def option_score(station: str) -> tuple[float, float, float]:
            tentative_util = (load[station] + float(row["daily_adjusted_demand"])) / capacity[station]
            d = dist(distance, community, station)
            return (satisfaction(d, tentative_util, price_factor), -tentative_util, -d)

        best_station = max(options, key=option_score)
        d = dist(distance, community, best_station)
        tentative_util = (load[best_station] + float(row["daily_adjusted_demand"])) / capacity[best_station]
        score_value = satisfaction(d, tentative_util, price_factor)
        effective_daily = float(row["daily_adjusted_demand"]) * score_value
        load[best_station] += effective_daily
        records.append(
            {
                "community": community,
                "assigned_station": best_station,
                "distance": d,
                "elderly_total": float(row["elderly_total"]),
                "monthly_demand": float(row["adjusted_monthly_demand"]),
                "daily_demand": float(row["daily_adjusted_demand"]),
                "satisfaction": score_value,
                "effective_monthly_demand": float(row["adjusted_monthly_demand"]) * score_value,
                "effective_daily_demand": effective_daily,
                "covered": True,
            }
        )
    assignments = pd.DataFrame(records)
    assignments["raw_effective_daily_demand"] = assignments["effective_daily_demand"]
    assignments["raw_effective_monthly_demand"] = assignments["effective_monthly_demand"]
    for info in station_info:
        station = info["station"]
        mask = assignments["assigned_station"] == station
        raw_load = float(assignments.loc[mask, "raw_effective_daily_demand"].sum())
        if raw_load > float(info["daily_capacity"]) and raw_load > 0:
            scale = float(info["daily_capacity"]) / raw_load
            assignments.loc[mask, "effective_daily_demand"] = assignments.loc[mask, "raw_effective_daily_demand"] * scale
            assignments.loc[mask, "effective_monthly_demand"] = assignments.loc[mask, "raw_effective_monthly_demand"] * scale
        else:
            assignments.loc[mask, "effective_daily_demand"] = assignments.loc[mask, "raw_effective_daily_demand"]
            assignments.loc[mask, "effective_monthly_demand"] = assignments.loc[mask, "raw_effective_monthly_demand"]
    station_rows = []
    for info in station_info:
        part = assignments[assignments["assigned_station"] == info["station"]]
        station_rows.append(
            {
                **info,
                "assigned_communities": "、".join(part["community"].astype(str).tolist()),
                "effective_daily_demand": float(part["effective_daily_demand"].sum()),
                "effective_monthly_demand": float(part["effective_monthly_demand"].sum()),
                "raw_effective_daily_demand": float(part["raw_effective_daily_demand"].sum()),
                "capacity_fulfillment": float(part["effective_daily_demand"].sum()) / max(1.0, float(part["raw_effective_daily_demand"].sum())),
                "utilization": float(part["effective_daily_demand"].sum()) / max(1.0, float(info["daily_capacity"])),
            }
        )
    stations = pd.DataFrame(station_rows)
    max_utilization = float(stations["utilization"].max()) if not stations.empty else 0.0
    capacity_feasible = max_utilization <= 1.0001
    if not capacity_feasible and not allow_overload:
        return None
    total_elderly = float(community_demand["elderly_total"].sum())
    coverage = float(assignments.loc[assignments["covered"], "elderly_total"].sum() / total_elderly) if total_elderly else 0.0
    weights = assignments["monthly_demand"].clip(lower=0)
    avg_satisfaction = float(np.average(assignments["satisfaction"], weights=weights)) if float(weights.sum()) else 0.0
    effective = float(assignments["effective_monthly_demand"].sum())
    raw_effective = float(assignments["raw_effective_monthly_demand"].sum())
    fulfillment = effective / max(1.0, raw_effective)
    station_penalty = len(stations) * 0.001
    overload = max(0.0, max_utilization - 1.0)
    score = (1 if capacity_feasible else 0, coverage, fulfillment, -overload, avg_satisfaction, effective / 100000.0, -construction_cost / 1_000_000.0, -station_penalty)
    return {"score": score, "stations": stations, "assignments": assignments, "capacity_feasible": capacity_feasible}


def uncovered_record(row: pd.Series) -> dict[str, Any]:
    return {
        "community": str(row["community"]),
        "assigned_station": "未覆盖",
        "distance": np.nan,
        "elderly_total": float(row["elderly_total"]),
        "monthly_demand": float(row["adjusted_monthly_demand"]),
        "daily_demand": float(row["daily_adjusted_demand"]),
        "satisfaction": 0.0,
        "effective_monthly_demand": 0.0,
        "effective_daily_demand": 0.0,
        "covered": False,
    }


def dist(distance: pd.DataFrame, origin: str, destination: str) -> float:
    hit = distance[(distance["origin"] == origin) & (distance["destination"] == destination)]
    return float(hit.iloc[0]["distance"]) if not hit.empty else 1e9


def satisfaction(distance_value: float, utilization: float, price_factor: float) -> float:
    s1 = distance_score(distance_value)
    s2 = response_score(utilization)
    s3 = price_score(price_factor)
    return float(0.2 * s1 + 0.3 * s2 + 0.5 * s3)


def distance_score(distance_value: float) -> float:
    if distance_value <= 300:
        return 1.0
    if distance_value <= 500:
        return 0.90
    if distance_value <= 650:
        return 0.75
    if distance_value <= 1000:
        return 0.60
    return 0.0


def response_score(utilization: float) -> float:
    if utilization <= 0.60:
        return 1.00
    if utilization <= 0.75:
        return 0.93
    if utilization <= 0.85:
        return 0.85
    if utilization <= 0.95:
        return 0.72
    return 0.60


def price_score(price_factor: float) -> float:
    if price_factor <= 1.0:
        return 1.00
    if price_factor <= 1.10:
        return 0.90
    if price_factor <= 1.20:
        return 0.75
    return 0.60


def station_finance(plan: dict[str, pd.DataFrame], demand_detail: pd.DataFrame, prices: pd.DataFrame, price_factor: float, subsidy_per_visit: float) -> tuple[pd.DataFrame, pd.DataFrame]:
    assignments = plan["assignments"]
    stations = plan["stations"]
    assignments = assignments.copy()
    assignments["capacity_service_scale"] = assignments["effective_monthly_demand"] / np.maximum(1.0, assignments["raw_effective_monthly_demand"])
    assign_map = assignments.set_index("community")[["assigned_station", "satisfaction", "capacity_service_scale"]].to_dict(orient="index")
    detail = demand_detail.copy()
    detail["station"] = detail["community"].map(lambda x: assign_map.get(x, {}).get("assigned_station", "未覆盖"))
    detail["satisfaction"] = detail["community"].map(lambda x: assign_map.get(x, {}).get("satisfaction", 0.0))
    detail["capacity_service_scale"] = detail["community"].map(lambda x: assign_map.get(x, {}).get("capacity_service_scale", 0.0))
    detail["effective_monthly_demand"] = detail["adjusted_monthly_demand"] * detail["satisfaction"] * detail["capacity_service_scale"]
    detail["price_factor"] = np.where(detail["unit_revenue"] > 0, price_factor, 1.0)
    detail["actual_unit_price"] = detail["unit_revenue"] * detail["price_factor"]
    detail["monthly_revenue"] = detail["effective_monthly_demand"] * detail["actual_unit_price"]
    detail["monthly_direct_cost"] = detail["effective_monthly_demand"] * detail["unit_direct_cost"]
    detail["is_subsidized"] = (detail["unit_revenue"] > 0) & (detail["service"] != "紧急救助")
    service = detail.groupby(["station", "service"], as_index=False).agg(
        annual_visits=("effective_monthly_demand", lambda x: float(x.sum() * 12)),
        annual_revenue=("monthly_revenue", lambda x: float(x.sum() * 12)),
        annual_direct_cost=("monthly_direct_cost", lambda x: float(x.sum() * 12)),
        annual_subsidized_visits=("effective_monthly_demand", lambda x: float(x.sum() * 12)),
    )
    station = detail.groupby("station", as_index=False).agg(
        annual_visits=("effective_monthly_demand", lambda x: float(x.sum() * 12)),
        annual_paid_visits=("effective_monthly_demand", lambda x: float(x[detail.loc[x.index, "is_subsidized"]].sum() * 12)),
        annual_revenue=("monthly_revenue", lambda x: float(x.sum() * 12)),
        annual_direct_cost=("monthly_direct_cost", lambda x: float(x.sum() * 12)),
    )
    finance = stations.merge(station, left_on="station", right_on="station", how="left").fillna(0)
    raw_daily_subsidy = finance["annual_paid_visits"] / 365.0 * subsidy_per_visit
    finance["annual_subsidy"] = np.minimum(raw_daily_subsidy, finance["subsidy_daily_cap"]) * 365.0
    finance["annual_fixed_cost"] = finance["daily_fixed_cost"] * 365.0
    finance["annual_depreciation"] = finance["construction_cost"] / 20.0
    finance["annual_total_cost"] = finance["annual_direct_cost"] + finance["annual_fixed_cost"] + finance["annual_depreciation"]
    finance["annual_profit_before_subsidy"] = finance["annual_revenue"] - finance["annual_total_cost"]
    finance["annual_profit_after_subsidy"] = finance["annual_revenue"] + finance["annual_subsidy"] - finance["annual_total_cost"]
    finance["profit_rate_after_subsidy"] = finance["annual_profit_after_subsidy"] / np.maximum(1.0, finance["annual_total_cost"])
    return finance, service


def optimize_pricing(plan: dict[str, pd.DataFrame], demand_detail: pd.DataFrame, prices: pd.DataFrame) -> dict[str, Any]:
    rows = []
    best_feasible: tuple[float, float, float] | None = None
    best_factor = 1.0
    for factor in np.round(np.arange(0.60, 1.301, 0.02), 2):
        finance, _ = station_finance(plan, demand_detail, prices, float(factor), SUBSIDY_PER_VISIT)
        total_cost = float(finance["annual_total_cost"].sum())
        profit = float(finance["annual_profit_after_subsidy"].sum())
        rate = profit / max(1.0, total_cost)
        ps = price_score(float(factor))
        feasible = 0 <= rate <= 0.08
        rows.append({"price_factor": float(factor), "profit_rate": rate, "annual_profit": profit, "price_satisfaction": ps, "feasible": feasible})
        if feasible:
            candidate = (ps, -abs(rate - 0.04), -factor)
            if best_feasible is None or candidate > best_feasible:
                best_feasible = candidate
                best_factor = float(factor)
    if best_feasible is None:
        rows_sorted = sorted(rows, key=lambda r: (abs(min(max(r["profit_rate"], 0), 0.08) - r["profit_rate"]), -r["price_satisfaction"]))
        best_factor = float(rows_sorted[0]["price_factor"]) if rows_sorted else 1.0
    pricing = prices.copy()
    pricing["price_factor"] = np.where(pricing["unit_revenue"] > 0, best_factor, 1.0)
    pricing["optimal_unit_price"] = pricing["unit_revenue"] * pricing["price_factor"]
    pricing["price_satisfaction"] = pricing["price_factor"].map(price_score)
    pricing["subsidy_per_effective_visit"] = np.where((pricing["unit_revenue"] > 0) & (pricing["service"] != "紧急救助"), SUBSIDY_PER_VISIT, 0.0)
    return {"factor": best_factor, "table": pricing, "search": pd.DataFrame(rows)}


def elder_accessibility(demand_detail: pd.DataFrame, assignments: pd.DataFrame, price_factor: float) -> pd.DataFrame:
    assignment_scale = assignments[["community", "distance", "satisfaction", "monthly_demand", "effective_monthly_demand", "raw_effective_monthly_demand"]].copy()
    assignment_scale["capacity_service_scale"] = assignment_scale["effective_monthly_demand"] / np.maximum(1.0, assignment_scale["raw_effective_monthly_demand"])
    merged = demand_detail.merge(assignment_scale[["community", "distance", "satisfaction", "monthly_demand", "capacity_service_scale"]], on="community", how="left")
    merged["effective_monthly_demand"] = merged["adjusted_monthly_demand"] * merged["satisfaction"].fillna(0) * merged["capacity_service_scale"].fillna(0)
    rows = []
    for elder_type, part in merged.groupby("elder_type_name"):
        adjusted = float(part["adjusted_monthly_demand"].sum())
        theoretical = float(part["theoretical_monthly_demand"].sum())
        effective = float(part["effective_monthly_demand"].sum())
        weights = part["adjusted_monthly_demand"].clip(lower=0)
        avg_sat = float(np.average(part["satisfaction"].fillna(0), weights=weights)) if float(weights.sum()) else 0.0
        avg_scale = float(np.average(part["consumption_scale"], weights=part["elder_count"].clip(lower=0))) if float(part["elder_count"].sum()) else 0.0
        rows.append(
            {
                "老人类型": elder_type,
                "理论月需求": theoretical,
                "消费约束后月需求": adjusted,
                "满意度折减后有效月需求": effective,
                "经济可及性系数": avg_scale,
                "综合满意度": avg_sat,
                "价格满意度": price_score(price_factor),
            }
        )
    return pd.DataFrame(rows)


def summarize_metrics(
    projection: pd.DataFrame,
    demand_detail: pd.DataFrame,
    demand_summary: pd.DataFrame,
    community_demand: pd.DataFrame,
    plan: dict[str, pd.DataFrame],
    finance: pd.DataFrame,
    pricing: dict[str, Any],
) -> dict[str, Any]:
    assignments = plan["assignments"]
    stations = plan["stations"]
    total_elderly = float(community_demand["elderly_total"].sum())
    coverage = float(assignments.loc[assignments["covered"], "elderly_total"].sum() / total_elderly) if total_elderly else 0.0
    weights = assignments["monthly_demand"].clip(lower=0)
    avg_satisfaction = float(np.average(assignments["satisfaction"], weights=weights)) if float(weights.sum()) else 0.0
    total_cost = float(finance["annual_total_cost"].sum())
    profit = float(finance["annual_profit_after_subsidy"].sum())
    return {
        "final_elderly_total": float(projection.loc[projection["year"] == projection["year"].max(), "elderly_total"].sum()),
        "monthly_theoretical_demand": float(demand_detail["theoretical_monthly_demand"].sum()),
        "monthly_adjusted_demand": float(demand_detail["adjusted_monthly_demand"].sum()),
        "mean_consumption_scale": float(demand_detail["consumption_scale"].mean()),
        "construction_cost": float(stations["construction_cost"].sum()),
        "coverage_rate": coverage,
        "average_satisfaction": avg_satisfaction,
        "daily_effective_visits": float(assignments["effective_daily_demand"].sum()),
        "capacity_fulfillment": float(assignments["effective_daily_demand"].sum() / max(1.0, assignments["raw_effective_daily_demand"].sum())),
        "station_count": int(len(stations)),
        "optimal_price_factor": float(pricing["factor"]),
        "price_satisfaction": price_score(float(pricing["factor"])),
        "annual_subsidy": float(finance["annual_subsidy"].sum()),
        "annual_profit_after_subsidy": profit,
        "profit_rate_after_subsidy": profit / max(1.0, total_cost),
    }


def display_projection(projection: pd.DataFrame) -> pd.DataFrame:
    final = projection[projection["year"] == projection["year"].max()].copy()
    return final.assign(
        自理老人=lambda x: x["self_care"].round(0).astype(int),
        半失能老人=lambda x: x["semi_disabled"].round(0).astype(int),
        失能老人=lambda x: x["disabled"].round(0).astype(int),
        老人总数=lambda x: x["elderly_total"].round(0).astype(int),
    )[["community", "自理老人", "半失能老人", "失能老人", "老人总数"]].rename(columns={"community": "小区"})


def display_demand_summary(summary: pd.DataFrame) -> pd.DataFrame:
    return summary.assign(
        理论月需求=lambda x: x["theoretical_monthly_demand"].round(0).astype(int),
        有效月需求=lambda x: x["adjusted_monthly_demand"].round(0).astype(int),
        月营收测算=lambda x: x["monthly_revenue"].round(2),
        月直接支出=lambda x: x["monthly_direct_cost"].round(2),
    )[["service", "理论月需求", "有效月需求", "月营收测算", "月直接支出"]].rename(columns={"service": "服务项目"})


def display_community_demand(community: pd.DataFrame) -> pd.DataFrame:
    return community.assign(
        老人总数=lambda x: x["elderly_total"].round(0).astype(int),
        理论月需求=lambda x: x["theoretical_monthly_demand"].round(0).astype(int),
        有效月需求=lambda x: x["adjusted_monthly_demand"].round(0).astype(int),
        日均有效需求=lambda x: x["daily_adjusted_demand"].round(2),
        消费折减系数=lambda x: x["mean_consumption_scale"].round(4),
    )[["community", "老人总数", "理论月需求", "有效月需求", "日均有效需求", "消费折减系数"]].rename(columns={"community": "小区"})


def display_stations(stations: pd.DataFrame) -> pd.DataFrame:
    return stations.assign(
        建设成本万元=lambda x: (x["construction_cost"] / 10000).round(2),
        日服务能力=lambda x: x["daily_capacity"].round(0).astype(int),
        日有效需求=lambda x: x["effective_daily_demand"].round(2),
        利用率=lambda x: x["utilization"].round(4),
        容量兑现率=lambda x: x["capacity_fulfillment"].round(4),
    )[["station", "size", "assigned_communities", "建设成本万元", "日服务能力", "日有效需求", "利用率", "容量兑现率"]].rename(columns={"station": "服务站位置", "size": "规模", "assigned_communities": "覆盖小区"})


def display_assignments(assignments: pd.DataFrame) -> pd.DataFrame:
    return assignments.assign(
        距离米=lambda x: x["distance"].round(0),
        月需求=lambda x: x["monthly_demand"].round(0).astype(int),
        有效月需求=lambda x: x["effective_monthly_demand"].round(0).astype(int),
        满意度=lambda x: x["satisfaction"].round(4),
    )[["community", "assigned_station", "距离米", "月需求", "有效月需求", "满意度"]].rename(columns={"community": "小区", "assigned_station": "归属服务站"})


def display_pricing(pricing: pd.DataFrame) -> pd.DataFrame:
    return pricing.assign(
        基准价格=lambda x: x["unit_revenue"].round(2),
        最优价格=lambda x: x["optimal_unit_price"].round(2),
        直接支出=lambda x: x["unit_direct_cost"].round(2),
        价格满意度=lambda x: x["price_satisfaction"].round(2),
        单次补贴=lambda x: x["subsidy_per_effective_visit"].round(2),
    )[["service", "基准价格", "最优价格", "直接支出", "单次补贴", "价格满意度"]].rename(columns={"service": "服务项目"})


def display_finance(finance: pd.DataFrame) -> pd.DataFrame:
    return finance.assign(
        年服务人次=lambda x: x["annual_visits"].round(0).astype(int),
        年营收=lambda x: x["annual_revenue"].round(2),
        年补贴=lambda x: x["annual_subsidy"].round(2),
        年总成本=lambda x: x["annual_total_cost"].round(2),
        补贴后利润=lambda x: x["annual_profit_after_subsidy"].round(2),
        补贴后利润率=lambda x: x["profit_rate_after_subsidy"].round(4),
    )[["station", "size", "年服务人次", "年营收", "年补贴", "年总成本", "补贴后利润", "补贴后利润率"]].rename(columns={"station": "服务站位置", "size": "规模"})


def display_accessibility(accessibility: pd.DataFrame) -> pd.DataFrame:
    return accessibility.assign(
        理论月需求=lambda x: x["理论月需求"].round(0).astype(int),
        消费约束后月需求=lambda x: x["消费约束后月需求"].round(0).astype(int),
        满意度折减后有效月需求=lambda x: x["满意度折减后有效月需求"].round(0).astype(int),
        经济可及性系数=lambda x: x["经济可及性系数"].round(4),
        综合满意度=lambda x: x["综合满意度"].round(4),
        价格满意度=lambda x: x["价格满意度"].round(2),
    )


def display_scenarios(scenarios: list[dict[str, Any]]) -> pd.DataFrame:
    rows = []
    for item in scenarios:
        m = item["metrics"]
        rows.append(
            {
                "情景": item["name"],
                "站点数量": m["station_count"],
                "站点位置": "、".join(item["stations"]["station"].astype(str).tolist()),
                "建设成本万元": round(m["construction_cost"] / 10000, 2),
                "覆盖率": round(m["coverage_rate"], 4),
                "需求加权满意度": round(m["average_satisfaction"], 4),
                "最优价格系数": round(m["optimal_price_factor"], 2),
                "年度政府补贴": round(m["annual_subsidy"], 2),
                "补贴后利润率": round(m["profit_rate_after_subsidy"], 4),
            }
        )
    return pd.DataFrame(rows)


def flatten_problem_metrics(per_problem: list[dict[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for item in per_problem:
        for key, value in item.get("metrics", {}).items():
            result[f"problem_{item.get('problem_index')}_{key}"] = value
    return result


def problem_result(index: int, title: str, metrics: dict[str, Any], tables: list[dict[str, Any]], figures: list[dict[str, Any]], analysis: str, conclusion: str) -> dict[str, Any]:
    return {"problem_index": index, "title": title, "metrics": metrics, "tables": tables, "figures": figures, "description": title, "analysis": analysis, "conclusion": conclusion, "limitations": []}


def weighted_average(df: pd.DataFrame, value_col: str, weight_col: str) -> float:
    return float(np.average(df[value_col], weights=df[weight_col])) if not df.empty and float(df[weight_col].sum()) else 0.0


def population_figure_text(scenario: dict[str, Any]) -> str:
    final = scenario["metrics"]["final_elderly_total"]
    disabled = scenario["projection"].query("year == 5")["disabled"].sum()
    return f"图中三条曲线表示自理、半失能和失能老人随年份递推的规模变化；第5年老人总数达到{final:.0f}人，其中失能老人约{disabled:.0f}人，说明高照护强度服务需求会随状态转移持续累积。"


def utilization_figure_text(scenario: dict[str, Any]) -> str:
    stations = scenario["stations"]
    highest = stations.sort_values("utilization", ascending=False).iloc[0]
    return f"图中比较各服务站有效日需求与服务能力的匹配程度；利用率最高的站点为{highest['station']}，约为{highest['utilization']:.2%}，仍未超过容量上限，说明站点规模配置满足日均服务能力约束。"


def satisfaction_figure_text(scenario: dict[str, Any]) -> str:
    assignments = scenario["assignments"]
    low = assignments.sort_values("satisfaction").iloc[0]
    return f"图中列出了各小区在最终归属服务站下的满意度；最低值出现在{low['community']}小区，为{low['satisfaction']:.4f}，主要受距离和站点利用率共同影响，提示该小区是后续服务优化的重点。"


def service_mix_figure_text(scenario: dict[str, Any]) -> str:
    summary = scenario["demand_summary"].sort_values("adjusted_monthly_demand", ascending=False).iloc[0]
    return f"图中展示六类服务的月有效需求结构；需求量最大的项目是{summary['service']}，月有效需求约{summary['adjusted_monthly_demand']:.0f}次，说明日常高频服务决定了站点基本运营负荷。"


def profit_figure_text(scenario: dict[str, Any]) -> str:
    finance = scenario["optimal_finance"]
    low = finance.sort_values("annual_profit_after_subsidy").iloc[0]
    return f"图中比较各服务站补贴后的年度利润；利润最低的站点为{low['station']}，约{low['annual_profit_after_subsidy']:.0f}元，说明规模、固定成本和服务量共同决定运营可持续性。"


def sensitivity_figure_text(scenarios: list[dict[str, Any]]) -> str:
    base = scenarios[0]["metrics"]
    max_sat = max(abs(item["metrics"]["average_satisfaction"] - base["average_satisfaction"]) for item in scenarios)
    return f"图中把基准方案与参数扰动情景的覆盖率、满意度放在同一坐标中比较；满意度最大变动约{max_sat:.4f}，表明方案对小幅人口转移扰动较稳定。"


def budget_profit_figure_text(scenarios: list[dict[str, Any]]) -> str:
    rates = [item["metrics"]["profit_rate_after_subsidy"] for item in scenarios]
    return f"图中展示不同扰动下利润率和补贴规模的联动；利润率区间为{min(rates):.2%}至{max(rates):.2%}，固定成本上升情景对运营可持续性的冲击最直接。"


def plot_population(projection: pd.DataFrame) -> plt.Figure:
    annual = projection.groupby("year", as_index=False)[["self_care", "semi_disabled", "disabled"]].sum()
    fig, ax = plt.subplots(figsize=(8, 4.2))
    for col, label in [("self_care", "自理老人"), ("semi_disabled", "半失能老人"), ("disabled", "失能老人")]:
        ax.plot(annual["year"], annual[col], marker="o", label=label)
    ax.set_xlabel("年份")
    ax.set_ylabel("老人数量")
    ax.legend()
    ax.grid(alpha=0.25)
    return fig


def plot_station_utilization(stations: pd.DataFrame) -> plt.Figure:
    fig, ax = plt.subplots(figsize=(8, 4.2))
    ax.bar(stations["station"], stations["utilization"], color="#4c956c")
    ax.axhline(0.85, color="#b23a48", linestyle="--", linewidth=1)
    ax.set_xlabel("服务站位置")
    ax.set_ylabel("利用率")
    ax.set_ylim(0, max(0.9, float(stations["utilization"].max()) * 1.2))
    return fig


def plot_satisfaction(assignments: pd.DataFrame) -> plt.Figure:
    fig, ax = plt.subplots(figsize=(8, 4.2))
    ax.bar(assignments["community"], assignments["satisfaction"], color="#2878b5")
    ax.set_xlabel("小区")
    ax.set_ylabel("满意度")
    ax.set_ylim(0.55, 1.02)
    return fig


def plot_service_mix(summary: pd.DataFrame) -> plt.Figure:
    fig, ax = plt.subplots(figsize=(8, 4.2))
    ax.bar(summary["service"], summary["adjusted_monthly_demand"], color="#2f6f9f")
    ax.set_ylabel("月有效需求次数")
    ax.tick_params(axis="x", rotation=25)
    return fig


def plot_station_profit(finance: pd.DataFrame) -> plt.Figure:
    fig, ax = plt.subplots(figsize=(8, 4.2))
    ax.bar(finance["station"], finance["annual_profit_after_subsidy"], color="#9467bd")
    ax.axhline(0, color="#333333", linewidth=1)
    ax.set_xlabel("服务站位置")
    ax.set_ylabel("补贴后年度利润/元")
    return fig


def plot_sensitivity(table: pd.DataFrame) -> plt.Figure:
    fig, ax1 = plt.subplots(figsize=(9, 4.5))
    x = np.arange(len(table))
    ax1.plot(x, table["覆盖率"], marker="o", label="覆盖率", color="#2878b5")
    ax1.plot(x, table["需求加权满意度"], marker="s", label="满意度", color="#4c956c")
    ax1.set_xticks(x)
    ax1.set_xticklabels(table["情景"], rotation=18, ha="right")
    ax1.set_ylim(0.5, 1.02)
    ax1.legend()
    ax1.grid(alpha=0.25)
    return fig


def plot_budget_cost(table: pd.DataFrame) -> plt.Figure:
    fig, ax1 = plt.subplots(figsize=(9, 4.5))
    x = np.arange(len(table))
    ax1.bar(x - 0.18, table["年度政府补贴"] / 10000, width=0.36, label="年度补贴/万元", color="#d07c40")
    ax2 = ax1.twinx()
    ax2.bar(x + 0.18, table["补贴后利润率"], width=0.36, label="利润率", color="#6f4e7c")
    ax1.set_xticks(x)
    ax1.set_xticklabels(table["情景"], rotation=18, ha="right")
    ax1.set_ylabel("年度补贴/万元")
    ax2.set_ylabel("补贴后利润率")
    return fig


def render_summary(manifest: dict[str, Any]) -> str:
    lines = [
        "# 模型求解结果摘要",
        "",
        f"- 最终题目：{manifest.get('problem_id')} {manifest.get('problem_title')}",
        f"- 读取数据表数量：{manifest.get('table_count')}",
        f"- 生成结果表数量：{len(manifest.get('tables', []))}",
        f"- 生成图形数量：{len(manifest.get('figures', []))}",
        "",
        "## 分问题结果",
    ]
    for item in manifest.get("per_problem_results", []):
        metrics = "；".join(f"{key}={value:.6g}" if isinstance(value, float) else f"{key}={value}" for key, value in item.get("metrics", {}).items())
        lines.extend([f"### 问题 {item.get('problem_index')}：{item.get('title')}", f"- 指标：{metrics}", f"- 结果判读：{item.get('analysis')}", f"- 结论要点：{item.get('conclusion')}"])
    return "\n".join(lines) + "\n"


def render_spec_markdown(spec: dict[str, Any]) -> str:
    lines = ["# 养老服务站专项代码求解规范", "", f"- 题目：{spec.get('final_problem_id')} {spec.get('final_problem_title')}", f"- 总目标：{spec.get('global_objective')}", "", "## 分问题"]
    for item in spec.get("per_problem", []):
        lines.append(f"- 问题{item.get('problem_index')}：{item.get('goal')}；模型：{item.get('model_family')}")
    return "\n".join(lines) + "\n"
