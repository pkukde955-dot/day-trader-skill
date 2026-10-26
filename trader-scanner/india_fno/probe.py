#!/usr/bin/env python3
"""Read-only feasibility probe for Indian market data; no orders or credentials.

Yahoo Finance endpoints are unofficial and may be delayed, incomplete, or changed.
This probe only reports what the endpoint returned; it does not validate trading use.
"""
import argparse
import datetime as dt
import json
import sys
import urllib.error
import urllib.parse
import urllib.request

UA = "Mozilla/5.0 (compatible; day-trader-skill-india-readonly-probe/0.1)"
DEFAULT_SYMBOLS = ["^NSEI", "^NSEBANK", "^CNXFINANCE", "^BSESN",
                   "RELIANCE.NS", "HDFCBANK.NS", "INFY.NS"]


def fetch_json(url, timeout=8):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        if response.status != 200:
            raise RuntimeError("HTTP {}".format(response.status))
        return json.loads(response.read().decode("utf-8"))


def parse_chart(payload):
    """Return a small, safe summary of Yahoo chart JSON."""
    chart = payload.get("chart") or {}
    error = chart.get("error")
    results = chart.get("result") or []
    if error:
        return {"ok": False, "error": error.get("description") or error.get("code") or "chart error"}
    if not results:
        return {"ok": False, "error": "No chart result"}
    item = results[0]
    timestamps = item.get("timestamp") or []
    indicators = item.get("indicators") or {}
    quote_list = indicators.get("quote") or []
    quote = quote_list[0] if quote_list else {}
    closes = quote.get("close") or []
    valid = [value for value in closes if isinstance(value, (int, float))]
    meta = item.get("meta") or {}
    last_epoch = timestamps[-1] if timestamps else None
    last_time = dt.datetime.fromtimestamp(last_epoch, dt.timezone.utc).isoformat() if last_epoch else None
    return {
        "ok": bool(valid),
        "symbol": meta.get("symbol"),
        "exchange": meta.get("exchangeName"),
        "instrument_type": meta.get("instrumentType"),
        "interval_bars_returned": len(timestamps),
        "valid_closes": len(valid),
        "last_bar_utc": last_time,
        "currency": meta.get("currency"),
        "error": None if valid else "No valid close values",
    }


def probe_chart(symbol, timeout=8):
    encoded = urllib.parse.quote(symbol, safe="")
    url = "https://query1.finance.yahoo.com/v8/finance/chart/{}?range=5d&interval=5m".format(encoded)
    try:
        result = parse_chart(fetch_json(url, timeout))
        result["requested_symbol"] = symbol
        result["endpoint"] = "Yahoo chart (unofficial)"
        return result
    except (OSError, ValueError, RuntimeError, urllib.error.URLError) as exc:
        return {"ok": False, "requested_symbol": symbol, "endpoint": "Yahoo chart (unofficial)",
                "error": "{}: {}".format(type(exc).__name__, str(exc)[:180])}


def probe_options(symbol, timeout=8):
    encoded = urllib.parse.quote(symbol, safe="")
    url = "https://query1.finance.yahoo.com/v7/finance/options/{}".format(encoded)
    try:
        payload = fetch_json(url, timeout)
        chain = (payload.get("optionChain") or {})
        error = chain.get("error")
        results = chain.get("result") or []
        if error:
            return {"ok": False, "requested_symbol": symbol, "endpoint": "Yahoo options (unofficial)",
                    "error": error.get("description") or error.get("code") or "options error"}
        if not results:
            return {"ok": False, "requested_symbol": symbol, "endpoint": "Yahoo options (unofficial)",
                    "error": "No options result; derivatives availability not confirmed"}
        item = results[0]
        options = item.get("options") or []
        calls = sum(len(x.get("calls") or []) for x in options)
        puts = sum(len(x.get("puts") or []) for x in options)
        return {"ok": calls + puts > 0, "requested_symbol": symbol,
                "endpoint": "Yahoo options (unofficial)", "expiry_dates": len(item.get("expirationDates") or []),
                "calls": calls, "puts": puts,
                "error": None if calls + puts else "No option contracts returned"}
    except (OSError, ValueError, RuntimeError, urllib.error.URLError) as exc:
        return {"ok": False, "requested_symbol": symbol, "endpoint": "Yahoo options (unofficial)",
                "error": "{}: {}".format(type(exc).__name__, str(exc)[:180])}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Read-only Indian market data availability probe (no trading).")
    parser.add_argument("--symbols", default=",".join(DEFAULT_SYMBOLS), help="comma-separated Yahoo symbols")
    parser.add_argument("--options-symbol", default="^NSEI", help="underlying symbol to test options endpoint")
    parser.add_argument("--timeout", type=float, default=8, help="per-request timeout seconds (default: 8)")
    parser.add_argument("--chart-only", action="store_true", help="skip options endpoint")
    parser.add_argument("--json", action="store_true", help="print JSON")
    args = parser.parse_args(argv)
    symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    report = {
        "mode": "READ_ONLY",
        "orders_enabled": False,
        "data_warning": "Yahoo endpoints are unofficial; success does not prove real-time, complete, licensed, or tradable F&O data.",
        "charts": [probe_chart(symbol, args.timeout) for symbol in symbols],
    }
    if not args.chart_only:
        report["options_probe"] = probe_options(args.options_symbol, args.timeout)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print("Indian market data probe - READ ONLY; orders_enabled=False")
        for item in report["charts"]:
            status = "OK" if item.get("ok") else "UNAVAILABLE"
            print("{:11} {:16} bars={} last_bar_utc={} {}".format(
                status, item.get("requested_symbol", "?"),
                item.get("interval_bars_returned", 0), item.get("last_bar_utc") or "-",
                item.get("error") or ""))
        if "options_probe" in report:
            item = report["options_probe"]
            status = "OK" if item.get("ok") else "UNAVAILABLE"
            print("{} options {}: expiries={} calls={} puts={} {}".format(
                status, item.get("requested_symbol"), item.get("expiry_dates", 0),
                item.get("calls", 0), item.get("puts", 0), item.get("error") or ""))
        print("NOTE: chart success is not proof of real-time data or usable NSE/BSE futures/options data.")
    return 0 if any(item.get("ok") for item in report["charts"]) else 2


if __name__ == "__main__":
    sys.exit(main())
