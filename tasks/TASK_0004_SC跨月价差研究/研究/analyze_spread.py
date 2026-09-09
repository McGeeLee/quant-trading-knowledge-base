#!/usr/bin/env python3
"""Analyze a fixed adjacent-contract spread without look-ahead leakage."""

from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path

import numpy as np


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="检验市场上涨、价差、持仓量与下一交易日价差变化的关系。"
    )
    parser.add_argument("csv_file", type=Path, help="fetch_ine_daily.py 生成的配对 CSV")
    parser.add_argument(
        "--price",
        choices=("close", "settle"),
        default="close",
        help="使用收盘价或结算价，默认 close",
    )
    parser.add_argument("--z-window", type=int, default=20, help="价差 Z 分数窗口")
    parser.add_argument("--train-ratio", type=float, default=0.70, help="时序训练集比例")
    parser.add_argument("--output", type=Path, help="Markdown 输出文件；不填则打印")
    return parser.parse_args()


def number(value: str) -> float:
    if value is None or value.strip() == "":
        return math.nan
    return float(value)


def load_rows(path: Path, price_type: str) -> dict[str, np.ndarray]:
    rows: list[dict[str, str]] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows.extend(csv.DictReader(handle))
    if not rows:
        raise ValueError("CSV 没有数据")

    required = [
        "date",
        f"near_{price_type}",
        f"far_{price_type}",
        "near_open_interest",
        "far_open_interest",
        "near_volume",
        "far_volume",
    ]
    missing = [name for name in required if name not in rows[0]]
    if missing:
        raise ValueError(f"CSV 缺少字段：{', '.join(missing)}")

    rows.sort(key=lambda row: row["date"])
    return {
        "date": np.array([row["date"] for row in rows]),
        "near_price": np.array([number(row[f"near_{price_type}"]) for row in rows]),
        "far_price": np.array([number(row[f"far_{price_type}"]) for row in rows]),
        "near_oi": np.array([number(row["near_open_interest"]) for row in rows]),
        "far_oi": np.array([number(row["far_open_interest"]) for row in rows]),
        "near_volume": np.array([number(row["near_volume"]) for row in rows]),
        "far_volume": np.array([number(row["far_volume"]) for row in rows]),
    }


def rolling_zscore(values: np.ndarray, window: int) -> np.ndarray:
    result = np.full(values.shape, np.nan, dtype=float)
    for idx in range(window - 1, len(values)):
        sample = values[idx - window + 1 : idx + 1]
        if np.all(np.isfinite(sample)):
            std = float(np.std(sample, ddof=1))
            result[idx] = 0.0 if std == 0 else (values[idx] - float(np.mean(sample))) / std
    return result


def safe_log_change(values: np.ndarray) -> np.ndarray:
    result = np.full(values.shape, np.nan, dtype=float)
    valid = (values[1:] > 0) & (values[:-1] > 0)
    result[1:][valid] = np.log(values[1:][valid] / values[:-1][valid])
    return result


def correlation(left: np.ndarray, right: np.ndarray) -> float:
    valid = np.isfinite(left) & np.isfinite(right)
    if int(np.sum(valid)) < 3:
        return math.nan
    x = left[valid]
    y = right[valid]
    if float(np.std(x)) == 0 or float(np.std(y)) == 0:
        return math.nan
    return float(np.corrcoef(x, y)[0, 1])


def fmt(value: float, digits: int = 3) -> str:
    if not np.isfinite(value):
        return "NA"
    return f"{value:.{digits}f}"


def directional_stats(mask: np.ndarray, spread_move: np.ndarray) -> tuple[int, float, float, float]:
    valid = mask & np.isfinite(spread_move)
    sample = spread_move[valid]
    if len(sample) == 0:
        return 0, math.nan, math.nan, math.nan
    return (
        len(sample),
        float(np.mean(sample > 0)),
        float(np.mean(sample)),
        float(np.median(sample)),
    )


def same_day_regression(market_move: np.ndarray, spread_move: np.ndarray) -> tuple[float, float, float]:
    valid = np.isfinite(market_move) & np.isfinite(spread_move)
    x = market_move[valid]
    y = spread_move[valid]
    if len(x) < 3 or float(np.var(x)) == 0:
        return math.nan, math.nan, math.nan
    beta = float(np.cov(x, y, ddof=1)[0, 1] / np.var(x, ddof=1))
    alpha = float(np.mean(y) - beta * np.mean(x))
    return alpha, beta, correlation(x, y)


def liquidity_robustness(
    market_move: np.ndarray,
    spread_move: np.ndarray,
    far_oi: np.ndarray,
    far_volume: np.ndarray,
) -> list[tuple[str, int, int, float, float, float]]:
    """Require both the current and previous bar to pass each liquidity filter."""
    filters = [
        ("不筛选", np.ones(len(far_oi), dtype=bool)),
        ("远月持仓 ≥ 500 手", far_oi >= 500),
        ("远月持仓 ≥ 1,000 手", far_oi >= 1_000),
        ("远月成交量 ≥ 1,000 手", far_volume >= 1_000),
    ]
    output: list[tuple[str, int, int, float, float, float]] = []
    for label, liquid in filters:
        paired = liquid & np.r_[False, liquid[:-1]]
        valid = paired & np.isfinite(market_move) & np.isfinite(spread_move)
        up = valid & (market_move > 0)
        _, beta, corr = same_day_regression(market_move[valid], spread_move[valid])
        probability = float(np.mean(spread_move[up] > 0)) if int(np.sum(up)) else math.nan
        output.append((label, int(np.sum(valid)), int(np.sum(up)), probability, beta, corr))
    return output


def oi_regimes(
    near_oi_move: np.ndarray,
    far_oi_move: np.ndarray,
    next_spread_move: np.ndarray,
) -> list[tuple[str, int, float, float]]:
    regimes = [
        ("近增 / 远增", (near_oi_move > 0) & (far_oi_move > 0)),
        ("近增 / 远减", (near_oi_move > 0) & (far_oi_move <= 0)),
        ("近减 / 远增（移仓外观）", (near_oi_move <= 0) & (far_oi_move > 0)),
        ("近减 / 远减", (near_oi_move <= 0) & (far_oi_move <= 0)),
    ]
    output: list[tuple[str, int, float, float]] = []
    for label, mask in regimes:
        valid = mask & np.isfinite(next_spread_move)
        sample = next_spread_move[valid]
        if len(sample) == 0:
            output.append((label, 0, math.nan, math.nan))
        else:
            output.append(
                (label, len(sample), float(np.mean(sample > 0)), float(np.mean(sample)))
            )
    return output


def chronological_model(
    features: dict[str, np.ndarray],
    target: np.ndarray,
    train_ratio: float,
) -> dict[str, object]:
    names = list(features)
    matrix = np.column_stack([features[name] for name in names])
    valid = np.all(np.isfinite(matrix), axis=1) & np.isfinite(target)
    matrix = matrix[valid]
    target = target[valid]
    if len(target) < 60:
        return {"available": False, "n": len(target), "reason": "有效样本少于 60"}

    split = max(30, min(len(target) - 20, int(len(target) * train_ratio)))
    train_x = matrix[:split]
    test_x = matrix[split:]
    train_y = target[:split]
    test_y = target[split:]

    means = np.mean(train_x, axis=0)
    stds = np.std(train_x, axis=0, ddof=1)
    keep = stds > 1e-12
    train_x = (train_x[:, keep] - means[keep]) / stds[keep]
    test_x = (test_x[:, keep] - means[keep]) / stds[keep]
    kept_names = [name for name, kept in zip(names, keep) if kept]

    train_design = np.column_stack([np.ones(len(train_x)), train_x])
    test_design = np.column_stack([np.ones(len(test_x)), test_x])
    coefficients = np.linalg.lstsq(train_design, train_y, rcond=None)[0]
    prediction = test_design @ coefficients

    nonzero = test_y != 0
    sign_accuracy = (
        float(np.mean(np.sign(prediction[nonzero]) == np.sign(test_y[nonzero])))
        if int(np.sum(nonzero)) > 0
        else math.nan
    )
    baseline_sign = 1.0 if float(np.mean(train_y)) >= 0 else -1.0
    baseline_accuracy = (
        float(np.mean(baseline_sign == np.sign(test_y[nonzero])))
        if int(np.sum(nonzero)) > 0
        else math.nan
    )
    denominator = float(np.sum((test_y - float(np.mean(test_y))) ** 2))
    r_squared = (
        1.0 - float(np.sum((test_y - prediction) ** 2)) / denominator
        if denominator > 0
        else math.nan
    )
    coefficient_rows = sorted(
        zip(kept_names, coefficients[1:]), key=lambda item: abs(float(item[1])), reverse=True
    )
    return {
        "available": True,
        "n": len(target),
        "train_n": len(train_y),
        "test_n": len(test_y),
        "ic": correlation(prediction, test_y),
        "sign_accuracy": sign_accuracy,
        "baseline_accuracy": baseline_accuracy,
        "r_squared": r_squared,
        "coefficients": coefficient_rows,
    }


def build_report(data: dict[str, np.ndarray], price_type: str, z_window: int, train_ratio: float) -> str:
    dates = data["date"]
    near_price = data["near_price"]
    far_price = data["far_price"]
    valid_price = np.isfinite(near_price) & np.isfinite(far_price)
    if int(np.sum(valid_price)) < max(30, z_window + 3):
        raise ValueError("共同有效价格样本不足")

    spread = near_price - far_price
    market_level = (near_price + far_price) / 2.0
    market_move = np.full(spread.shape, np.nan)
    spread_move = np.full(spread.shape, np.nan)
    market_move[1:] = market_level[1:] - market_level[:-1]
    spread_move[1:] = spread[1:] - spread[:-1]

    near_oi_move = safe_log_change(data["near_oi"])
    far_oi_move = safe_log_change(data["far_oi"])
    roll_pressure = -near_oi_move + far_oi_move
    liquidity_ratio = np.log((data["near_volume"] + 1.0) / (data["far_volume"] + 1.0))
    spread_z = rolling_zscore(spread, z_window)

    next_spread_move = np.full(spread.shape, np.nan)
    next_spread_move[:-1] = spread[1:] - spread[:-1]
    features = {
        "当日市场变动": market_move,
        "当日价差动量": spread_move,
        f"价差Z分数({z_window})": spread_z,
        "移仓外观(-近OI变动+远OI变动)": roll_pressure,
        "近远月成交量对数比": liquidity_ratio,
    }

    alpha, beta, same_day_corr = same_day_regression(market_move, spread_move)
    up = directional_stats(market_move > 0, spread_move)
    down = directional_stats(market_move < 0, spread_move)
    flat = directional_stats(market_move == 0, spread_move)
    model = chronological_model(features, next_spread_move, train_ratio)

    price_label = "收盘价" if price_type == "close" else "结算价"
    latest = int(np.where(valid_price)[0][-1])
    liquid_history = valid_price & (data["far_oi"] >= 1_000)
    liquid_percentile = float(np.mean(spread[liquid_history] <= spread[latest]))
    relationship = (
        "样本内支持“价格上涨时价差同步扩大”"
        if beta > 0 and up[1] > 0.5
        else "样本内未同时满足正 Beta 与上涨日扩差概率超过 50%"
    )

    lines = [
        f"# SC2610-SC2611 日频价差研究（{price_label}）",
        "",
        "## 样本与当前截面",
        "",
        f"- 共同样本：{len(dates)} 个交易日，{dates[0]} 至 {dates[-1]}。",
        f"- 最新 {price_label}：SC2610 = {near_price[latest]:.1f}，SC2611 = {far_price[latest]:.1f}。",
        f"- 最新价差 `SC2610-SC2611` = {spread[latest]:+.1f} 元/桶。",
        f"- 在远月持仓 ≥1,000 手的本合约历史中，最新价差处于 {liquid_percentile * 100:.1f}% 分位；{z_window} 日 Z 分数 = {fmt(spread_z[latest])}。",
        f"- 1 手对 1 手组合每变动 1 元/桶，毛盈亏变动约 1,000 元；未计双腿手续费、滑点与保证金。",
        "",
        "## 同期关系：回答“上涨时是否通常扩差”",
        "",
        f"结论：**{relationship}**。这里是同一交易日的共同变动，只说明联动，不是可提前交易的预测。",
        "",
        "| 市场状态 | 样本数 | 价差扩大概率 | 平均价差变化 | 中位数价差变化 |",
        "|---|---:|---:|---:|---:|",
    ]
    for label, values in (("上涨", up), ("下跌", down), ("不变", flat)):
        lines.append(
            f"| {label} | {values[0]} | {fmt(values[1] * 100, 1)}% | {fmt(values[2])} | {fmt(values[3])} |"
        )
    lines.extend(
        [
            "",
            f"同期回归：`价差变化 = {fmt(alpha)} + {fmt(beta)} × 市场价格变化`，相关系数 = {fmt(same_day_corr)}。",
            "",
            "### 流动性筛选",
            "",
            "远月早期持仓或成交量很低，最后成交价可能陈旧。每个筛选同时要求本日和上一交易日达标：",
            "",
            "| 筛选 | 有效变动样本 | 上涨样本 | 上涨日扩差概率 | 同期 Beta | 同期相关系数 |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for label, count, up_count, probability, liquid_beta, liquid_corr in liquidity_robustness(
        market_move, spread_move, data["far_oi"], data["far_volume"]
    ):
        lines.append(
            f"| {label} | {count} | {up_count} | {fmt(probability * 100, 1)}% | {fmt(liquid_beta)} | {fmt(liquid_corr)} |"
        )
    lines.extend(
        [
            "",
            "## 滞后关系：本日信息预测下一交易日价差",
            "",
            "| 当日特征 | 与下一日价差变化的相关系数 |",
            "|---|---:|",
        ]
    )
    for name, values in features.items():
        lines.append(f"| {name} | {fmt(correlation(values, next_spread_move))} |")

    lines.extend(
        [
            "",
            "### 持仓量状态",
            "",
            "持仓量只告诉我们未平仓合约数量，不能区分新开的是多头还是空头；以下只把它当状态变量。",
            "",
            "| 当日近/远月持仓变化 | 样本数 | 下一日扩差概率 | 下一日平均价差变化 |",
            "|---|---:|---:|---:|",
        ]
    )
    for label, count, probability, average in oi_regimes(
        near_oi_move, far_oi_move, next_spread_move
    ):
        lines.append(
            f"| {label} | {count} | {fmt(probability * 100, 1)}% | {fmt(average)} |"
        )

    lines.extend(["", "### 按时间切分的样本外线性模型", ""])
    if not model["available"]:
        lines.append(f"未运行：{model['reason']}（有效样本 {model['n']}）。")
    else:
        lines.extend(
            [
                f"训练 {model['train_n']} 条、测试 {model['test_n']} 条；测试集预测值与真实值相关系数（IC）= {fmt(float(model['ic']))}。",
                f"方向命中率 = {fmt(float(model['sign_accuracy']) * 100, 1)}%，训练集多数方向基线 = {fmt(float(model['baseline_accuracy']) * 100, 1)}%，样本外 R² = {fmt(float(model['r_squared']))}。",
                "",
                "标准化系数仅用于比较样本内权重，不代表因果：",
                "",
                "| 特征 | 标准化系数 |",
                "|---|---:|",
            ]
        )
        for name, coefficient in model["coefficients"]:
            lines.append(f"| {name} | {fmt(float(coefficient))} |")

    lines.extend(
        [
            "",
            "## 研究边界",
            "",
            "1. 固定的 SC2610/SC2611 只有一个合约生命周期，无法代表所有年份；本任务已另用 2020–2026 年同到期距离的 10–11 月组合做面板复核。",
            "2. 同期关系不是预测，本报告的下一日收盘到收盘关系也不是可实现的成交收益。面板报告已另用下一交易日开盘至收盘变化测试信号时点。",
            "3. 日频收盘/结算无法模拟双腿是否同步成交；远月流动性不足时，最后成交价还可能陈旧。",
            "4. 临近交割和主力移仓会改变行为，应按距最后交易日分段，避免把移仓期与普通期混为一谈。",
            "5. 本报告是研究诊断，不构成实盘交易建议。",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    if args.z_window < 5:
        raise ValueError("z-window 至少为 5")
    if not 0.5 <= args.train_ratio <= 0.9:
        raise ValueError("train-ratio 必须在 0.5 到 0.9 之间")
    data = load_rows(args.csv_file, args.price)
    report = build_report(data, args.price, args.z_window, args.train_ratio)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report, encoding="utf-8")
        print(f"已写入报告：{args.output}")
    else:
        print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
