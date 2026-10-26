import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "trader-scanner"))
from india_fno.order_intent import build_order_intent, OrderIntentError


class OrderIntentTests(unittest.TestCase):
    def build(self, **kwargs):
        base = dict(symbol="NIFTY26NOV25000CE", exchange="NSE", side="BUY",
                    entry="100", stop="90", target="130", risk_budget="1000",
                    lot_size=25)
        base.update(kwargs)
        return build_order_intent(**base)

    def test_sizes_down_to_whole_lots(self):
        result = self.build()
        self.assertEqual(result["lots"], 4)
        self.assertEqual(result["quantity"], 100)
        self.assertEqual(result["planned_risk"], "1000")
        self.assertEqual(result["planned_reward"], "3000")

    def test_sell_geometry(self):
        result = self.build(side="SELL", entry="100", stop="110", target="70")
        self.assertEqual(result["side"], "SELL")
        self.assertEqual(result["reward_risk_ratio"], "3.00")

    def test_caps_lots(self):
        self.assertEqual(self.build(max_lots=2)["lots"], 2)

    def test_refuses_budget_below_one_lot_risk(self):
        with self.assertRaises(OrderIntentError):
            self.build(risk_budget="249")

    def test_rejects_wrong_buy_geometry(self):
        with self.assertRaises(OrderIntentError):
            self.build(stop="105", target="130")

    def test_rejects_wrong_sell_geometry(self):
        with self.assertRaises(OrderIntentError):
            self.build(side="SELL", stop="90", target="70")

    def test_rejects_unknown_exchange(self):
        with self.assertRaises(OrderIntentError):
            self.build(exchange="MCX")

    def test_rejects_zero_price(self):
        with self.assertRaises(OrderIntentError):
            self.build(entry="0")

    def test_rejects_nonfinite_price(self):
        with self.assertRaises(OrderIntentError):
            self.build(entry="NaN")

    def test_does_not_claim_live_or_placed(self):
        result = self.build()
        self.assertFalse(result["market_data_verified"])
        self.assertFalse(result["broker_connected"])
        self.assertFalse(result["order_placed"])
        self.assertEqual(result["status"], "AWAITING_USER_REVIEW")


if __name__ == "__main__":
    unittest.main()
