---
name: trader-perps
description: CoinDCX USDT perpetual scanner and isolated-margin paper trader. Detects higher-timeframe bias plus 5m liquidity sweep, reclaim, BOS and FVG. No live order placement.
argument-hint: "scan | paper-entry [--pairs B-BTC_USDT,B-ETH_USDT]"
---
# CoinDCX Perpetuals Trader

Paper-first USDT perpetual workflow, separate from the US-equity scanner. It
does not authenticate or place/cancel exchange orders.

```bash
python3 "${CLAUDE_SKILL_DIR}/perps.py" scan
python3 "${CLAUDE_SKILL_DIR}/perps.py" scan --pairs B-BTC_USDT,B-ETH_USDT
python3 "${CLAUDE_SKILL_DIR}/perps.py" paper-entry --balance 1000 --risk 0.005 --leverage 2
```

Writes `trader/perps-watchlist.json`; paper state is
`trader/perps-paper.jsonl`.

Signal requires a 1h higher-high/higher-low or lower-high/lower-low bias, then
a 5m liquidity sweep, reclaim, displacement/BOS and three-candle FVG. Stop is
beyond the sweep and target defaults to 2R. This is a mechanical heuristic,
not a validated profitable strategy or full discretionary ICT analysis.

Paper controls: risk sizing, max 20% initial margin, isolated one-way positions,
daily loss entry guard, idempotency, fees/slippage assumptions and restart
journal. Funding is only applied when a verified event is explicitly supplied.
Liquidation estimate is approximate. OI is omitted until a documented source
is verified. Live execution is not implemented.
