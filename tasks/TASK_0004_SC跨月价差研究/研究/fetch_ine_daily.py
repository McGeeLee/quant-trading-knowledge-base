#!/usr/bin/env python3
"""Download paired INE daily futures data from the exchange's public endpoint."""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


BASE_URL = "https://www.ine.cn/data/tradedata/future/dailydata/kx{date}.dat"
USER_AGENT = "Mozilla/5.0 (compatible; QMT-research/1.0)"
PRICE_FIELDS = {
    "open": "OPENPRICE",
    "high": "HIGHESTPRICE",
    "low": "LOWESTPRICE",
    "close": "CLOSEPRICE",
    "settle": "SETTLEMENTPRICE",
    "pre_settle": "PRESETTLEMENTPRICE",
    "volume": "VOLUME",
    "open_interest": "OPENINTEREST",
    "oi_change": "OPENINTERESTCHG",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="下载并配对上期能源两份期货合约的官方日行情。"
    )
    parser.add_argument("--start", required=True, help="开始日期，YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="结束日期，YYYY-MM-DD")
    parser.add_argument("--product", default="sc", help="品种代码，默认 sc")
    parser.add_argument("--near", default="2610", help="近月交割月份，默认 2610")
    parser.add_argument("--far", default="2611", help="远月交割月份，默认 2611")
    parser.add_argument("--workers", type=int, default=4, help="并发数，默认 4")
    parser.add_argument("--timeout", type=float, default=15.0, help="单次超时秒数")
    parser.add_argument("--retries", type=int, default=2, help="失败重试次数")
    parser.add_argument("--output", required=True, type=Path, help="输出 CSV")
    return parser.parse_args()


def date_range(start: date, end: date) -> list[date]:
    if end < start:
        raise ValueError("结束日期不能早于开始日期")
    result: list[date] = []
    current = start
    while current <= end:
        if current.weekday() < 5:
            result.append(current)
        current += timedelta(days=1)
    return result


def clean_number(value: object) -> float | int | None:
    if value is None or str(value).strip() in ("", "-", "--"):
        return None
    number = float(str(value).strip())
    if number.is_integer():
        return int(number)
    return number


def download_json(day: date, timeout: float, retries: int) -> dict | None:
    date_text = day.strftime("%Y%m%d")
    url = BASE_URL.format(date=date_text)
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    for attempt in range(retries + 1):
        try:
            with urlopen(request, timeout=timeout) as response:
                payload = response.read()
            data = json.loads(payload.decode("utf-8"))
            success_code = str(data.get("o_code", "")).strip()
            if success_code in ("0", "0000") and str(data.get("report_date")) == date_text:
                return data
            return None
        except HTTPError as exc:
            if exc.code == 404:
                return None
            last_error: Exception = exc
        except (URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = exc
        if attempt < retries:
            time.sleep(0.5 * (attempt + 1))
    print(f"警告：{date_text} 下载失败：{last_error}", file=sys.stderr)
    return None


def contract_row(data: dict, product: str, delivery_month: str) -> dict | None:
    for item in data.get("o_curinstrument", []):
        if (
            str(item.get("PRODUCTGROUPID", "")).strip().lower() == product.lower()
            and str(item.get("DELIVERYMONTH", "")).strip() == delivery_month
        ):
            return item
    return None


def paired_row(
    day: date,
    product: str,
    near: str,
    far: str,
    timeout: float,
    retries: int,
) -> dict | None:
    data = download_json(day, timeout, retries)
    if data is None:
        return None
    near_row = contract_row(data, product, near)
    far_row = contract_row(data, product, far)
    if near_row is None or far_row is None:
        return None

    result: dict[str, object] = {
        "date": day.isoformat(),
        "near_symbol": f"{product.lower()}{near}",
        "far_symbol": f"{product.lower()}{far}",
        "source_update": data.get("update_date", ""),
    }
    for output_name, source_name in PRICE_FIELDS.items():
        result[f"near_{output_name}"] = clean_number(near_row.get(source_name))
        result[f"far_{output_name}"] = clean_number(far_row.get(source_name))

    near_close = result["near_close"]
    far_close = result["far_close"]
    near_settle = result["near_settle"]
    far_settle = result["far_settle"]
    result["close_spread"] = (
        float(near_close) - float(far_close)
        if near_close is not None and far_close is not None
        else None
    )
    result["settle_spread"] = (
        float(near_settle) - float(far_settle)
        if near_settle is not None and far_settle is not None
        else None
    )
    return result


def main() -> int:
    args = parse_args()
    start = datetime.strptime(args.start, "%Y-%m-%d").date()
    end = datetime.strptime(args.end, "%Y-%m-%d").date()
    days = date_range(start, end)
    if not 1 <= args.workers <= 8:
        raise ValueError("workers 必须在 1 到 8 之间")

    rows: list[dict] = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {
            pool.submit(
                paired_row,
                day,
                args.product,
                args.near,
                args.far,
                args.timeout,
                args.retries,
            ): day
            for day in days
        }
        for future in as_completed(futures):
            row = future.result()
            if row is not None:
                rows.append(row)

    rows.sort(key=lambda row: str(row["date"]))
    if not rows:
        print("没有取得同时包含两份合约的数据", file=sys.stderr)
        return 1

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    print(
        f"已写入 {len(rows)} 个共同交易日：{rows[0]['date']} 至 {rows[-1]['date']} -> {args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
