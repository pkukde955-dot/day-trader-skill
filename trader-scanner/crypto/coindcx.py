"""CoinDCX public Spot market-data client. No credentials or order methods."""

import json
import re
import urllib.parse
import urllib.request
from decimal import Decimal, InvalidOperation


BASE_URL = "https://api.coindcx.com"
VALID_INTERVALS = {"1m", "15m", "1h", "1d"}
PAIR_RE = re.compile(r"^B-[A-Z0-9]+_[A-Z0-9]+$")


class CoinDCXError(Exception):
    pass


class CoinDCXClient:
    def __init__(self, timeout=10):
        self.timeout = timeout

    def _get(self, path, params=None):
        query = urllib.parse.urlencode(params or {})
        url = BASE_URL + path + (("?" + query) if query else "")
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "day-trader-skill/1.0"}
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                if response.status != 200:
                    raise CoinDCXError("HTTP status: " + str(response.status))
                payload = response.read(5_000_000)
            data = json.loads(payload.decode("utf-8"))
        except CoinDCXError:
            raise
        except Exception as exc:
            raise CoinDCXError("CoinDCX request failed: " + str(exc)) from exc

        if not isinstance(data, (list, dict)):
            raise CoinDCXError("Unexpected API response")
        return data

    @staticmethod
    def _validate_pair(pair):
        if not isinstance(pair, str) or not PAIR_RE.fullmatch(pair):
            raise ValueError("Pair must look like B-BTC_USDT")

    @staticmethod
    def _decimal(value, field):
        try:
            result = Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError):
            raise CoinDCXError("Invalid numeric field: " + field)
        if not result.is_finite():
            raise CoinDCXError("Non-finite numeric field: " + field)
        return result

    def markets(self):
        data = self._get("/exchange/v1/markets")
        if not all(isinstance(item, str) for item in data):
            raise CoinDCXError("Invalid markets response")
        return data

    def ticker(self):
        data = self._get("/exchange/ticker")
        if not isinstance(data, list):
            raise CoinDCXError("Invalid ticker response")
        return data

    def ticker_for(self, pair):
        self._validate_pair(pair)
        symbol = pair[2:].replace("_", "")
        for item in self.ticker():
            if item.get("market") == symbol:
                return item
        raise CoinDCXError("Ticker not found for " + pair)

    def candles(self, pair, interval="1m", limit=200,
                start_time=None, end_time=None):
        self._validate_pair(pair)
        if interval not in VALID_INTERVALS:
            raise ValueError("Unsupported candle interval")
        if not isinstance(limit, int) or not 1 <= limit <= 1000:
            raise ValueError("limit must be between 1 and 1000")

        params = {"pair": pair, "interval": interval, "limit": limit}
        if start_time is not None:
            params["startTime"] = int(start_time)
        if end_time is not None:
            params["endTime"] = int(end_time)

        rows = self._get("/market_data/candles", params)
        if not isinstance(rows, list):
            raise CoinDCXError("Invalid candles response")

        result = []
        for row in rows:
            try:
                candle = {
                    "time": int(row["time"]),
                    "open": self._decimal(row["open"], "open"),
                    "high": self._decimal(row["high"], "high"),
                    "low": self._decimal(row["low"], "low"),
                    "close": self._decimal(row["close"], "close"),
                    "volume": self._decimal(row["volume"], "volume"),
                }
            except (KeyError, TypeError, ValueError) as exc:
                raise CoinDCXError("Malformed candle: " + str(exc)) from exc

            if candle["low"] > candle["high"]:
                raise CoinDCXError("Candle low exceeds high")
            if candle["volume"] < 0:
                raise CoinDCXError("Negative candle volume")
            result.append(candle)

        return sorted(result, key=lambda item: item["time"])

    def validated_candles(
        self, pair, interval="1m", limit=200, now_ms=None,
        max_age_intervals=2
    ):
        """Fetch candles and reject stale, incomplete or invalid data."""
        import time

        interval_ms = {
            "1m": 60_000,
            "15m": 900_000,
            "1h": 3_600_000,
            "1d": 86_400_000,
        }.get(interval)

        if interval_ms is None:
            raise ValueError("Unsupported validated candle interval")

        if now_ms is None:
            now_ms = int(time.time() * 1000)

        rows = self.candles(pair, interval=interval, limit=limit)
        return validate_candles(
            rows,
            interval_ms=interval_ms,
            now_ms=now_ms,
            max_age_intervals=max_age_intervals,
        )

    def orderbook(self, pair, depth=50):
        self._validate_pair(pair)
        if depth not in (1, 5, 10, 20, 50, 100, 200):
            raise ValueError("Unsupported orderbook depth")
        data = self._get("/market_data/orderbook", {
            "pair": pair, "depth": depth
        })
        if not isinstance(data, dict) or not isinstance(data.get("bids"), dict) or not isinstance(data.get("asks"), dict):
            raise CoinDCXError("Invalid orderbook response")
        return data


def aggregate_candles(candles, minutes=5):
    """Aggregate complete, consecutive 1-minute candles into larger candles."""
    from collections import defaultdict

    if not isinstance(minutes, int) or minutes < 2:
        raise ValueError("minutes must be an integer >= 2")

    duration = minutes * 60_000
    groups = defaultdict(dict)

    for candle in candles:
        timestamp = int(candle["time"])
        bucket = (timestamp // duration) * duration
        slot = (timestamp - bucket) // 60_000

        if timestamp != bucket + slot * 60_000:
            continue
        if slot >= minutes:
            continue
        if slot in groups[bucket]:
            groups[bucket][slot] = None
        else:
            groups[bucket][slot] = candle

    result = []
    for bucket in sorted(groups):
        slots = groups[bucket]
        if len(slots) != minutes:
            continue
        if any(slots.get(i) is None for i in range(minutes)):
            continue

        rows = [slots[i] for i in range(minutes)]
        if any(
            int(rows[i]["time"]) - int(rows[i - 1]["time"]) != 60_000
            for i in range(1, minutes)
        ):
            continue

        result.append({
            "time": bucket,
            "open": rows[0]["open"],
            "high": max(row["high"] for row in rows),
            "low": min(row["low"] for row in rows),
            "close": rows[-1]["close"],
            "volume": sum(
                (row["volume"] for row in rows),
                start=rows[0]["volume"] * 0
            ),
        })

    return result


def validate_candles(candles, interval_ms, now_ms, max_age_intervals=2):
    """Reject malformed, incomplete, non-contiguous or stale candle data."""
    if not isinstance(interval_ms, int) or interval_ms <= 0:
        raise ValueError("interval_ms must be positive")
    if not isinstance(max_age_intervals, int) or max_age_intervals < 1:
        raise ValueError("max_age_intervals must be >= 1")
    if not candles:
        raise CoinDCXError("No candle data")

    rows = sorted(candles, key=lambda item: int(item["time"]))
    previous_time = None

    for row in rows:
        try:
            timestamp = int(row["time"])
            op = Decimal(str(row["open"]))
            high = Decimal(str(row["high"]))
            low = Decimal(str(row["low"]))
            close = Decimal(str(row["close"]))
            volume = Decimal(str(row["volume"]))
        except (KeyError, TypeError, ValueError, InvalidOperation):
            raise CoinDCXError("Malformed candle data")

        values = (op, high, low, close, volume)
        if not all(value.is_finite() for value in values):
            raise CoinDCXError("Non-finite candle value")
        if timestamp % interval_ms:
            raise CoinDCXError("Candle timestamp is off interval grid")
        if high < max(op, close, low) or low > min(op, close, high):
            raise CoinDCXError("Invalid OHLC relationship")
        if volume < 0:
            raise CoinDCXError("Negative candle volume")
        if previous_time is not None:
            if timestamp == previous_time:
                raise CoinDCXError("Duplicate candle timestamp")
            if timestamp - previous_time != interval_ms:
                raise CoinDCXError("Missing candle interval")
        previous_time = timestamp

    latest_close_time = previous_time + interval_ms
    if latest_close_time > now_ms:
        raise CoinDCXError("Latest candle is not complete")
    if now_ms - latest_close_time > max_age_intervals * interval_ms:
        raise CoinDCXError("Stale candle data")

    return rows
