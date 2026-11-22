"""Offline, deterministic checks for the original GridStress Ridge readiness gate."""

import json
import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from pilot.ridge_readiness import (
    AVAILABLE_FEATURES,
    EXPECTED_FEATURES,
    ORIGINAL_RIDGE_CONFIG,
    PilotUnavailable,
    load_original_contract,
    readiness_report,
)
from pilot.smard_daily_pilot import daily_hours_utc


def snapshot(day: date) -> dict:
    hours = daily_hours_utc(day)
    return {
        "status": "RESEARCH_PREVIEW_ONLY",
        "delivery_date": day.isoformat(),
        "source_vintage_verified": False,
        "model_inference": "NOT_AVAILABLE",
        "ensemble_forecast": None,
        "public_release_authorized": False,
        "hours": [
            {
                "hour_start_utc": hour.isoformat(),
                "hour_start_europe_berlin": hour.isoformat(),
                "forecast_load_mwh": 55000.0,
                "forecast_wind_solar_mwh": 25000.0,
            }
            for hour in hours
        ],
    }


class RidgeReadinessTests(unittest.TestCase):
    def test_contract_matches_saved_original_ridge_config(self):
        self.assertTrue(ORIGINAL_RIDGE_CONFIG.is_file())
        model = load_original_contract()
        self.assertEqual(model["model"], "linear_direct")
        self.assertEqual(model["selected_alpha"], 0.01)
        self.assertEqual(tuple(model["features"]), EXPECTED_FEATURES)

    def test_six_available_seven_missing_and_no_false_prediction(self):
        report = readiness_report(snapshot(date(2026, 11, 21)))
        self.assertEqual(report["status"], "RIDGE_FEATURES_INCOMPLETE")
        self.assertEqual(report["feature_total"], 13)
        self.assertEqual(report["available_feature_names"], list(AVAILABLE_FEATURES))
        self.assertEqual(len(report["unavailable_features"]), 7)
        self.assertEqual(len({x["feature"] for x in report["unavailable_features"]}), 7)
        self.assertEqual(report["smard_target_hour_count"], 24)
        self.assertEqual(report["issue_time_europe_berlin"], "2026-11-20T18:00:00+01:00")
        self.assertEqual(report["actuals_cutoff_europe_berlin"], "2026-11-20T16:00:00+01:00")
        self.assertEqual(report["last_eligible_actual_hour_start"], "2026-11-20T15:00:00+01:00")
        self.assertIsNone(report["ridge_predictions"])
        self.assertIsNone(report["ensemble_predictions"])
        self.assertFalse(report["trained_estimator_available"])
        self.assertFalse(report["source_vintage_verified"])
        self.assertFalse(report["safe_to_publish"])

    def test_dst_target_dates_preserve_23_and_25_physical_hours(self):
        for day, expected in [(date(2027, 3, 28), 23), (date(2027, 10, 31), 25)]:
            with self.subTest(day=day):
                report = readiness_report(snapshot(day))
                self.assertEqual(report["smard_target_hour_count"], expected)
                self.assertFalse(report["safe_to_publish"])

    def test_missing_or_duplicate_hour_fails_closed(self):
        data = snapshot(date(2026, 11, 21))
        data["hours"].pop(8)
        with self.assertRaisesRegex(PilotUnavailable, "incomplete"):
            readiness_report(data)
        data = snapshot(date(2026, 11, 21))
        data["hours"][8]["hour_start_utc"] = data["hours"][7]["hour_start_utc"]
        with self.assertRaisesRegex(PilotUnavailable, "out-of-order"):
            readiness_report(data)

    def test_missing_bad_or_nonfinite_input_rejected(self):
        for bad in [None, "bad", -1, float("nan"), float("inf"), True]:
            with self.subTest(value=str(bad)):
                data = snapshot(date(2026, 11, 21))
                data["hours"][10]["forecast_load_mwh"] = bad
                with self.assertRaisesRegex(PilotUnavailable, "invalid SMARD input"):
                    readiness_report(data)

    def test_misleading_source_contract_refused(self):
        for field, value in [
            ("status", "HISTORICAL_COMPONENT_PREVIEW_ONLY"),
            ("source_vintage_verified", True),
            ("model_inference", "READY"),
            ("ensemble_forecast", [1]),
            ("public_release_authorized", True),
        ]:
            with self.subTest(field=field):
                data = snapshot(date(2026, 11, 21))
                data[field] = value
                with self.assertRaises(PilotUnavailable):
                    readiness_report(data)

    def test_config_schema_drift_fails_before_claiming_readiness(self):
        source = json.loads(ORIGINAL_RIDGE_CONFIG.read_text(encoding="utf-8"))
        source["settings"]["features"][0] = "some_new_feature"
        with tempfile.TemporaryDirectory() as folder:
            file = Path(folder) / "config.json"
            file.write_text(json.dumps(source), encoding="utf-8")
            with self.assertRaisesRegex(PilotUnavailable, "schema changed"):
                load_original_contract(file)

    def test_config_info_cutoff_drift_fails_before_claiming_readiness(self):
        source = json.loads(ORIGINAL_RIDGE_CONFIG.read_text(encoding="utf-8"))
        source["settings"]["data_info"]["actuals_lag"] = "0h"
        with tempfile.TemporaryDirectory() as folder:
            file = Path(folder) / "config.json"
            file.write_text(json.dumps(source), encoding="utf-8")
            with self.assertRaisesRegex(PilotUnavailable, "cutoff contract"):
                load_original_contract(file)


if __name__ == "__main__":
    unittest.main()
