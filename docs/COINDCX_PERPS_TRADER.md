# CoinDCX Perpetuals Trader

Run `python3 trader-perps/perps.py scan` for public USDT perpetual instrument,
mark/funding and 5m/1h candle analysis. Run `paper-entry` to open a qualifying
isolated-margin paper position. No live exchange action exists.

The mechanical setup requires 1h structure bias and 5m sweep, reclaim,
displacement/BOS and FVG. This is unvalidated and needs walk-forward/OOS
evaluation before any performance claim. Default risk is 0.5% equity, leverage
2x, and initial margin capped at 20% of equity.

OI is omitted. Funding events are never guessed. Liquidation estimate is
approximate. Fee/slippage defaults are illustrative, not exchange quotes.
