import unittest
from decimal import Decimal
from _load import load

crypto = load("trader-scanner/crypto", "coindcx")
paper = load("trader-scanner/crypto", "paper_trader")


def candle(timestamp, open_, high, low, close, volume):
    return {
        "time": timestamp,
        "open": Decimal(str(open_)),
        "high": Decimal(str(high)),
        "low": Decimal(str(low)),
        "close": Decimal(str(close)),
        "volume": Decimal(str(volume)),
    }


class AggregateCandles(unittest.TestCase):
    def setUp(self):
        self.start = 1793325900000
        self.rows = [
            candle(self.start + i * 60000, 100+i, 105+i, 98+i,
                   103+i, 2)
            for i in range(5)
        ]

    def test_complete_five_minute_candle(self):
        result = crypto.aggregate_candles(self.rows)
        self.assertEqual(len(result), 1)
        item = result[0]
        self.assertEqual(item["time"], self.start)
        self.assertEqual(item["open"], Decimal("100"))
        self.assertEqual(item["high"], Decimal("109"))
        self.assertEqual(item["low"], Decimal("98"))
        self.assertEqual(item["close"], Decimal("107"))
        self.assertEqual(item["volume"], Decimal("10"))

    def test_missing_minute_is_discarded(self):
        result = crypto.aggregate_candles(self.rows[:2] + self.rows[3:])
        self.assertEqual(result, [])

    def test_duplicate_minute_is_discarded(self):
        result = crypto.aggregate_candles(self.rows + [self.rows[0]])
        self.assertEqual(result, [])

    def test_invalid_minutes(self):
        with self.assertRaises(ValueError):
            crypto.aggregate_candles(self.rows, minutes=1)




class ValidateCandles(unittest.TestCase):
    def setUp(self):
        self.interval = 60_000
        self.start = 1_800_000_000_000
        self.rows = [
            candle(self.start + i * self.interval, 100, 105, 95, 102, 10)
            for i in range(3)
        ]
        self.now = self.start + 3 * self.interval

    def test_valid_fresh_series(self):
        result = crypto.validate_candles(
            self.rows, self.interval, self.now
        )
        self.assertEqual(len(result), 3)

    def test_rejects_stale_series(self):
        with self.assertRaises(crypto.CoinDCXError):
            crypto.validate_candles(
                self.rows, self.interval,
                self.now + 5 * self.interval
            )

    def test_rejects_incomplete_latest_candle(self):
        with self.assertRaises(crypto.CoinDCXError):
            crypto.validate_candles(
                self.rows, self.interval, self.now - 1
            )

    def test_rejects_missing_interval(self):
        with self.assertRaises(crypto.CoinDCXError):
            crypto.validate_candles(
                [self.rows[0], self.rows[2]],
                self.interval, self.now
            )

    def test_rejects_invalid_ohlc(self):
        bad = list(self.rows)
        bad[1] = candle(
            self.start + self.interval, 100, 101, 99, 110, 10
        )
        with self.assertRaises(crypto.CoinDCXError):
            crypto.validate_candles(bad, self.interval, self.now)

    def test_rejects_negative_volume(self):
        bad = list(self.rows)
        bad[1] = candle(
            self.start + self.interval, 100, 105, 95, 102, -1
        )
        with self.assertRaises(crypto.CoinDCXError):
            crypto.validate_candles(bad, self.interval, self.now)


class MockedClient(unittest.TestCase):
    def setUp(self):
        self.client = crypto.CoinDCXClient()

    def test_ticker_lookup(self):
        self.client._get = lambda path, params=None: [
            {"market": "BTCUSDT", "last_price": "100"},
            {"market": "ETHUSDT", "last_price": "50"},
        ]
        self.assertEqual(
            self.client.ticker_for("B-BTC_USDT")["last_price"], "100"
        )

    def test_missing_ticker(self):
        self.client._get = lambda path, params=None: []
        with self.assertRaises(crypto.CoinDCXError):
            self.client.ticker_for("B-BTC_USDT")

    def test_rejects_unsupported_interval_without_network(self):
        self.client._get = lambda *args, **kwargs: self.fail("Network called")
        with self.assertRaises(ValueError):
            self.client.candles("B-BTC_USDT", "5m", limit=5)

    def test_rejects_invalid_pair(self):
        self.client._get = lambda *args, **kwargs: self.fail("Network called")
        with self.assertRaises(ValueError):
            self.client.orderbook("BTCUSDT")

    def test_orderbook_shape(self):
        expected = {"bids": {"100": "2"}, "asks": {"101": "3"}}
        self.client._get = lambda path, params=None: expected
        self.assertEqual(self.client.orderbook("B-BTC_USDT"), expected)




class ValidatedClientPipeline(unittest.TestCase):
    def setUp(self):
        self.client = crypto.CoinDCXClient()
        self.start = 1_800_000_000_000
        self.interval = 60_000
        self.rows = [
            candle(self.start + i * self.interval, 100, 105, 95, 102, 10)
            for i in range(3)
        ]

    def test_validated_candles_returns_only_valid_data(self):
        self.client.candles = lambda *args, **kwargs: self.rows
        result = self.client.validated_candles(
            "B-BTC_USDT", "1m",
            now_ms=self.start + 3 * self.interval
        )
        self.assertEqual(len(result), 3)

    def test_validated_pipeline_rejects_stale_data(self):
        self.client.candles = lambda *args, **kwargs: self.rows
        with self.assertRaises(crypto.CoinDCXError):
            self.client.validated_candles(
                "B-BTC_USDT", "1m",
                now_ms=self.start + 8 * self.interval
            )

    def test_validated_pipeline_rejects_unsupported_interval(self):
        self.client.candles = lambda *args, **kwargs: self.fail(
            "Unsupported interval reached API"
        )
        with self.assertRaises(ValueError):
            self.client.validated_candles(
                "B-BTC_USDT", "5m",
                now_ms=self.start + 3 * self.interval
            )




class PaperTraderTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.temp = tempfile.TemporaryDirectory()
        self.journal = self.temp.name + "/paper.jsonl"
        self.trader = paper.PaperTrader(
            starting_cash="1000",
            fee_rate="0.001",
            slippage_rate="0.01",
            qty_step="0.001",
            min_qty="0.001",
            daily_loss_limit="10",
            journal_path=self.journal,
        )
        self.day = 1_800_000_000_000

    def tearDown(self):
        self.temp.cleanup()

    def test_buy_applies_fee_and_slippage(self):
        result = self.trader.buy(
            "BTCUSDT", "100", "1", "buy-1", self.day
        )
        self.assertEqual(result["fill_price"], Decimal("101"))
        self.assertEqual(result["fee"], Decimal("0.101"))
        self.assertEqual(self.trader.cash, Decimal("898.899"))

    def test_sell_calculates_realized_pnl(self):
        self.trader.buy("BTCUSDT", "100", "1", "buy-1", self.day)
        result = self.trader.sell(
            "BTCUSDT", "110", "1", "sell-1", self.day
        )
        self.assertGreater(result["realized_pnl"], 0)
        self.assertNotIn("BTCUSDT", self.trader.positions)

    def test_duplicate_signal_rejected(self):
        self.trader.buy("BTCUSDT", "100", "1", "same", self.day)
        with self.assertRaises(paper.PaperTradeError):
            self.trader.buy("BTCUSDT", "100", "1", "same", self.day)

    def test_quantity_rounded_down(self):
        result = self.trader.buy(
            "BTCUSDT", "10", "1.23456", "buy-1", self.day
        )
        self.assertEqual(result["quantity"], Decimal("1.234"))

    def test_insufficient_cash_rejected(self):
        with self.assertRaises(paper.PaperTradeError):
            self.trader.buy("BTCUSDT", "2000", "1", "buy-1", self.day)

    def test_daily_loss_blocks_new_entries(self):
        self.trader.buy("BTCUSDT", "100", "1", "buy-1", self.day)
        self.trader.sell("BTCUSDT", "80", "1", "sell-1", self.day)
        with self.assertRaises(paper.PaperTradeError):
            self.trader.buy("BTCUSDT", "50", "1", "buy-2", self.day)

    def test_journal_restores_state_and_duplicate_guard(self):
        self.trader.buy("BTCUSDT", "100", "1", "buy-1", self.day)
        restored = paper.PaperTrader(
            starting_cash="1000",
            fee_rate="0.001",
            slippage_rate="0.01",
            qty_step="0.001",
            min_qty="0.001",
            daily_loss_limit="10",
            journal_path=self.journal,
        )
        self.assertEqual(restored.cash, self.trader.cash)
        self.assertEqual(
            restored.positions["BTCUSDT"]["qty"], Decimal("1")
        )
        with self.assertRaises(paper.PaperTradeError):
            restored.buy("BTCUSDT", "100", "1", "buy-1", self.day)

    def test_sell_cannot_exceed_position(self):
        with self.assertRaises(paper.PaperTradeError):
            self.trader.sell("BTCUSDT", "100", "1", "sell-1", self.day)


if __name__ == "__main__":
    unittest.main()
