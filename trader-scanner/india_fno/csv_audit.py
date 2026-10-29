#!/usr/bin/env python3
"""Offline integrity audit for imported India F&O OHLC candle CSVs.

No network access, credentials, broker connection, or order placement.
This checks structural data quality; it cannot certify that a source is
licensed, complete, exchange-authoritative, or suitable for execution.
"""
import argparse
import csv
import datetime as dt
import json
import math
import re
import sys
from collections import defaultdict


ALIASES = {
    "timestamp": ("timestamp", "datetime", "dateandtime", "time", "date"),
    "symbol": ("symbol", "tradingsymbol", "instrument", "contract", "ticker"),
    "exchange": ("exchange", "exch", "segment"),
    "interval": ("interval", "timeframe", "period"),
    "open": ("open", "o"),
    "high": ("high", "h"),
    "low": ("low", "l"),
    "close": ("close", "c"),
    "volume": ("volume", "vol", "v"),
}


def _norm(value):
    return re.sub(r"[ _-]", "", (value or "").strip().lower())


def _number(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _interval_minutes(value):
    match = re.fullmatch(
        r"\s*(\d+)\s*(m|min|mins|minute|minutes|h|hr|hour|hours|d|day|days)\s*",
        str(value or "5m").lower(),
    )
    if not match or int(match.group(1)) <= 0:
        return None
    amount, unit = int(match.group(1)), match.group(2)
    if unit in ("h", "hr", "hour", "hours"):
        return amount * 60
    if unit in ("d", "day", "days"):
        return amount * 1440
    return amount


def _parse_timestamp(value):
    try:
        parsed = dt.datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
        return parsed, parsed.tzinfo is None or parsed.utcoffset() is None
    except (TypeError, ValueError, OverflowError):
        return None, False


def audit_rows(rows, min_bars=100):
    """Audit iterable of dict rows. Return JSON-serializable quality report."""
    groups = defaultdict(list)
    invalid = defaultdict(int)
    total = 0
    naive_timestamps = 0
    valid_rows = 0
    duplicate_rows = 0
    out_of_order = 0

    for row_number, row in enumerate(rows, start=2):
        total += 1
        normalized = {_norm(k): v for k, v in row.items() if k is not None}
        values = {}
        for field, aliases in ALIASES.items():
            values[field] = next(
                (normalized[name] for name in aliases
                 if name in normalized and str(normalized[name]).strip() != ""),
                "",
            )

        symbol = str(values["symbol"]).strip().upper()
        exchange = str(values["exchange"]).strip().upper() or "UNKNOWN"
        interval_value = str(values["interval"]).strip() or "5m"
        interval = _interval_minutes(interval_value)
        timestamp, naive = _parse_timestamp(values["timestamp"])
        ohlc = {name: _number(values[name]) for name in ("open", "high", "low", "close")}
        volume = _number(values["volume"]) if str(values["volume"]).strip() else 0.0

        reasons = []
        if not symbol:
            reasons.append("missing_symbol")
        if timestamp is None:
            reasons.append("invalid_timestamp")
        elif naive:
            naive_timestamps += 1
        if interval is None:
            reasons.append("invalid_interval")
        if any(value is None for value in ohlc.values()):
            reasons.append("invalid_ohlc_number")
        elif (ohlc["low"] <= 0 or ohlc["close"] <= 0
              or ohlc["high"] < max(ohlc["open"], ohlc["close"], ohlc["low"])
              or ohlc["low"] > min(ohlc["open"], ohlc["close"], ohlc["high"])):
            reasons.append("invalid_ohlc_geometry")
        if volume is None or volume < 0:
            reasons.append("invalid_volume")

        if reasons:
            for reason in reasons:
                invalid[reason] += 1
            continue

        valid_rows += 1
        if timestamp.tzinfo is not None:
            timestamp_key = timestamp.astimezone(dt.timezone.utc).isoformat()
        else:
            timestamp_key = timestamp.isoformat()
        key = (symbol, exchange, interval)
        groups[key].append({
            "row_number": row_number,
            "timestamp": timestamp,
            "timestamp_key": timestamp_key,
            "interval_minutes": interval,
        })

    reports = []
    for key, records in sorted(groups.items()):
        previous_input = None
        for record in records:
            if previous_input is not None and record["timestamp"] < previous_input:
                out_of_order += 1
            previous_input = record["timestamp"]

        seen = set()
        unique = []
        for record in records:
            if record["timestamp_key"] in seen:
                duplicate_rows += 1
                continue
            seen.add(record["timestamp_key"])
            unique.append(record)
        unique.sort(key=lambda record: record["timestamp"])

        interval = key[2]
        # Only count plausible intraday gaps; overnight/session breaks are
        # intentionally excluded to avoid labelling them as missing candles.
        gap_count = 0
        estimated_missing = 0
        for left, right in zip(unique, unique[1:]):
            try:
                delta_minutes = (right["timestamp"] - left["timestamp"]).total_seconds() / 60
            except (TypeError, ValueError):
                continue
            if delta_minutes > interval * 1.5 and delta_minutes <= interval * 6:
                gap_count += 1
                estimated_missing += max(1, int(round(delta_minutes / interval)) - 1)

        count = len(unique)
        reports.append({
            "symbol": key[0],
            "exchange": key[1],
            "interval_minutes": interval,
            "rows_valid_before_dedup": len(records),
            "unique_bars": count,
            "duplicate_rows": len(records) - count,
            "out_of_order_rows": sum(
                1 for left, right in zip(records, records[1:])
                if right["timestamp"] < left["timestamp"]
            ),
            "plausible_intraday_gap_count": gap_count,
            "estimated_missing_intraday_bars": estimated_missing,
            "enough_bars_for_70_30_holdout": count >= min_bars,
            "holdout_eligible_min_bars": min_bars,
        })

    return {
        "mode": "OFFLINE_CSV_AUDIT",
        "orders_enabled": False,
        "total_rows": total,
        "valid_rows_before_dedup": valid_rows,
        "invalid_rows": total - valid_rows,
        "invalid_reason_counts": dict(sorted(invalid.items())),
        "duplicate_rows": duplicate_rows,
        "naive_timestamp_rows": naive_timestamps,
        "out_of_order_rows": out_of_order,
        "groups": reports,
        "holdout_eligible_groups": sum(
            1 for group in reports if group["enough_bars_for_70_30_holdout"]
        ),
        "min_bars_for_holdout": min_bars,
        "warning": (
            "Structural audit only. It does not verify source licensing, market-session "
            "completeness, contract survivorship, official prices, executable fills, or profitability."
        ),
    }


def audit_file(path, min_bars=100):
    with open(path, "r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError("CSV must include a header row.")
        normalized_headers = {_norm(name) for name in reader.fieldnames}
        required = {"timestamp", "symbol", "open", "high", "low", "close"}
        recognized = {
            field for field, aliases in ALIASES.items()
            if normalized_headers.intersection(aliases)
        }
        missing = sorted(required - recognized)
        if missing:
            raise ValueError("Missing required CSV columns: " + ", ".join(missing))
        return audit_rows(reader, min_bars=min_bars)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Offline CSV integrity audit for India F&O OHLC candles."
    )
    parser.add_argument("csv_file", help="path to historical candle CSV")
    parser.add_argument("--min-bars", type=int, default=100,
                        help="minimum unique bars per group for 70/30 holdout (default: 100)")
    parser.add_argument("--json", action="store_true", help="print machine-readable JSON")
    args = parser.parse_args(argv)
    if args.min_bars < 60:
        parser.error("--min-bars must be at least 60 so train and holdout can each contain 30 bars")
    try:
        report = audit_file(args.csv_file, min_bars=args.min_bars)
    except (OSError, UnicodeError, csv.Error, ValueError) as exc:
        print("CSV audit failed: {}".format(exc), file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, indent=2))
        return 0

    print("India F&O CSV audit — OFFLINE; orders_enabled=False")
    print("Rows: total={} valid={} invalid={} duplicates={}".format(
        report["total_rows"], report["valid_rows_before_dedup"],
        report["invalid_rows"], report["duplicate_rows"]))
    print("Timezone-naive timestamps={} out-of-order rows={}".format(
        report["naive_timestamp_rows"], report["out_of_order_rows"]))
    for group in report["groups"]:
        eligible = "ELIGIBLE" if group["enough_bars_for_70_30_holdout"] else "NOT ENOUGH BARS"
        print("{symbol} {exchange} {interval_minutes}m: unique={unique_bars}, gaps={plausible_intraday_gap_count}, estimated_missing={estimated_missing_intraday_bars}, holdout={eligible}".format(
            eligible=eligible, **group))
    if report["invalid_reason_counts"]:
        print("Invalid reasons: {}".format(json.dumps(report["invalid_reason_counts"], sort_keys=True)))
    print("WARNING: " + report["warning"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
