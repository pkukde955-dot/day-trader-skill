import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DASHBOARD = ROOT / "trader-scanner" / "india_fno" / "dashboard"
HTML = DASHBOARD / "index.html"
STRATEGY = DASHBOARD / "strategy.js"
SERVER = DASHBOARD / "server.py"
LAUNCHER = ROOT / "trader-scanner" / "india_fno" / "start_dashboard.sh"


class IndiaFnoDashboardTests(unittest.TestCase):
    def test_dashboard_assets_exist(self):
        self.assertTrue(HTML.is_file())
        self.assertTrue(STRATEGY.is_file())
        self.assertTrue(SERVER.is_file())
        self.assertTrue(LAUNCHER.is_file())

    def test_dashboard_is_manual_only_and_documents_no_orders(self):
        page = HTML.read_text(encoding="utf-8")
        self.assertIn("Manual trading only", page)
        self.assertIn("No broker connection", page)
        self.assertIn("No orders", page)
        self.assertIn('id="candles"', page)

    def test_stale_data_is_rejected_before_signal(self):
        page = HTML.read_text(encoding="utf-8")
        strategy = STRATEGY.read_text(encoding="utf-8")
        self.assertIn('window.IndiaFnoStrategy.analyse', page)
        self.assertIn('var maxAge = interval * 2', strategy)
        self.assertIn('if (!base.fresh)', strategy)
        self.assertIn('signal: "NO SIGNAL"', strategy)
        self.assertIn('ageMin >= 0 && ageMin <= maxAge', strategy)
        self.assertIn('Future timestamp rejected', strategy)

    def test_candles_are_partitioned_by_symbol_exchange_and_interval(self):
        page = HTML.read_text(encoding="utf-8")
        self.assertIn('[c.symbol,c.exchange,c.interval].join("|")', page)
        self.assertIn('c.symbol+"|"+c.exchange+"|"+c.interval+"|"+c.ms', page)

    def test_invalid_intervals_and_negative_volume_are_rejected(self):
        page = HTML.read_text(encoding="utf-8")
        self.assertIn("if(!m)return NaN", page)
        self.assertIn("!Number.isFinite(c.interval)", page)
        self.assertIn("c.volume<0", page)

    def test_server_binds_to_loopback_only(self):
        server = SERVER.read_text(encoding="utf-8")
        self.assertIn('HOST = "127.0.0.1"', server)
        self.assertIn("ThreadingHTTPServer((HOST, PORT)", server)

    def test_no_exchange_scraper_or_broker_order_endpoint(self):
        page = HTML.read_text(encoding="utf-8").lower()
        server = SERVER.read_text(encoding="utf-8").lower()
        self.assertNotIn("fetch(", page)
        self.assertNotIn("placeorder", page)
        self.assertNotIn("api key", server)


if __name__ == "__main__":
    unittest.main()
