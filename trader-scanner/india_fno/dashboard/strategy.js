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

  function backtestHistory(candles, options) {
    options = options || {};
    var trades = [];
    var skipped = 0;
    var openAtEnd = 0;
    var signalCount = 0;
    var equityR = 0;
    var grossRTotal = 0;
    var totalCostR = 0;
    var peakR = 0;
    var maxDrawdownR = 0;
    var n = Array.isArray(candles) ? candles.length : 0;
    var startIndex = Number.isFinite(Number(options.startIndex)) ? Math.max(29, Math.floor(Number(options.startIndex))) : 29;
    var endIndex = Number.isFinite(Number(options.endIndex)) ? Math.min(n - 1, Math.floor(Number(options.endIndex))) : n - 1;
    var costBpsRoundTrip = Number(options.costBpsRoundTrip);
    if (!Number.isFinite(costBpsRoundTrip) || costBpsRoundTrip < 0) costBpsRoundTrip = 0;
    var empty = { bars: n, trades: trades, signals: 0, skipped: 0, openAtEnd: 0,
      wins: 0, losses: 0, winRatePct: null, netR: 0, grossR: 0, totalCostR: 0,
      expectancyR: null, profitFactor: 0, maxDrawdownR: 0,
      costsIncluded: costBpsRoundTrip > 0, costBpsRoundTrip: costBpsRoundTrip };
    if (!Array.isArray(candles) || n < 30 || startIndex > endIndex || endIndex < 30) return empty;

    var i = startIndex;
    while (i < Math.min(n - 1, endIndex)) {
      var prefix = candles.slice(0, i + 1);
      var bar = candles[i];
      var signal = analyse(prefix, bar.ms + Number(bar.interval) * 60000);
      if (signal.signal !== "BUY" && signal.signal !== "SELL") {
        i++;
        continue;
      }
      signalCount++;
      var entryBar = candles[i + 1];
      var entry = Number(entryBar.open);
      var isLong = signal.signal === "BUY";
      var stop = Number(signal.stop);
      var target = Number(signal.target);
      var validGeometry = Number.isFinite(entry) && Number.isFinite(stop) &&
        Number.isFinite(target) && (isLong ? stop < entry && entry < target : target < entry && entry < stop);
      if (!validGeometry) {
        skipped++;
        i++;
        continue;
      }

      var risk = Math.abs(entry - stop);
      var exitPrice = null;
      var exitReason = "";
      var exitIndex = -1;
      for (var j = i + 1; j <= endIndex; j++) {
        var futureBar = candles[j];
        var open = Number(futureBar.open);
        var high = Number(futureBar.high);
        var low = Number(futureBar.low);
        if (![open, high, low].every(Number.isFinite)) continue;

        if (isLong && open >= target) {
          exitPrice = target; exitReason = "TARGET_GAP"; exitIndex = j; break;
        }
        if (!isLong && open <= target) {
          exitPrice = target; exitReason = "TARGET_GAP"; exitIndex = j; break;
        }
        if (isLong && open <= stop) {
          exitPrice = open; exitReason = "STOP_GAP"; exitIndex = j; break;
        }
        if (!isLong && open >= stop) {
          exitPrice = open; exitReason = "STOP_GAP"; exitIndex = j; break;
        }

        var stopTouched = isLong ? low <= stop : high >= stop;
        var targetTouched = isLong ? high >= target : low <= target;
        if (stopTouched && targetTouched) {
          exitPrice = stop; exitReason = "STOP_AND_TARGET_SAME_BAR_STOP_FIRST"; exitIndex = j; break;
        }
        if (stopTouched) {
          exitPrice = stop; exitReason = "STOP"; exitIndex = j; break;
        }
        if (targetTouched) {
          exitPrice = target; exitReason = "TARGET"; exitIndex = j; break;
        }
      }

      if (exitIndex < 0) {
        openAtEnd++;
        break;
      }
      var pnl = isLong ? exitPrice - entry : entry - exitPrice;
      var grossTradeR = pnl / risk;
      // User-supplied round-trip cost assumption, expressed in basis points of
      // entry notional. This is a sensitivity estimate, not a fee schedule.
      var costR = (entry * costBpsRoundTrip / 10000) / risk;
      var netTradeR = grossTradeR - costR;
      trades.push({
        signalIndex: i, entryIndex: i + 1, exitIndex: exitIndex,
        side: signal.signal, entry: entry, stop: stop, target: target,
        exit: exitPrice, exitReason: exitReason, grossR: grossTradeR,
        costR: costR, r: netTradeR
      });
      grossRTotal += grossTradeR;
      totalCostR += costR;
      equityR += netTradeR;
      peakR = Math.max(peakR, equityR);
      maxDrawdownR = Math.max(maxDrawdownR, peakR - equityR);
      i = exitIndex + 1;
    }

    var wins = trades.filter(function (t) { return t.r > 0; }).length;
    var losses = trades.filter(function (t) { return t.r < 0; }).length;
    var grossWinsR = trades.reduce(function (sum, t) { return sum + (t.r > 0 ? t.r : 0); }, 0);
    var grossLossesR = trades.reduce(function (sum, t) { return sum + (t.r < 0 ? -t.r : 0); }, 0);
    return {
      bars: candles.length, trades: trades, signals: signalCount, skipped: skipped,
      openAtEnd: openAtEnd, wins: wins, losses: losses,
      winRatePct: trades.length ? (wins / trades.length) * 100 : null,
      netR: equityR, grossR: grossRTotal, totalCostR: totalCostR,
      expectancyR: trades.length ? equityR / trades.length : null,
      profitFactor: grossLossesR ? grossWinsR / grossLossesR : (grossWinsR ? null : 0),
      maxDrawdownR: maxDrawdownR, costsIncluded: costBpsRoundTrip > 0,
      costBpsRoundTrip: costBpsRoundTrip
    };
  }

  // Chronological holdout validation: the test period may use earlier candles
  // as signal warm-up, but only signals from the test period count as test trades.
  function walkForward(candles, trainFraction, costBpsRoundTrip) {
    var rows = Array.isArray(candles) ? candles : [];
    var fraction = Number(trainFraction);
    if (!Number.isFinite(fraction) || fraction <= 0.5 || fraction >= 0.9) fraction = 0.7;
    var splitIndex = Math.floor(rows.length * fraction);
    if (rows.length < 100 || splitIndex < 30 || rows.length - splitIndex < 30) {
      return { valid: false, reason: "Need at least 100 chronological candles so both train and holdout periods have at least 30 bars.", bars: rows.length, splitIndex: splitIndex };
    }
    var train = backtestHistory(rows, { startIndex: 29, endIndex: splitIndex - 1, costBpsRoundTrip: costBpsRoundTrip });
    var test = backtestHistory(rows, { startIndex: splitIndex, endIndex: rows.length - 1, costBpsRoundTrip: costBpsRoundTrip });
    return { valid: true, bars: rows.length, splitIndex: splitIndex, trainFraction: fraction,
      trainBars: splitIndex, testBars: rows.length - splitIndex, train: train, test: test };
  }

  function backtestAll(candles) {
    var grouped = {};
    (Array.isArray(candles) ? candles : []).forEach(function (c) {
      var key = [c.symbol, c.exchange, c.interval].join("|");
      (grouped[key] || (grouped[key] = [])).push(c);
    });
    return Object.keys(grouped).sort().map(function (key) {
      var group = grouped[key].slice().sort(function (a, b) { return a.ms - b.ms; });
      var result = backtestHistory(group);
      result.symbol = group[0].symbol;
      result.exchange = group[0].exchange;
      result.interval = group[0].interval;
      return result;
    });
  }

  return { analyse: analyse, scanHistory: scanHistory, backtestHistory: backtestHistory, walkForward: walkForward, backtestAll: backtestAll, getSwing: getSwing };
});
