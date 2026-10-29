const test = require("node:test");
const assert = require("node:assert/strict");
const { analyse, scanHistory } = require("../trader-scanner/india_fno/dashboard/strategy.js");

function candlesWithBullishBreak() {
  const start = 1_790_000_000_000;
  const rows = [];
  for (let i = 0; i < 29; i++) {
    rows.push({
      symbol: "NIFTY", exchange: "NSE", interval: 5,
      ts: new Date(start + i * 300000).toISOString(),
      ms: start + i * 300000,
      open: 100, high: 100.5, low: 99.5, close: 100, volume: 100
    });
  }
  rows.push({
    symbol: "NIFTY", exchange: "NSE", interval: 5,
    ts: new Date(start + 29 * 300000).toISOString(),
    ms: start + 29 * 300000,
    open: 101, high: 106, low: 100.8, close: 105, volume: 200
  });
  return rows;
}

test("closed-bar bullish structure/FVG setup produces deterministic 2R references", () => {
  const rows = candlesWithBullishBreak();
  const signal = analyse(rows, rows.at(-1).ms + 300000);
  assert.equal(signal.signal, "BUY");
  assert.equal(signal.entry, 105);
  assert.ok(signal.stop < signal.entry);
  assert.equal(signal.target, signal.entry + 2 * (signal.entry - signal.stop));
});

test("future-dated candle is rejected", () => {
  const rows = candlesWithBullishBreak();
  const signal = analyse(rows, rows.at(-1).ms - 1000);
  assert.equal(signal.signal, "NO SIGNAL");
  assert.equal(signal.fresh, false);
  assert.match(signal.reason, /Future timestamp rejected/);
});

test("historical scan evaluates each bar from its prefix, not future candles", () => {
  const base = candlesWithBullishBreak();
  const original = scanHistory(base)[0];
  const appendedFuture = base.concat([
    {
      symbol: "NIFTY", exchange: "NSE", interval: 5,
      ts: new Date(base.at(-1).ms + 300000).toISOString(),
      ms: base.at(-1).ms + 300000,
      open: 105, high: 10000, low: 1, close: 9000, volume: 999999
    },
    {
      symbol: "NIFTY", exchange: "NSE", interval: 5,
      ts: new Date(base.at(-1).ms + 600000).toISOString(),
      ms: base.at(-1).ms + 600000,
      open: 9000, high: 12000, low: 8000, close: 11000, volume: 999999
    }
  ]);
  const withFuture = scanHistory(appendedFuture)[0];
  assert.equal(original.barIndex, 29);
  assert.equal(original.signal, "BUY");
  assert.equal(withFuture.signal, original.signal);
  assert.equal(withFuture.entry, original.entry);
  assert.equal(withFuture.stop, original.stop);
  assert.equal(withFuture.target, original.target);
});

test("history shorter than 30 candles produces no backtest signals", () => {
  assert.deepEqual(scanHistory(candlesWithBullishBreak().slice(0, 29)), []);
});
