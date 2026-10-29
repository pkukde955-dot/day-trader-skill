const test = require("node:test");
const assert = require("node:assert/strict");
const { analyse, scanHistory, backtestHistory, walkForward } = require("../trader-scanner/india_fno/dashboard/strategy.js");

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

test("backtest enters next bar and records a target hit in R units", () => {
  const rows = candlesWithBullishBreak();
  const step = 300000;
  rows.push({
    symbol: "NIFTY", exchange: "NSE", interval: 5,
    ts: new Date(rows.at(-1).ms + step).toISOString(), ms: rows.at(-1).ms + step,
    open: 105, high: 106, low: 104, close: 105, volume: 100
  });
  rows.push({
    symbol: "NIFTY", exchange: "NSE", interval: 5,
    ts: new Date(rows.at(-1).ms + step).toISOString(), ms: rows.at(-1).ms + step,
    open: 105, high: 117, low: 104, close: 116, volume: 100
  });
  const result = backtestHistory(rows);
  assert.equal(result.trades.length, 1);
  assert.equal(result.trades[0].entryIndex, 30);
  assert.equal(result.trades[0].exitReason, "TARGET");
  assert.equal(result.trades[0].r, 2);
  assert.equal(result.costsIncluded, false);
});

test("same-bar stop and target collision resolves conservatively to stop", () => {
  const rows = candlesWithBullishBreak();
  const step = 300000;
  rows.push({
    symbol: "NIFTY", exchange: "NSE", interval: 5,
    ts: new Date(rows.at(-1).ms + step).toISOString(), ms: rows.at(-1).ms + step,
    open: 105, high: 106, low: 104, close: 105, volume: 100
  });
  rows.push({
    symbol: "NIFTY", exchange: "NSE", interval: 5,
    ts: new Date(rows.at(-1).ms + step).toISOString(), ms: rows.at(-1).ms + step,
    open: 105, high: 117, low: 99, close: 110, volume: 100
  });
  const result = backtestHistory(rows);
  assert.equal(result.trades.length, 1);
  assert.equal(result.trades[0].exitReason, "STOP_AND_TARGET_SAME_BAR_STOP_FIRST");
  assert.equal(result.trades[0].r, -1);
  assert.equal(result.losses, 1);
});

test("history shorter than 30 candles produces no backtest signals", () => {
  assert.deepEqual(scanHistory(candlesWithBullishBreak().slice(0, 29)), []);
});

test("round-trip cost assumption reduces net R and is exposed per trade", () => {
  const rows = candlesWithBullishBreak();
  const step = 300000;
  rows.push({
    symbol: "NIFTY", exchange: "NSE", interval: 5,
    ts: new Date(rows.at(-1).ms + step).toISOString(), ms: rows.at(-1).ms + step,
    open: 105, high: 106, low: 104, close: 105, volume: 100
  });
  rows.push({
    symbol: "NIFTY", exchange: "NSE", interval: 5,
    ts: new Date(rows.at(-1).ms + step).toISOString(), ms: rows.at(-1).ms + step,
    open: 105, high: 117, low: 104, close: 116, volume: 100
  });
  const gross = backtestHistory(rows);
  const withCosts = backtestHistory(rows, { costBpsRoundTrip: 100 });
  assert.equal(gross.trades.length, 1);
  assert.equal(withCosts.costsIncluded, true);
  assert.ok(withCosts.trades[0].costR > 0);
  assert.ok(withCosts.trades[0].r < gross.trades[0].r);
  assert.ok(withCosts.netR < withCosts.grossR);
  assert.equal(withCosts.costBpsRoundTrip, 100);
});

test("holdout validation requires enough history and uses chronological signal boundaries", () => {
  const tooShort = walkForward(candlesWithBullishBreak(), 0.7, 0);
  assert.equal(tooShort.valid, false);
  assert.match(tooShort.reason, /at least 100/);

  const rows = [];
  const start = 1_790_000_000_000;
  for (let i = 0; i < 120; i++) {
    rows.push({
      symbol: "NIFTY", exchange: "NSE", interval: 5,
      ts: new Date(start + i * 300000).toISOString(),
      ms: start + i * 300000,
      open: 100, high: 100.5, low: 99.5, close: 100, volume: 100
    });
  }
  const split = walkForward(rows, 0.7, 25);
  assert.equal(split.valid, true);
  assert.equal(split.splitIndex, 84);
  assert.equal(split.trainBars, 84);
  assert.equal(split.testBars, 36);
  assert.equal(split.train.costBpsRoundTrip, 25);
  assert.equal(split.test.costBpsRoundTrip, 25);
  assert.ok(split.test.trades.every((trade) => trade.signalIndex >= split.splitIndex));
  assert.ok(split.test.trades.every((trade) => trade.exitIndex < rows.length));
});
