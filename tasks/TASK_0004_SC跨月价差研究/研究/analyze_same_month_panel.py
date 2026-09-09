#!/usr/bin/env python3
"""Analyze repeated SC October-November calendar spreads across contract years."""

from __future__ import annotations

import argparse
import csv
import math
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

import numpy as np


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="跨年份检验 SC 10月-11月价差规律。")
    parser.add_argument("csv_file", type=Path)
    parser.add_argument("--price", choices=("close", "settle"), default="settle")
    parser.add_argument("--min-far-oi", type=float, default=1000.0)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def to_float(value: str | None) -> float:
    if value is None or value.strip() == "":
        return math.nan
    return float(value)


def corr(left: np.ndarray, right: np.ndarray) -> float:
    valid = np.isfinite(left) & np.isfinite(right)
    if int(np.sum(valid)) < 3:
        return math.nan
    x = left[valid]
    y = right[valid]
    if float(np.std(x)) == 0 or float(np.std(y)) == 0:
        return math.nan
    return float(np.corrcoef(x, y)[0, 1])


def beta(left: np.ndarray, right: np.ndarray) -> float:
    valid = np.isfinite(left) & np.isfinite(right)
    x = left[valid]
    y = right[valid]
    if len(x) < 3 or float(np.var(x, ddof=1)) == 0:
        return math.nan
    return float(np.cov(x, y, ddof=1)[0, 1] / np.var(x, ddof=1))


def fmt(value: float, digits: int = 3) -> str:
    if not np.isfinite(value):
        return "NA"
    return f"{value:.{digits}f}"


def wilson_interval(successes: int, total: int, z: float = 1.95996398454) -> tuple[float, float]:
    """Return a binomial Wilson interval; it does not adjust for serial dependence."""
    if total <= 0:
        return math.nan, math.nan
    probability = successes / total
    denominator = 1.0 + z * z / total
    center = (probability + z * z / (2.0 * total)) / denominator
    half_width = (
        z
        * math.sqrt(probability * (1.0 - probability) / total + z * z / (4.0 * total * total))
        / denominator
    )
    return center - half_width, center + half_width


def rolling_std(values: np.ndarray, window: int) -> np.ndarray:
    output = np.full(len(values), np.nan)
    for idx in range(window - 1, len(values)):
        sample = values[idx - window + 1 : idx + 1]
        if np.all(np.isfinite(sample)):
            output[idx] = float(np.std(sample, ddof=1))
    return output


def load_features(path: Path, price_type: str, min_far_oi: float) -> list[dict[str, object]]:
    grouped: dict[int, list[dict[str, str]]] = defaultdict(list)
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            grouped[int(row["pair_year"])].append(row)

    output: list[dict[str, object]] = []
    for pair_year, rows in sorted(grouped.items()):
        rows.sort(key=lambda item: item["date"])
        dates = [datetime.strptime(row["date"], "%Y-%m-%d").date() for row in rows]
        near = np.array([to_float(row[f"near_{price_type}"]) for row in rows])
        far = np.array([to_float(row[f"far_{price_type}"]) for row in rows])
        near_open = np.array([to_float(row["near_open"]) for row in rows])
        far_open = np.array([to_float(row["far_open"]) for row in rows])
        near_close = np.array([to_float(row["near_close"]) for row in rows])
        far_close = np.array([to_float(row["far_close"]) for row in rows])
        near_oi = np.array([to_float(row["near_open_interest"]) for row in rows])
        far_oi = np.array([to_float(row["far_open_interest"]) for row in rows])
        spread = near - far
        market = (near + far) / 2.0
        market_move = np.r_[np.nan, np.diff(market)]
        spread_move = np.r_[np.nan, np.diff(spread)]
        next_spread_move = np.r_[np.diff(spread), np.nan]
        session_spread_change = (near_close - far_close) - (near_open - far_open)
        next_session_spread_change = np.r_[session_spread_change[1:], np.nan]
        near_oi_move = np.r_[np.nan, np.diff(np.log(np.where(near_oi > 0, near_oi, np.nan)))]
        far_oi_move = np.r_[np.nan, np.diff(np.log(np.where(far_oi > 0, far_oi, np.nan)))]
        market_volatility = rolling_std(market_move, 20)
        market_shock = market_move / market_volatility
        liquid = far_oi >= min_far_oi
        contemporaneous_liquid = liquid & np.r_[False, liquid[:-1]]
        trade_liquid = contemporaneous_liquid & np.r_[liquid[1:], False]
        expiry_anchor = date(pair_year, 9, 30)

        for idx, row_date in enumerate(dates):
            output.append(
                {
                    "pair_year": pair_year,
                    "date": row_date,
                    "days_to_expiry_proxy": (expiry_anchor - row_date).days,
                    "spread": spread[idx],
                    "market_move": market_move[idx],
                    "spread_move": spread_move[idx],
                    "next_spread_move": next_spread_move[idx],
                    "next_session_spread_change": next_session_spread_change[idx],
                    "near_oi_move": near_oi_move[idx],
                    "far_oi_move": far_oi_move[idx],
                    "market_shock": market_shock[idx],
                    "contemporaneous_liquid": bool(contemporaneous_liquid[idx]),
                    "trade_liquid": bool(trade_liquid[idx]),
                }
            )
    return output


def array(rows: list[dict[str, object]], key: str) -> np.ndarray:
    return np.array([float(row[key]) for row in rows], dtype=float)


def boolean(rows: list[dict[str, object]], key: str) -> np.ndarray:
    return np.array([bool(row[key]) for row in rows], dtype=bool)


def subset(rows: list[dict[str, object]], mask: np.ndarray) -> list[dict[str, object]]:
    return [row for row, keep in zip(rows, mask) if keep]


def state_stats(rows: list[dict[str, object]]) -> tuple[int, float, float, float]:
    target = array(rows, "next_spread_move")
    target = target[np.isfinite(target)]
    if len(target) == 0:
        return 0, math.nan, math.nan, math.nan
    return len(target), float(np.mean(target > 0)), float(np.mean(target)), float(np.median(target))


def rule_result(rows: list[dict[str, object]], positions: np.ndarray) -> dict[str, object]:
    target = array(rows, "next_session_spread_change")
    years = np.array([int(row["pair_year"]) for row in rows])
    valid = np.isfinite(target) & np.isfinite(positions) & (positions != 0) & boolean(rows, "trade_liquid")
    pnl = positions[valid] * target[valid]
    used_years = years[valid]
    if len(pnl) == 0:
        return {"n": 0, "mean": math.nan, "median": math.nan, "win": math.nan, "positive_years": 0, "years": 0}
    yearly = {
        int(year): float(np.mean(pnl[used_years == year]))
        for year in sorted(set(used_years))
    }
    return {
        "n": len(pnl),
        "mean": float(np.mean(pnl)),
        "median": float(np.median(pnl)),
        "win": float(np.mean(pnl > 0)),
        "positive_years": int(np.sum(np.array(list(yearly.values())) > 0)),
        "years": len(yearly),
        "yearly": yearly,
    }


def build_report(rows: list[dict[str, object]], price_type: str, min_far_oi: float) -> str:
    years = sorted({int(row["pair_year"]) for row in rows})
    liquid = boolean(rows, "contemporaneous_liquid")
    market_move = array(rows, "market_move")
    spread_move = array(rows, "spread_move")
    next_move = array(rows, "next_spread_move")
    spread = array(rows, "spread")
    near_oi_move = array(rows, "near_oi_move")
    far_oi_move = array(rows, "far_oi_move")
    market_shock = array(rows, "market_shock")
    trade_liquid = boolean(rows, "trade_liquid")
    price_label = "收盘价" if price_type == "close" else "结算价"

    lines = [
        f"# SC 10月-11月跨月价差跨年份检验（{price_label}）",
        "",
        "## 样本",
        "",
        f"- 可用组合年份：{years[0]}–{years[-1]}，共 {len(years)} 组；原计划的 2019 组因当前官方新地址未返回旧文件而未纳入。",
        f"- 原始配对日数：{len(rows)}；核心统计要求远月持仓至少 {min_far_oi:,.0f} 手，并要求相邻日期同时达标。",
        "- 每组使用前一年 12 月至交割年 9 月中旬；2026 组截至 9 月 8 日。",
        "",
        "## 1. “价格上涨时价差扩大”是否跨年份成立",
        "",
        "| 合约年 | 有效变动日 | 上涨日 | 上涨日扩差概率 | 下跌日扩差概率 | 同期 Beta | 同期相关 |",
        "|---:|---:|---:|---:|---:|---:|---:|",
    ]
    yearly_up_probabilities: list[float] = []
    yearly_betas: list[float] = []
    for year in years:
        mask = liquid & np.array([int(row["pair_year"]) == year for row in rows])
        valid = mask & np.isfinite(market_move) & np.isfinite(spread_move)
        up = valid & (market_move > 0)
        down = valid & (market_move < 0)
        up_probability = float(np.mean(spread_move[up] > 0)) if int(np.sum(up)) else math.nan
        down_probability = float(np.mean(spread_move[down] > 0)) if int(np.sum(down)) else math.nan
        year_beta = beta(market_move[valid], spread_move[valid])
        year_corr = corr(market_move[valid], spread_move[valid])
        if np.isfinite(up_probability):
            yearly_up_probabilities.append(up_probability)
        if np.isfinite(year_beta):
            yearly_betas.append(year_beta)
        lines.append(
            f"| {year} | {int(np.sum(valid))} | {int(np.sum(up))} | {fmt(up_probability * 100, 1)}% | {fmt(down_probability * 100, 1)}% | {fmt(year_beta)} | {fmt(year_corr)} |"
        )

    valid = liquid & np.isfinite(market_move) & np.isfinite(spread_move)
    up = valid & (market_move > 0)
    down = valid & (market_move < 0)
    pooled_up = float(np.mean(spread_move[up] > 0))
    pooled_down = float(np.mean(spread_move[down] > 0))
    up_interval = wilson_interval(int(np.sum(spread_move[up] > 0)), int(np.sum(up)))
    down_interval = wilson_interval(int(np.sum(spread_move[down] > 0)), int(np.sum(down)))
    lines.extend(
        [
            f"| **合并** | **{int(np.sum(valid))}** | **{int(np.sum(up))}** | **{pooled_up * 100:.1f}%** | **{pooled_down * 100:.1f}%** | **{beta(market_move[valid], spread_move[valid]):.3f}** | **{corr(market_move[valid], spread_move[valid]):.3f}** |",
            "",
            f"上涨日扩差概率高于 50% 的年份为 {sum(value > 0.5 for value in yearly_up_probabilities)}/{len(yearly_up_probabilities)}；同期 Beta 为正的年份为 {sum(value > 0 for value in yearly_betas)}/{len(yearly_betas)}。",
            "",
            f"若暂时把每个交易日当独立样本，合并上涨日扩差概率的 95% Wilson 区间为 {up_interval[0] * 100:.1f}%–{up_interval[1] * 100:.1f}%，下跌日为 {down_interval[0] * 100:.1f}%–{down_interval[1] * 100:.1f}%。日频有序列相关，所以该区间只用于感受估计误差，逐年一致性更重要。",
            "",
            "### 当前价差在同到期阶段的位置",
            "",
        ]
    )

    latest_year = max(years)
    latest_row = max(
        (row for row in rows if int(row["pair_year"]) == latest_year),
        key=lambda row: row["date"],
    )
    latest_dte = int(latest_row["days_to_expiry_proxy"])
    matched_rows: list[dict[str, object]] = []
    for year in years:
        candidates = [row for row in rows if int(row["pair_year"]) == year]
        matched_rows.append(
            min(
                candidates,
                key=lambda row: abs(int(row["days_to_expiry_proxy"]) - latest_dte),
            )
        )
    matched_spreads = np.array([float(row["spread"]) for row in matched_rows])
    latest_spread = float(latest_row["spread"])
    percentile = float(np.mean(matched_spreads <= latest_spread))
    lines.extend(
        [
            f"最新 {latest_year} 组样本距统一到期锚点 {latest_dte} 天，{price_label}价差为 {latest_spread:+.1f}。下表为各年最接近该到期距离的单日截面。",
            "",
            "| 合约年 | 日期 | 距到期代理 | 价差 |",
            "|---:|---|---:|---:|",
        ]
    )
    for row in matched_rows:
        lines.append(
            f"| {int(row['pair_year'])} | {row['date'].isoformat()} | {int(row['days_to_expiry_proxy'])} | {float(row['spread']):+.1f} |"
        )
    lines.extend(
        [
            "",
            f"按这 {len(matched_rows)} 个逐年截面计算，当前价差处于 {percentile * 100:.1f}% 分位（并列按小于等于计）。样本只有 {len(matched_rows)} 年，这是“历史稀有程度”，不是做空信号。",
            "",
            "## 2. 哪些状态对下一交易日有信息",
            "",
            "所有下表统计都只使用在信号日及相邻日期通过流动性条件的样本。",
            "",
            "| 当日状态 | 样本数 | 下一日扩差概率 | 下一日平均变化 | 下一日中位数变化 |",
            "|---|---:|---:|---:|---:|",
        ]
    )

    state_masks = [
        ("市场上涨", market_move > 0),
        ("市场下跌", market_move < 0),
        ("价差当日扩大", spread_move > 0),
        ("价差当日收窄", spread_move < 0),
        ("正价差（近月升水）", spread > 0),
        ("负价差（近月贴水）", spread < 0),
        ("上涨但价差未扩大", (market_move > 0) & (spread_move <= 0)),
        ("下跌但价差未收窄", (market_move < 0) & (spread_move >= 0)),
        ("近月减仓、远月增仓", (near_oi_move < 0) & (far_oi_move > 0)),
        ("近月增仓、远月减仓", (near_oi_move > 0) & (far_oi_move < 0)),
    ]
    for label, state_mask in state_masks:
        selected = subset(rows, trade_liquid & state_mask)
        count, probability, average, median = state_stats(selected)
        lines.append(
            f"| {label} | {count} | {fmt(probability * 100, 1)}% | {fmt(average)} | {fmt(median)} |"
        )

    days_to_expiry = array(rows, "days_to_expiry_proxy")
    lines.extend(
        [
            "",
            "### 到期阶段",
            "",
            "这里用交割年前 9 月 30 日作统一到期锚点，只用于跨年分层，不替代交易所实际最后交易日。",
            "",
            "| 距到期代理 | 样本数 | 下一日扩差概率 | 下一日平均变化 |",
            "|---|---:|---:|---:|",
        ]
    )
    stages = [
        (">120 天", days_to_expiry > 120),
        ("61–120 天", (days_to_expiry >= 61) & (days_to_expiry <= 120)),
        ("≤60 天", days_to_expiry <= 60),
    ]
    for label, stage_mask in stages:
        count, probability, average, _ = state_stats(subset(rows, trade_liquid & stage_mask))
        lines.append(f"| {label} | {count} | {fmt(probability * 100, 1)}% | {fmt(average)} |")

    rules = [
        ("全样本次日做多（基线）", np.ones(len(rows))),
        ("上涨后做多价差", np.where(market_move > 0, 1.0, 0.0)),
        ("下跌后做空价差", np.where(market_move < 0, -1.0, 0.0)),
        ("价差一日反转", -np.sign(spread_move)),
        ("上涨但未扩差，次日做多", np.where((market_move > 0) & (spread_move <= 0), 1.0, 0.0)),
        ("标准化上涨冲击>1，次日做多", np.where(market_shock > 1.0, 1.0, 0.0)),
        ("近减仓远增仓后做多", np.where((near_oi_move < 0) & (far_oi_move > 0), 1.0, 0.0)),
        ("近增仓远减仓后做空", np.where((near_oi_move > 0) & (far_oi_move < 0), -1.0, 0.0)),
    ]
    lines.extend(
        [
            "",
            "## 3. 可执行时点的下一交易日规则（毛价差点数）",
            "",
            "规则在本日收盘/结算后形成，下一交易日按官方日行情中两腿各自的开盘价进入，并按该交易日收盘价退出。这样不使用已经知道的本日结算价作为成交价。结果仍未扣双腿手续费、盘口滑点与腿间风险，也未证明两腿可在各自日开盘价同时成交。",
            "",
            "| 规则 | 交易日数 | 平均毛点数/次 | 中位数 | 胜率 | 正收益年份 |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    rule_results: dict[str, dict[str, object]] = {}
    for label, positions in rules:
        result = rule_result(rows, positions)
        rule_results[label] = result
        lines.append(
            f"| {label} | {result['n']} | {fmt(float(result['mean']))} | {fmt(float(result['median']))} | {fmt(float(result['win']) * 100, 1)}% | {result['positive_years']}/{result['years']} |"
        )

    lines.extend(
        [
            "",
            "### 规则逐年平均毛点数",
            "",
            "| 规则 | " + " | ".join(str(year) for year in years) + " |",
            "|---|" + "---:|" * len(years),
        ]
    )
    for label, _ in rules:
        yearly = rule_results[label].get("yearly", {})
        lines.append(
            f"| {label} | "
            + " | ".join(fmt(float(yearly.get(year, math.nan))) for year in years)
            + " |"
        )

    friction_levels = (0.2, 0.4, 0.6, 0.8)
    lines.extend(
        [
            "",
            "### 全成本压力测试",
            "",
            "下表把双腿手续费、买卖价差、滑点与腿间风险合并为每次交易的固定价差点数，仅用于查看毛优势对成本的敏感度，不代表真实成交成本。",
            "",
            "| 规则 | 毛均值 | "
            + " | ".join(f"净均值@成本{level:.1f}" for level in friction_levels)
            + " |",
            "|---|---:|" + "---:|" * len(friction_levels),
        ]
    )
    for label, _ in rules:
        average = float(rule_results[label]["mean"])
        lines.append(
            f"| {label} | {fmt(average)} | "
            + " | ".join(fmt(average - level) for level in friction_levels)
            + " |"
        )

    lines.extend(
        [
            "",
            "## 4. 可以整理出的结论",
            "",
            "1. **结构规律较稳**：油价上涨时近月通常比远月更强，这个关系应作为曲线状态判断，而不是下一日入场信号。",
            "2. **预测规律弱得多**：当天上涨、扩差或移仓外观，对下一日的方向并没有天然保证；必须按年份与到期阶段看稳定性。",
            "3. **价差的短周期反转不稳定**：结算价口径只略正，收盘价口径为负，不能把均值回归当成已证实的赚钱方法。",
            "4. **持仓的首要用途是识别流动性和换月**：它适合做过滤器与阶段变量，不适合作为单独的多空按钮。",
            "5. **当前 SC2610/2611 已进入极端近月升水阶段**：固定阈值会随波动环境失效，后续应使用历史分位数或波动标准化，而不是把 +20、+40 写死。",
            "",
            "## 研究限制",
            "",
            "- 各年份宏观冲击不同，合并结果不能替代逐年一致性。",
            "- 结算价适合研究日终结构，但不是可直接成交价；收盘价又可能受远月最后一笔陈旧影响。",
            "- 日频数据看不到双腿成交顺序、盘口深度与盘中先后关系。",
            "- 所有规则仍是探索性结果，尚未预注册参数或留出完全未查看的最终测试集。",
            "- 本报告不构成实盘交易建议。",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    rows = load_features(args.csv_file, args.price, args.min_far_oi)
    report = build_report(rows, args.price, args.min_far_oi)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(report, encoding="utf-8")
    print(f"已写入报告：{args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
