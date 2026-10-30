"""CoinDCX USDT-margined perpetual public market-data client.

Read-only: this module has no authentication, account, or order-placement methods.
Endpoints follow the official CoinDCX Futures API reference.
"""
import json
import re
import urllib.parse
import urllib.request
from decimal import Decimal, InvalidOperation

API_BASE = "https://api.coindcx.com"
PUBLIC_BASE = "https://public.coindcx.com"
PAIR_RE = re.compile(r"^B-[A-Z0-9]+_USDT$")
CANDLE_RESOLUTIONS = {"1m": "1", "5m": "5", "1h": "60", "1d": "1D"}


class PerpsDataError(Exception):
    """Invalid, unavailable, or malformed Perps market data."""


class CoinDCXPerpsClient:
    def __init__(self, timeout=10):
        self.timeout = timeout

    def _get(self, base, path, params=None):
        query = urllib.parse.urlencode(params or {}, doseq=True)
        url = base + path + (("?" + query) if query else "")
        request = urllib.request.Request(
            url, headers={"User-Agent": "day-trader-skill-perps/0.1"}
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                if response.status != 200:
                    raise PerpsDataError("HTTP status: " + str(response.status))
                raw = response.read(5_000_000)
            data = json.loads(raw.decode("utf-8"))
        except PerpsDataError:
            raise
        except Exception as exc:
            raise PerpsDataError("CoinDCX Perps request failed: " + str(exc)) from exc
        if not isinstance(data, (dict, list)):
            raise PerpsDataError("Unexpected API response")
        return data

    @staticmethod
    def validate_pair(pair):
        if not isinstance(pair, str) or not PAIR_RE.fullmatch(pair):
            raise ValueError("Pair must be a USDT perpetual such as B-BTC_USDT")

    @staticmethod
    def decimal(value, field):
        try:
            number = Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise PerpsDataError("Invalid numeric field: " + field) from exc
        if not number.is_finite():
            raise PerpsDataError("Non-finite numeric field: " + field)
        return number

    def active_instruments(self):
        rows = self._get(
            API_BASE,
            "/exchange/v1/derivatives/futures/data/active_instruments",
            {"margin_currency_short_name[]": "USDT"},
        )
        if not isinstance(rows, list) or any(
            not isinstance(pair, str) or not PAIR_RE.fullmatch(pair)
            for pair in rows
        ):
            raise PerpsDataError("Invalid USDT active instruments response")
        return rows

    def instrument(self, pair):
        self.validate_pair(pair)
        data = self._get(
            API_BASE,
            "/exchange/v1/derivatives/futures/data/instrument",
            {"pair": pair, "margin_currency_short_name": "USDT"},
        )
        item = data.get("instrument") if isinstance(data, dict) else None
        if not isinstance(item, dict) or item.get("pair") != pair:
            raise PerpsDataError("Instrument details missing or mismatched")
        if item.get("kind") != "perpetual" or item.get("settle_currency_short_name") != "USDT":
            raise PerpsDataError("Instrument is not a USDT-settled perpetual")
        for key in ("price_increment", "quantity_increment", "min_trade_size"):
            value = self.decimal(item.get(key), key)
            if value <= 0:
                raise PerpsDataError("Invalid instrument constraint: " + key)
        return item

    def current_prices(self):
        data = self._get(
            PUBLIC_BASE, "/market_data/v3/current_prices/futures/rt"
        )
        if not isinstance(data, dict) or not isinstance(data.get("prices"), dict):
            raise PerpsDataError("Invalid futures current-prices response")
        return data

    def ticker_for(self, pair):
        self.validate_pair(pair)
        data = self.current_prices()
        item = data["prices"].get(pair)
        if not isinstance(item, dict):
            raise PerpsDataError("No current futures ticker for " + pair)
        result = dict(item)
        for key in ("ls", "mp", "fr", "efr", "v"):
            if key in result and result[key] is not None:
                result[key] = self.decimal(result[key], key)
        result["timestamp"] = data.get("ts")
        return result

    def candles(self, pair, resolution="5m", start_seconds=None, end_seconds=None):
        self.validate_pair(pair)
        if resolution not in CANDLE_RESOLUTIONS:
            raise ValueError("Supported resolutions: 1m, 5m, 1h, 1d")
        if start_seconds is None or end_seconds is None:
            raise ValueError("start_seconds and end_seconds are required")
        if int(start_seconds) < 0 or int(end_seconds) <= int(start_seconds):
            raise ValueError("Invalid candle time range")
        rows = self._get(
            PUBLIC_BASE, "/market_data/candlesticks",
            {
                "pair": pair, "from": int(start_seconds),
                "to": int(end_seconds),
                "resolution": CANDLE_RESOLUTIONS[resolution], "pcode": "f",
            },
        )
        if not isinstance(rows, list):
            raise PerpsDataError("Invalid futures candles response")
        result = []
        for row in rows:
            try:
                candle = {
                    "time": int(row["time"]),
                    "open": self.decimal(row["open"], "open"),
                    "high": self.decimal(row["high"], "high"),
                    "low": self.decimal(row["low"], "low"),
                    "close": self.decimal(row["close"], "close"),
                    "volume": self.decimal(row["volume"], "volume"),
                }
            except (KeyError, TypeError, ValueError) as exc:
                raise PerpsDataError("Malformed futures candle") from exc
            if (candle["low"] <= 0 or candle["high"] < max(
                candle["open"], candle["close"], candle["low"]
            ) or candle["low"] > min(
                candle["open"], candle["close"], candle["high"]
            ) or candle["volume"] < 0):
                raise PerpsDataError("Invalid futures candle values")
            result.append(candle)
        return sorted(result, key=lambda item: item["time"])

    def trades(self, pair):
        self.validate_pair(pair)
        rows = self._get(
            API_BASE, "/exchange/v1/derivatives/futures/data/trades",
            {"pair": pair},
        )
        if not isinstance(rows, list):
            raise PerpsDataError("Invalid futures trades response")
        return rows

    def orderbook(self, pair, depth=50):
        self.validate_pair(pair)
        if depth not in (10, 20, 50):
            raise ValueError("Futures orderbook depth must be 10, 20 or 50")
        data = self._get(
            PUBLIC_BASE, f"/market_data/v3/orderbook/{pair}-futures/{depth}"
        )
        if not isinstance(data, dict) or not isinstance(
            data.get("bids"), dict
        ) or not isinstance(data.get("asks"), dict):
            raise PerpsDataError("Invalid futures orderbook response")
        return data

    @staticmethod
    def funding_snapshot(ticker, instrument):
        """Return documented funding fields; no funding/OI values are inferred."""
        return {
            "funding_rate": ticker.get("fr"),
            "effective_funding_rate": ticker.get("efr"),
            "funding_frequency_hours": instrument.get("funding_frequency"),
            "mark_price": ticker.get("mp"),
            "last_price": ticker.get("ls"),
        }
