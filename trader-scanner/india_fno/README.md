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

## Historical validation in the dashboard

Load a chronological OHLC CSV and choose **Run historical backtest**. The dashboard groups rows by symbol, exchange, and interval, then evaluates each bar using only the history up to that bar. A qualifying signal is entered at the next candle open; one position per dataset is simulated at a time. If a candle touches both stop and target, the simulation assumes the stop was hit first. Open trades remaining at the end of the file are excluded from closed-trade statistics.

The report shows closed trades, win rate, net R, expectancy in R, profit factor, maximum drawdown in R, skipped entries, and any position still open at the end. Brokerage, taxes, spread, slippage, order-book liquidity, and partial fills are **not** included. Results are only a first-pass gross diagnostic; use separate out-of-sample data and realistic costs before drawing conclusions. This backtest does not prove profitability.

## Scope / limitations

- A successful chart response proves only that Yahoo returned bars for that symbol at that moment. It does **not** prove real-time freshness, completeness, exchange accuracy, or permission to use the data for automated trading.
- The probe now reports `freshness`, `age_seconds`, and `fresh` separately from endpoint availability. For the 5-minute chart request, the default freshness threshold is 15 minutes with a 60-second future-timestamp tolerance. A stale/future/misaligned response is not marked fresh; this diagnostic threshold does not certify market-session correctness or tradability.
- The options endpoint probe is experimental. An empty/error response means options availability was not confirmed; it is not proof that the exchange has no contracts.
- This is not yet an NSE/BSE futures-and-options scanner. It does not calculate option-chain signals, futures basis, open interest, IV/Greeks, lot-size-aware risk, or broker instruments.
- Do not use Yahoo responses as an execution feed. For reliable real-time NSE F&O data, consult the exchange's current licensing terms and/or a broker's documented market-data API.
- All outputs are read-only diagnostics. Live trading is out of scope and remains disabled.

The first implementation milestone is to observe actual endpoint responses on-device, then select a lawful, stable source before adding any strategy logic.
