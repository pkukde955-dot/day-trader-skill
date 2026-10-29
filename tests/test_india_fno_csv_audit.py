import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "trader-scanner"))

from india_fno.csv_audit import audit_rows


def candle(timestamp, **overrides):
    row = {
        "timestamp": timestamp,
        "symbol": "NIFTY26OCT25000CE",
        "exchange": "NSE",
        "interval": "5m",
        "open": "110",
        "high": "116",
        "low": "105",
        "close": "113",
        "volume": "1200",
    }
    row.update(overrides)
    return row


class CsvAuditTests(unittest.TestCase):
    def test_counts_duplicate_invalid_and_intraday_gap_rows(self):
        rows = [
            candle("2026-10-26T09:15:00+05:30"),
            candle("2026-10-26T09:20:00+05:30"),
            candle("2026-10-26T09:20:00+05:30"),  # duplicate
            candle("2026-10-26T09:35:00+05:30"),  # 2 missing 5m bars
            candle("2026-10-26T09:40:00+05:30", high="100", low="105"),
        ]
        result = audit_rows(rows, min_bars=60)
        self.assertEqual(result["total_rows"], 5)
        self.assertEqual(result["valid_rows_before_dedup"], 4)
        self.assertEqual(result["invalid_rows"], 1)
        self.assertEqual(result["duplicate_rows"], 1)
        self.assertEqual(result["invalid_reason_counts"]["invalid_ohlc_geometry"], 1)
        group = result["groups"][0]
        self.assertEqual(group["unique_bars"], 3)
        self.assertEqual(group["plausible_intraday_gap_count"], 1)
        self.assertEqual(group["estimated_missing_intraday_bars"], 2)
        self.assertFalse(group["enough_bars_for_70_30_holdout"])

    def test_detects_out_of_order_and_timezone_naive_rows(self):
        rows = [
            candle("2026-10-26T09:20:00"),
            candle("2026-10-26T09:15:00+05:30"),
            candle("2026-10-26T09:25:00+05:30"),
        ]
        result = audit_rows(rows)
        self.assertEqual(result["naive_timestamp_rows"], 1)
        self.assertGreaterEqual(result["out_of_order_rows"], 1)
        self.assertEqual(result["groups"][0]["unique_bars"], 3)

    def test_rejects_nonfinite_volume_and_bad_timestamp(self):
        rows = [
            candle("not-a-time"),
            candle("2026-10-26T09:20:00+05:30", volume="inf"),
            candle("2026-10-26T09:25:00+05:30", close="nan"),
        ]
        result = audit_rows(rows)
        self.assertEqual(result["invalid_rows"], 3)
        self.assertEqual(result["groups"], [])
        self.assertEqual(result["invalid_reason_counts"]["invalid_timestamp"], 1)
        self.assertEqual(result["invalid_reason_counts"]["invalid_volume"], 1)
        self.assertEqual(result["invalid_reason_counts"]["invalid_ohlc_number"], 1)

    def test_groups_are_separated_by_symbol_exchange_and_interval(self):
        rows = [
            candle("2026-10-26T09:15:00+05:30"),
            candle("2026-10-26T09:15:00+05:30", symbol="BANKNIFTY26OCT50000CE"),
            candle("2026-10-26T09:15:00+05:30", interval="15m"),
            candle("2026-10-26T09:15:00+05:30", exchange="BSE"),
        ]
        result = audit_rows(rows)
        self.assertEqual(len(result["groups"]), 4)
        self.assertEqual(result["holdout_eligible_groups"], 0)

    def test_mixed_naive_and_aware_timestamps_do_not_crash(self):
        rows = [
            candle("2026-10-26T09:15:00"),
            candle("2026-10-26T09:20:00+05:30"),
        ]
        result = audit_rows(rows)
        self.assertEqual(result["total_rows"], 2)
        self.assertEqual(result["naive_timestamp_rows"], 1)
        self.assertEqual(result["groups"][0]["unique_bars"], 2)


if __name__ == "__main__":
    unittest.main()
