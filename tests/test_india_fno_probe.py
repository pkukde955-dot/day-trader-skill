import unittest

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
