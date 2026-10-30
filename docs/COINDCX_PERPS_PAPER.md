# CoinDCX USDT Perpetuals - Paper Trader

Paper-only implementation. There is no authentication, order placement, cancel, or live-execution code.

## Modules
- `coindcx_perps.py`: read-only public Futures data client (USDT active instruments, instrument metadata, ticker/mark/funding fields, candles, trades, order book).
- `perps_paper.py`: isolated-margin LONG/SHORT paper engine with leverage, contract quantity step/minimum, fees, configurable slippage, mark-to-market P&L, explicit funding events, daily loss entry guard, idempotency, JSONL journal recovery and a labelled approximate liquidation estimate.

## Important modelling limits
- Supply quantity increment, minimum size and maintenance margin from verified instrument metadata. Do not use undocumented leverage fields as a risk rule.
- Funding is applied only when the caller supplies an actual funding event ID, rate and mark. No funding schedule is guessed. The model assumes positive funding means longs pay shorts; verify current exchange sign and settlement rules before reconciliation.
- Liquidation price is a simplified isolated-margin estimate. It excludes maintenance tiers, close/liquidation fees, exchange risk limits and liquidation mechanics; it is not an exchange quote.
- Cross margin, hedge mode and auto-deleveraging are not modelled. Close a position before reversing it.
- Open interest is intentionally absent until a documented public source is verified; volume is not used as a proxy.
- Marks are caller-supplied and not persisted. Refresh them after restart. The daily loss guard blocks new entries but does not force-close existing positions.
- Default fee/slippage rates are illustrative only, not CoinDCX fee quotes or measured execution costs. Configure from verified conditions.
- No automatic trading strategy or live execution is enabled.

## Example
```python
from perps_paper import PerpsPaperTrader
bot = PerpsPaperTrader(starting_balance="1000", journal_path="data/perps.jsonl")
bot.update_marks({"B-BTC_USDT": "65000"})
bot.open_position("B-BTC_USDT", "LONG", "65000", "0.001", "3",
                  signal_id="paper-entry-001",
                  quantity_step="0.001", min_quantity="0.001")
# Call only for an observed, verified settlement event:
bot.apply_funding("B-BTC_USDT", "0.0001", "funding-event-001", "65000")
bot.close_position("B-BTC_USDT", "65200", "paper-exit-001")
```
