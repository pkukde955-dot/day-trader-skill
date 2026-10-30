import unittest
from unittest.mock import patch
from decimal import Decimal
from _load import load
clientmod=load("trader-scanner/crypto","coindcx_perps")
strategy=load("trader-perps","strategy")

class ClientTests(unittest.TestCase):
    def test_ticker_rejects_stale_mark(self):
        c=clientmod.CoinDCXPerpsClient(max_age_ms=100)
        with patch.object(clientmod,"_get",return_value={"ts":1,"prices":{"B-BTC_USDT":{"mp":"100","bmST":1}}}):
            with self.assertRaises(clientmod.PerpsDataError): c.ticker_for("B-BTC_USDT")
    def test_instrument_checks_active_metadata(self):
        c=clientmod.CoinDCXPerpsClient()
        with patch.object(c,"active_instruments",return_value=["B-BTC_USDT"]), patch.object(clientmod,"_get",return_value={"instrument":{"pair":"B-BTC_USDT","kind":"perpetual","status":"active","quantity_increment":"0.001","min_trade_size":"0.001","price_increment":"0.1"}}):
            self.assertEqual(c.instrument("B-BTC_USDT")["quantity_increment"],Decimal("0.001"))
    def test_instrument_rejects_inactive(self):
        c=clientmod.CoinDCXPerpsClient()
        with patch.object(c,"active_instruments",return_value=[]):
            with self.assertRaises(clientmod.PerpsDataError): c.instrument("B-BTC_USDT")

class StrategyTests(unittest.TestCase):
    def test_sizing_caps_margin_and_risk(self):
        q=strategy.size_for_risk("1000","100","90","0.01","0.001","0.001","2","2")
        self.assertLessEqual(q*Decimal("100")/Decimal("2"),Decimal("200"))
        self.assertLessEqual(q*Decimal("10"),Decimal("10"))
    def test_sizing_blocks_excess_risk_fraction(self):
        self.assertEqual(strategy.size_for_risk("1000","100","90","0.03","0.001","0.001","2","2"),Decimal("0"))
