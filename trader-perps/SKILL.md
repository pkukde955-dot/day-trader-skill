---
name: trader-perps
description: CoinDCX USDT perpetual scanner and isolated-margin paper trader. Reads verified public market data, checks higher-timeframe structure and lower-timeframe liquidity sweep, reclaim, break of structure and fair-value-gap confluence, sizes paper positions with leverage and risk caps, and journals paper trades. It does not authenticate or place live exchange orders.
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


## Supported markets and data

The client accepts only CoinDCX perpetual symbols settled in USDT, such as
`B-BTC_USDT`. Instrument metadata supplies quantity increment, minimum
quantity and price increment. Ticker fields include last price, mark price and
documented funding fields. Candles are requested at 5-minute and 1-hour
resolution. The tool does not infer open interest from volume.

## Signal interpretation

The higher-timeframe filter compares the last ten hourly candles with the
preceding ten for higher highs and higher lows, or lower highs and lower lows.
The entry filter checks the previous ten 5-minute candles for a liquidity
sweep, then requires a reclaim and a following close through the sweep candle
with a three-candle fair-value gap. If one condition is absent, the signal is
NONE. This intentionally produces fewer signals than a simple moving-average
cross.

This is a compact, deterministic interpretation of selected ICT concepts. It
does not identify every order block, market structure shift, premium/discount
zone, or institutional order flow event. Do not treat a label as proof that
large participants entered a position.

## Paper execution

The paper-entry command is explicit. It sizes quantity from the configured
equity risk fraction and stop distance, then caps notional by the configured
leverage and initial-margin fraction. The paper engine applies configurable
fees and slippage, tracks isolated margin and mark-to-market P&L, and rejects
duplicate signal identifiers. The JSONL journal restores balances, open
positions, funding-event IDs and used signal IDs after a restart.

The paper engine does not submit an order to CoinDCX. It does not know your
actual account balance, fee tier, funding settlement schedule or maintenance
margin bracket. Configure assumptions from verified information before
interpreting a simulation. The default fee and slippage values are examples.

## Mandatory safety limits

- Start with `scan`; it is read-only.
- `paper-entry` creates a simulated position only.
- Never put exchange API credentials in this project or a chat.
- Live trading is not implemented and must remain unavailable.
- Use isolated margin only; cross margin and hedge mode are not modelled.
- Do not treat approximate liquidation output as an exchange liquidation quote.
- Funding is not auto-applied. Supply a verified event and unique event ID.
- OI is not shown until a documented public endpoint is verified.
- A daily loss breach blocks new paper entries; it does not flatten positions.
- Review the paper journal and the latest mark before making a decision.
- A missing, stale or malformed market-data response must be treated as no signal.
- This tool is not financial advice. Perpetual futures can lose the full margin
  and leverage magnifies losses.

## Output fields

The watchlist records pair, mark price, ticker timestamp, contract increments,
funding fields, candle counts and setup result. A paper-entry result includes
the simulated fill, quantity, margin, fee and an explicitly approximate
liquidation estimate. An ERROR or NONE is not a trade setup.

## Validation

Run the focused offline tests with:

```bash
python3 -m unittest discover -s tests -p 'test_coindcx_perps.py' -v
python3 -m unittest discover -s tests -p 'test_perps_paper.py' -v
python3 -m unittest discover -s tests -p 'test_perps_strategy.py' -v
```

No long-running soak test is part of the build gate. A later release needs
verified endpoint probes, out-of-sample strategy evaluation, and review of
funding and liquidation rules before any live-execution design is considered.
