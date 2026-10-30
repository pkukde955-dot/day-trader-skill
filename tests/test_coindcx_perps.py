import unittest
from decimal import Decimal
from _load import load

perps = load("trader-scanner/crypto", "coindcx_perps")


class PerpsClientTests(unittest.TestCase):
    def setUp(self):
        self.client = perps.CoinDCXPerpsClient()

    def test_pair_validation_is_usdt_perps_only(self):
        self.client.validate_pair("B-BTC_USDT")
        for pair in ("B-BTC_INR", "BTCUSDT", "B-BTC_USDT;"):
            with self.assertRaises(ValueError):
                self.client.validate_pair(pair)

    def test_active_instruments_rejects_non_usdt_symbols(self):
        self.client._get = lambda *a, **k: ["B-BTC_USDT", "B-ETH_USDT"]
        self.assertEqual(len(self.client.active_instruments()), 2)
        self.client._get = lambda *a, **k: ["B-BTC_INR"]
        with self.assertRaises(perps.PerpsDataError):
            self.client.active_instruments()

    def test_instrument_requires_perpetual_usdt_settlement(self):
        good = {"instrument": {
            "pair": "B-BTC_USDT", "kind": "perpetual",
            "settle_currency_short_name": "USDT",
            "price_increment": "0.1", "quantity_increment": "0.001",
            "min_trade_size": "0.001",
        }}
        self.client._get = lambda *a, **k: good
        self.assertEqual(self.client.instrument("B-BTC_USDT")["kind"], "perpetual")
        bad = {"instrument": dict(good["instrument"], kind="spot")}
        self.client._get = lambda *a, **k: bad
        with self.assertRaises(perps.PerpsDataError):
            self.client.instrument("B-BTC_USDT")

    def test_current_ticker_parses_mark_and_funding(self):
        self.client._get = lambda *a, **k: {
            "ts": 123, "prices": {"B-BTC_USDT": {
                "ls": "100", "mp": "99.9", "fr": "0.0001",
                "efr": "0.0002", "v": "1000",
            }}
        }
        result = self.client.ticker_for("B-BTC_USDT")
        self.assertEqual(result["mp"], Decimal("99.9"))
        self.assertEqual(result["fr"], Decimal("0.0001"))
        self.assertEqual(result["timestamp"], 123)

    def test_candles_use_futures_resolution_and_validate_ohlc(self):
        captured = {}
        def fake_get(base, path, params=None):
            captured.update(params)
            return [{"time": 60000, "open": "10", "high": "12",
                     "low": "9", "close": "11", "volume": "4"}]
        self.client._get = fake_get
        rows = self.client.candles("B-BTC_USDT", "5m", 60, 360)
        self.assertEqual(captured["resolution"], "5")
        self.assertEqual(captured["pcode"], "f")
        self.assertEqual(rows[0]["close"], Decimal("11"))

    def test_candle_rejects_invalid_ohlc(self):
        self.client._get = lambda *a, **k: [
            {"time": 1, "open": "10", "high": "9", "low": "8",
             "close": "10", "volume": "1"}
        ]
        with self.assertRaises(perps.PerpsDataError):
            self.client.candles("B-BTC_USDT", "1m", 1, 60)

    def test_orderbook_depth_and_shape(self):
        self.client._get = lambda *a, **k: {"bids": {"99": "2"}, "asks": {"101": "3"}}
        self.assertIn("bids", self.client.orderbook("B-BTC_USDT", 20))
        with self.assertRaises(ValueError):
            self.client.orderbook("B-BTC_USDT", 15)

    def test_funding_snapshot_does_not_invent_open_interest(self):
        result = self.client.funding_snapshot(
            {"fr": Decimal("0.001"), "efr": Decimal("0.002"),
             "mp": Decimal("100"), "ls": Decimal("101")},
            {"funding_frequency": 8},
        )
        self.assertEqual(result["funding_frequency_hours"], 8)
        self.assertNotIn("open_interest", result)


if __name__ == "__main__":
    unittest.main()
