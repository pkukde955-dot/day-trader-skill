import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DASHBOARD = ROOT / "trader-scanner" / "india_fno" / "dashboard"
HTML = DASHBOARD / "index.html"
SERVER = DASHBOARD / "server.py"
LAUNCHER = ROOT / "trader-scanner" / "india_fno" / "start_dashboard.sh"


class IndiaFnoDashboardTests(unittest.TestCase):
    def test_dashboard_assets_exist(self):
        self.assertTrue(HTML.is_file())
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
        self.assertIn("var maxAge=interval*2", page)
        self.assertIn('if(!base.fresh)', page)
        self.assertIn('base.signal="NO SIGNAL"', page)

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
