#!/usr/bin/env python3
"""Build a multi-year panel of the same adjacent SC delivery months."""

from __future__ import annotations

import argparse
import csv
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
from pathlib import Path

from fetch_ine_daily import date_range, paired_row


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="下载历年相同交割月份的 SC 相邻月组合，例如 1910-1911 至 2610-2611。"
    )
    parser.add_argument("--start-year", type=int, default=2019)
    parser.add_argument("--end-year", type=int, default=2026)
    parser.add_argument("--near-month", type=int, default=10)
    parser.add_argument("--far-month", type=int, default=11)
    parser.add_argument(
        "--window-start",
        default="12-01",
        help="每组合从前一年哪个月日开始，默认 12-01",
    )
    parser.add_argument(
        "--window-end",
        default="09-15",
        help="每组合到交割年哪个月日结束，默认 09-15",
    )
    parser.add_argument("--as-of", required=True, help="不得晚于此日期，YYYY-MM-DD")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def month_day(text: str) -> tuple[int, int]:
    parsed = datetime.strptime(text, "%m-%d")
    return parsed.month, parsed.day


def contract_code(year: int, month: int) -> str:
    return f"{year % 100:02d}{month:02d}"


def main() -> int:
    args = parse_args()
    if args.end_year < args.start_year:
        raise ValueError("end-year 不能早于 start-year")
    if not 1 <= args.workers <= 8:
        raise ValueError("workers 必须在 1 到 8 之间")
    if not 1 <= args.near_month < args.far_month <= 12:
        raise ValueError("当前脚本要求 1 <= near-month < far-month <= 12")

    as_of = datetime.strptime(args.as_of, "%Y-%m-%d").date()
    start_month, start_day = month_day(args.window_start)
    end_month, end_day = month_day(args.window_end)
    jobs: list[tuple[int, date, str, str]] = []
    for pair_year in range(args.start_year, args.end_year + 1):
        start = date(pair_year - 1, start_month, start_day)
        end = min(date(pair_year, end_month, end_day), as_of)
        if end < start:
            continue
        near = contract_code(pair_year, args.near_month)
        far = contract_code(pair_year, args.far_month)
        jobs.extend((pair_year, day, near, far) for day in date_range(start, end))

    rows: list[dict] = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        future_jobs = {
            pool.submit(
                paired_row,
                day,
                "sc",
                near,
                far,
                args.timeout,
                args.retries,
            ): (pair_year, day)
            for pair_year, day, near, far in jobs
        }
        for future in as_completed(future_jobs):
            pair_year, _ = future_jobs[future]
            row = future.result()
            if row is not None:
                row = {"pair_year": pair_year, **row}
                rows.append(row)

    rows.sort(key=lambda row: (int(row["pair_year"]), str(row["date"])))
    if not rows:
        raise RuntimeError("没有取得任何配对数据")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    counts: dict[int, int] = {}
    for row in rows:
        year = int(row["pair_year"])
        counts[year] = counts.get(year, 0) + 1
    summary = ", ".join(f"{year}:{count}" for year, count in sorted(counts.items()))
    print(f"已写入 {len(rows)} 行，分组合样本数 {summary} -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
