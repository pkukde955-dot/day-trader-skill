# India F&O data feasibility probe (read-only)

This diagnostic is nested under the existing scanner skill to preserve the repository's root layout.

## Run on Android / Termux

From the repository root:

```sh
python trader-scanner/india_fno/probe.py --timeout 8
python trader-scanner/india_fno/probe.py --chart-only --symbols '^NSEI,^NSEBANK,^BSESN,RELIANCE.NS,HDFCBANK.NS,INFY.NS' --json
python -m unittest discover -s tests -p 'test_india_fno_probe.py' -v
```

The script uses only Python's standard library. It sends read-only HTTPS requests to Yahoo Finance's unofficial chart and options endpoints. It does not request credentials, write files, connect to a broker, or place orders.

## Scope / limitations

- A successful chart response proves only that Yahoo returned bars for that symbol at that moment. It does **not** prove real-time freshness, completeness, exchange accuracy, or permission to use the data for automated trading.
- The probe now reports `freshness`, `age_seconds`, and `fresh` separately from endpoint availability. For the 5-minute chart request, the default freshness threshold is 15 minutes with a 60-second future-timestamp tolerance. A stale/future/misaligned response is not marked fresh; this diagnostic threshold does not certify market-session correctness or tradability.
- The options endpoint probe is experimental. An empty/error response means options availability was not confirmed; it is not proof that the exchange has no contracts.
- This is not yet an NSE/BSE futures-and-options scanner. It does not calculate option-chain signals, futures basis, open interest, IV/Greeks, lot-size-aware risk, or broker instruments.
- Do not use Yahoo responses as an execution feed. For reliable real-time NSE F&O data, consult the exchange's current licensing terms and/or a broker's documented market-data API.
- All outputs are read-only diagnostics. Live trading is out of scope and remains disabled.

The first implementation milestone is to observe actual endpoint responses on-device, then select a lawful, stable source before adding any strategy logic.


## Offline historical CSV integrity audit

Before interpreting dashboard backtest results, audit the exact CSV file you intend to import:

```sh
python trader-scanner/india_fno/csv_audit.py /path/to/candles.csv
python trader-scanner/india_fno/csv_audit.py /path/to/candles.csv --json
```

The audit checks required headers, parseable timestamps, finite OHLC/volume values, OHLC geometry, duplicate bars, input ordering, timezone-naive timestamps, plausible intraday gaps, and whether each symbol/exchange/timeframe group has at least 100 unique bars for the dashboard's 70/30 holdout. The report is local and read-only; it does not upload the CSV or connect to a broker.

Naive timestamps are provisionally treated as UTC for comparison so mixed timezone formats do not crash the audit, but they are counted and should be corrected at the source. Gap estimates deliberately ignore very long breaks because overnight/session gaps must not be treated as missing candles. Verify session calendars and the data source separately.

Example command from the repository root on Android/Termux:

```sh
python trader-scanner/india_fno/csv_audit.py ~/storage/downloads/nifty-candles.csv
```

Replace the example path with the actual downloaded CSV path. Do not use a file containing only the format-example row as a backtest dataset.
