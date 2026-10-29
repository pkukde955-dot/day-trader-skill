# India F&O SMC Signal Desk (manual trading)

A mobile-friendly, local-only dashboard for manually analysing NSE/BSE F&O candle CSVs. It does not connect to a broker, place orders, or scrape exchange websites.

## Run on Android / Termux

From the repository root:

```sh
sh trader-scanner/india_fno/start_dashboard.sh
```

Open `http://127.0.0.1:8766` in the phone browser. Stop with Ctrl+C.

## CSV inputs

### Candle CSV
Required headers (aliases are accepted): `timestamp`, `symbol`, `open`, `high`, `low`, `close`. Optional: `volume`, `interval` (examples `1m`, `5m`, `15m`, `1h`), `exchange`.

Use ISO timestamps with timezone where possible, e.g. `2026-10-26T09:15:00+05:30`. Load at least 30 candles per symbol, in chronological order or any order (the dashboard sorts them).

### Contract master (optional)
A CSV with a `symbol` or `tradingsymbol` column can filter the candle file to known contracts. Use a contract master from a source you are permitted to use. Confirm expiry, lot size, tick size and contract eligibility separately.

## Signal and freshness rules

- Browser-only CSV processing; imported data stays in the page and is not uploaded to a server.
- Latest candle must be no more than two candle intervals old. Old/future timestamps are marked and never produce a trade signal.
- Rule-based exploratory conditions: recent structure break or liquidity sweep, plus FVG or displacement proxy. BUY/SELL is a setup candidate, not a guarantee.
- Entry, stop and 2R target are reference levels calculated from imported candles. Verify spread, liquidity, contract details and risk before deciding manually.
- A missing or rejected dataset results in no signal. No broker API keys, live order path or automatic execution is included.

## Free-data limitation

Official exchange webpages can be viewed manually, and exchange reports may provide downloadable historical data. They are not automatically a licensed free real-time feed for an app. NSE website terms restrict aggregation/copying, and NSE Data & Analytics offers real-time and historical products under its data policies. Do not scrape exchange pages or assume a free public endpoint is authorized for continuous use. See:
- https://www.nseindia.com/option-chain
- https://www.nseindia.com/static/market-data/nse-data-policy
- https://www.nseindia.com/static/market-data/real-time-data-subscription
- https://www.bseindia.com/markets/Derivatives/DeriReports/DeriOptionchain.html

This first milestone deliberately uses imported CSV data instead of inventing a live feed. It is not yet an all-contract live scanner; a lawful current data source is needed for that.

## Historical validation: costs and holdout

- The dashboard can apply a user-entered round-trip cost sensitivity in basis points (bps) of entry notional. It deducts the estimate from each trade's gross R to report net R, expectancy and drawdown. The default is 0 bps, so set a cost assumption before interpreting results.
- This is a sensitivity estimate, **not** an official brokerage/tax calculator. It does not model exact order-book spread, partial fills, market impact, latency or instrument-specific fees; estimated costs do not make OHLC fills realistic.
- The chronological 70%/30% holdout reports the first 70% as the development period and the final 30% as the holdout. The holdout uses earlier candles only for signal warm-up; only signals generated inside the holdout are counted there. At least 100 candles per symbol/exchange/interval are required.
- This is a single chronological holdout, not a walk-forward parameter-optimization study. Do not tune rules against the holdout and then treat it as independent evidence. Prefer additional untouched periods and multiple market regimes.
- No strategy is declared profitable by this validation. CSV quality, survivorship/contract selection, missing candles, expiry/roll effects and real executable fills remain external risks.
