import os
import tempfile
import unittest
from decimal import Decimal
from _load import load

engine = load("trader-scanner/crypto", "perps_paper")


class PerpsPaperTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.bot = engine.PerpsPaperTrader(
            starting_balance="1000", fee_rate="0.001", slippage_rate="0.001",
            daily_loss_limit="50", max_leverage="10", max_margin_fraction="0.5",
            journal_path=os.path.join(self.tmp.name, "journal.jsonl"))

    def tearDown(self):
        self.tmp.cleanup()

    def open(self, side="LONG", signal="open-1"):
        return self.bot.open_position("B-BTC_USDT", side, "100", "1", "5",
            signal, quantity_step="0.001", min_quantity="0.001",
            timestamp_ms=1800000000000)

    def test_long_short_and_margin(self):
        result = self.open()
        self.assertEqual(result["side"], "LONG")
        self.assertEqual(result["initial_margin"], Decimal("20.020020"))
        self.bot.close_position("B-BTC_USDT", "100", "close-1", 1800000000001)
        self.assertEqual(self.open("SHORT", "open-2")["side"], "SHORT")

    def test_marks_create_signed_unrealized_pnl(self):
        self.open()
        self.bot.update_marks({"B-BTC_USDT": "110"}, 1800000000000)
        self.assertGreater(self.bot.status(1800000000000)["unrealized_pnl"], 0)
        self.bot.close_position("B-BTC_USDT", "110", "close-1", 1800000000001)
        self.open("SHORT", "open-2")
        self.bot.update_marks({"B-BTC_USDT": "110"}, 1800000000002)
        self.assertLess(self.bot.status(1800000000002)["unrealized_pnl"], 0)

    def test_leverage_and_margin_fraction_limits(self):
        with self.assertRaises(engine.PaperPerpsError):
            self.bot.open_position("B-BTC_USDT", "LONG", "100", "1", "11", "x")
        with self.assertRaises(engine.PaperPerpsError):
            self.bot.open_position("B-BTC_USDT", "LONG", "1000", "1", "1", "y")

    def test_duplicate_signal_and_one_way_guard(self):
        self.open()
        with self.assertRaises(engine.PaperPerpsError):
            self.open(signal="open-1")
        with self.assertRaises(engine.PaperPerpsError):
            self.open("SHORT", "reverse")

    def test_funding_long_pays_short_receives_and_deduplicates(self):
        self.open()
        paid = self.bot.apply_funding("B-BTC_USDT", "0.001", "fund-1", "100")
        self.assertLess(paid["funding_payment"], 0)
        with self.assertRaises(engine.PaperPerpsError):
            self.bot.apply_funding("B-BTC_USDT", "0.001", "fund-1", "100")
        self.bot.close_position("B-BTC_USDT", "100", "close-1", 1800000000001)
        self.open("SHORT", "open-2")
        got = self.bot.apply_funding("B-BTC_USDT", "0.001", "fund-2", "100")
        self.assertGreater(got["funding_payment"], 0)

    def test_close_realizes_pnl_and_fees(self):
        self.open()
        result = self.bot.close_position("B-BTC_USDT", "110", "close-1", 1800000000001)
        self.assertGreater(result["net_pnl"], 0)
        self.assertNotIn("B-BTC_USDT", self.bot.status()["positions"])

    def test_contract_symbol_direction_and_quantity_validation(self):
        with self.assertRaises(engine.PaperPerpsError):
            self.bot.open_position("BTCUSDT", "LONG", "100", "1", "2", "bad")
        with self.assertRaises(engine.PaperPerpsError):
            self.bot.open_position("B-BTC_USDT", "BUY", "100", "1", "2", "bad2")
        r = self.bot.open_position("B-BTC_USDT", "LONG", "100", "0.0019",
            "2", "step", quantity_step="0.001", min_quantity="0.001")
        self.assertEqual(r["quantity"], Decimal("0.001"))

    def test_restart_recovers_position_and_signal_ids(self):
        self.open()
        restored = engine.PerpsPaperTrader(starting_balance="1000",
            journal_path=self.bot.journal_path)
        self.assertIn("B-BTC_USDT", restored.status()["positions"])
        with self.assertRaises(engine.PaperPerpsError):
            restored.open_position("B-ETH_USDT", "LONG", "100", "1", "2", "open-1")

    def test_liquidation_is_explicitly_approximate_and_paper_only(self):
        r = self.open()
        self.assertGreater(r["estimated_liquidation_price"], 0)
        self.assertIn("Simplified", r["liquidation_estimate_note"])
        self.assertFalse(self.bot.status()["live_trading_enabled"])
        self.assertEqual(self.bot.status()["mode"], "PAPER")


if __name__ == "__main__":
    unittest.main()
