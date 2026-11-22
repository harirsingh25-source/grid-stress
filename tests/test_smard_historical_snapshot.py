"""Offline tests for the read-only SMARD historical Streamlit data layer."""

import unittest
from datetime import date, datetime, timezone
from unittest.mock import patch

from pilot.smard_daily_pilot import FILTER_LOAD, PilotUnavailable
from pilot.smard_historical_snapshot import build_historical_snapshot


def complete_stub(filter_id, hours, get_json):
    base = 50000 if filter_id == FILTER_LOAD else 17000
    return {hour: float(base + n) for n, hour in enumerate(hours)}


class HistoricalSnapshotTests(unittest.TestCase):
    def test_complete_day_retains_unverified_vintage_and_unavailable_models(self):
        with patch("pilot.smard_historical_snapshot.fetch_forecast_series", side_effect=complete_stub):
            result = build_historical_snapshot(
                date(2026, 11, 19), datetime(2026, 11, 20, tzinfo=timezone.utc)
            )
        self.assertEqual(result["status"], "HISTORICAL_COMPONENT_PREVIEW_ONLY")
        self.assertFalse(result["source_vintage_verified"])
        self.assertFalse(result["public_release_authorized"])
        self.assertEqual(result["model_inference"], "NOT_AVAILABLE")
        self.assertIsNone(result["ensemble_forecast"])
        self.assertEqual(len(result["hours"]), 24)
        self.assertEqual(result["hours"][0]["derived_component_residual_mwh"], 33000)

    def test_today_or_tomorrow_refused_before_network_access(self):
        with patch("pilot.smard_historical_snapshot.fetch_forecast_series") as fetch:
            for day in [date(2026, 11, 20), date(2026, 11, 21)]:
                with self.subTest(day=day):
                    with self.assertRaisesRegex(PilotUnavailable, "completed historical day"):
                        build_historical_snapshot(
                            day, datetime(2026, 11, 20, 16, tzinfo=timezone.utc)
                        )
            fetch.assert_not_called()

    def test_unaware_as_of_refused(self):
        with self.assertRaisesRegex(PilotUnavailable, "timezone-aware"):
            build_historical_snapshot(date(2026, 11, 19), datetime(2026, 11, 20))

    def test_different_day_lengths_on_dst_changes(self):
        with patch("pilot.smard_historical_snapshot.fetch_forecast_series", side_effect=complete_stub):
            spring = build_historical_snapshot(
                date(2027, 3, 28), datetime(2027, 3, 29, tzinfo=timezone.utc)
            )
            autumn = build_historical_snapshot(
                date(2027, 10, 31), datetime(2027, 11, 1, tzinfo=timezone.utc)
            )
        self.assertEqual(len(spring["hours"]), 23)
        self.assertEqual(len(autumn["hours"]), 25)
        self.assertEqual(len({x["hour_start_utc"] for x in autumn["hours"]}), 25)

    def test_missing_data_fails_closed(self):
        with patch("pilot.smard_historical_snapshot.fetch_forecast_series",
                   side_effect=PilotUnavailable("missing SMARD forecast hour")):
            with self.assertRaisesRegex(PilotUnavailable, "missing"):
                build_historical_snapshot(
                    date(2026, 11, 19), datetime(2026, 11, 20, tzinfo=timezone.utc)
                )


if __name__ == "__main__":
    unittest.main()
