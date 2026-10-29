(function (root, factory) {
  if (typeof module === "object" && module.exports) {
    module.exports = factory();
  } else {
    root.IndiaFnoStrategy = factory();
  }
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  function getSwing(arr, from, to, type) {
    var vals = arr.slice(from, to).map(function (c) {
      return type === "high" ? c.high : c.low;
    });
    if (!vals.length) return NaN;
    return type === "high" ? Math.max.apply(null, vals) : Math.min.apply(null, vals);
  }

  function analyse(group, nowMs) {
    if (!Array.isArray(group) || !group.length) {
      return { signal: "NO SIGNAL", reason: "No candles", fresh: false };
    }
    var c = group[group.length - 1];
    var n = group.length;
    var interval = Number(c.interval);
    var ageMin = ((nowMs === undefined ? Date.now() : nowMs) - c.ms) / 60000;
    var maxAge = interval * 2;
    var base = {
      symbol: c.symbol, exchange: c.exchange, ts: c.ts, age: ageMin,
      fresh: ageMin >= 0 && ageMin <= maxAge,
      signal: "NO SIGNAL", reason: "", entry: null, stop: null, target: null
    };
    if (n < 30) {
      base.reason = "Need at least 30 candles; got " + n;
      return base;
    }
    if (!base.fresh) {
      base.reason = ageMin < 0 ? "Future timestamp rejected" :
        "Stale data (" + Math.round(ageMin) + " min old; limit " + maxAge + " min)";
      return base;
    }

    var prev = group[n - 2];
    var swingHigh = getSwing(group, n - 21, n - 1, "high");
    var swingLow = getSwing(group, n - 21, n - 1, "low");
    var priorHigh = getSwing(group, n - 8, n - 2, "high");
    var priorLow = getSwing(group, n - 8, n - 2, "low");
    var bullishSweep = prev.low < priorLow && c.close > priorLow;
    var bearishSweep = prev.high > priorHigh && c.close < priorHigh;
    var bullBreak = c.close > swingHigh;
    var bearBreak = c.close < swingLow;
    var bullFVG = c.low > group[n - 3].high;
    var bearFVG = c.high < group[n - 3].low;
    var candleRange = c.high - c.low;
    var prevRange = prev.high - prev.low;
    var bullDisplacement = c.close > c.open && candleRange > 0 &&
      Math.abs(c.close - c.open) >= candleRange * 0.55 && candleRange >= prevRange * 0.8;
    var bearDisplacement = c.close < c.open && candleRange > 0 &&
      Math.abs(c.close - c.open) >= candleRange * 0.55 && candleRange >= prevRange * 0.8;
    var bull = (bullishSweep || bullBreak) && (bullFVG || bullDisplacement);
    var bear = (bearishSweep || bearBreak) && (bearFVG || bearDisplacement);

    if (bull && !bear) {
      var stop = getSwing(group, n - 6, n, "low");
      if (!(stop < c.close)) stop = Math.min(c.low, prev.low);
      var risk = c.close - stop;
      if (risk > 0) {
        base.signal = "BUY";
        base.entry = c.close;
        base.stop = stop;
        base.target = c.close + 2 * risk;
        base.reason = [
          bullishSweep ? "Sell-side liquidity sweep" : "",
          bullBreak ? "Bullish structure break" : "",
          bullFVG ? "Bullish FVG" : "",
          bullDisplacement ? "Bullish displacement" : ""
        ].filter(Boolean).join(" + ");
      }
    } else if (bear && !bull) {
      var stop2 = getSwing(group, n - 6, n, "high");
      if (!(stop2 > c.close)) stop2 = Math.max(c.high, prev.high);
      var risk2 = stop2 - c.close;
      if (risk2 > 0) {
        base.signal = "SELL";
        base.entry = c.close;
        base.stop = stop2;
        base.target = c.close - 2 * risk2;
        base.reason = [
          bearishSweep ? "Buy-side liquidity sweep" : "",
          bearBreak ? "Bearish structure break" : "",
          bearFVG ? "Bearish FVG" : "",
          bearDisplacement ? "Bearish displacement" : ""
        ].filter(Boolean).join(" + ");
      }
    } else {
      base.reason = bull && bear ?
        "Conflicting bullish/bearish conditions" :
        "No qualifying sweep/structure + displacement/FVG";
    }
    return base;
  }

  // Historical simulation: each bar is evaluated using only the prefix ending
  // at that bar. The bar timestamp is treated as its opening time.
  function scanHistory(candles) {
    var results = [];
    if (!Array.isArray(candles)) return results;
    for (var i = 29; i < candles.length; i++) {
      var prefix = candles.slice(0, i + 1);
      var current = prefix[prefix.length - 1];
      var closeTime = current.ms + Number(current.interval) * 60000;
      var result = analyse(prefix, closeTime);
      result.barIndex = i;
      results.push(result);
    }
    return results;
  }

  return { analyse: analyse, scanHistory: scanHistory, getSwing: getSwing };
});
