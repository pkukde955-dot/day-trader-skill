import unittest
from decimal import Decimal
from _load import load

strategy=load("trader-perps","strategy")

class PerpsStrategyTests(unittest.TestCase):
    def test_invalid_zero_or_negative_inputs_fail_closed(self):
        for args in [
            ("0","100","90","0.01","0.001","0.001","2","2"),
            ("1000","100","100","0.01","0.001","0.001","2","2"),
            ("1000","100","90","-0.01","0.001","0.001","2","2"),
            ("1000","100","90","0.01","0","0.001","2","2"),
            ("1000","100","90","0.01","0.001","0.001","3","2"),
        ]:
            self.assertEqual(strategy.size_for_risk(*args),Decimal("0"))

    def test_risk_and_margin_caps(self):
        q=strategy.size_for_risk("1000","100","90","0.01","0.001","0.001","2","2")
        self.assertGreater(q,0)
        self.assertLessEqual(q*Decimal("10"),Decimal("10"))
        self.assertLessEqual(q*Decimal("100")/Decimal("2"),Decimal("200"))

    def test_oversized_risk_is_blocked(self):
        self.assertEqual(strategy.size_for_risk("1000","100","90","0.03","0.001","0.001","2","2"),Decimal("0"))

    def test_invalid_candle_history_returns_no_signal(self):
        self.assertEqual(strategy.detect_setup([],[],100)["signal"],"NONE")
