import sys
import unittest
from pathlib import Path

# The skill folder contains a hyphen, so add it explicitly for package import.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "trader-scanner"))

from india_fno.probe import parse_chart


class ParseChartTests(unittest.TestCase):
    def test_parses_valid_chart_without_inventing_values(self):
        payload = {
            "chart": {
                "result": [{
                    "meta": {"symbol": "^NSEI", "exchangeName": "NSI", "instrumentType": "INDEX", "currency": "INR"},
                    "timestamp": [1790000000, 1790000300],
                    "indicators": {"quote": [{"close": [25000.0, None]}]},
                }],
                "error": None,
            }
        }
        result = parse_chart(payload)
        self.assertTrue(result["ok"])
        self.assertEqual(result["symbol"], "^NSEI")
        self.assertEqual(result["valid_closes"], 1)
        self.assertEqual(result["interval_bars_returned"], 2)
        self.assertEqual(result["currency"], "INR")

    def test_freshness_is_reported_deterministically(self):
        payload = {
            "chart": {"result": [{
                "meta": {"symbol": "^NSEI"},
                "timestamp": [1790000000, 1790000300],
                "indicators": {"quote": [{"close": [25000.0, 25010.0]}]},
            }], "error": None}
        }
        result = parse_chart(payload, now_epoch=1790000600)
        self.assertTrue(result["ok"])
        self.assertTrue(result["fresh"])
        self.assertEqual(result["freshness"], "FRESH")
        self.assertEqual(result["age_seconds"], 300.0)

    def test_stale_and_future_bars_are_not_marked_fresh(self):
        base = {
            "chart": {"result": [{
                "meta": {"symbol": "^NSEI"},
                "timestamp": [1790000000],
                "indicators": {"quote": [{"close": [25000.0]}]},
            }], "error": None}
        }
        stale = parse_chart(base, now_epoch=1790002000)
        future = parse_chart(base, now_epoch=1789999900)
        self.assertTrue(stale["ok"])
        self.assertFalse(stale["fresh"])
        self.assertEqual(stale["freshness"], "STALE")
        self.assertFalse(future["fresh"])
        self.assertEqual(future["freshness"], "FUTURE")

    def test_nonfinite_closes_do_not_count_as_valid(self):
        payload = {
            "chart": {"result": [{
                "meta": {"symbol": "^NSEI"},
                "timestamp": [1790000000, 1790000300, 1790000600],
                "indicators": {"quote": [{"close": [float("nan"), float("inf"), None]}]},
            }], "error": None}
        }
        result = parse_chart(payload, now_epoch=1790000600)
        self.assertFalse(result["ok"])
        self.assertFalse(result["fresh"])
        self.assertEqual(result["valid_closes"], 0)

    def test_timestamp_close_length_mismatch_is_not_fresh(self):
        payload = {
            "chart": {"result": [{
                "meta": {"symbol": "^NSEI"},
                "timestamp": [1790000000, 1790000300],
                "indicators": {"quote": [{"close": [25000.0]}]},
            }], "error": None}
        }
        result = parse_chart(payload, now_epoch=1790000600)
        self.assertTrue(result["ok"])
        self.assertFalse(result["fresh"])
        self.assertEqual(result["freshness"], "MISALIGNED")
        self.assertFalse(result["timestamp_close_series_aligned"])

    def test_empty_result_is_unavailable(self):
        self.assertFalse(parse_chart({"chart": {"result": [], "error": None}})["ok"])

    def test_api_error_is_reported(self):
        result = parse_chart({"chart": {"result": None, "error": {"code": "Not Found", "description": "No data"}}})
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "No data")

    def test_no_valid_closes_is_unavailable(self):
        payload = {
            "chart": {"result": [{
                "meta": {"symbol": "TEST.NS"},
                "timestamp": [1790000000],
                "indicators": {"quote": [{"close": [None]}]},
            }], "error": None}
        }
        result = parse_chart(payload)
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "No valid close values")


if __name__ == "__main__":
    unittest.main()
