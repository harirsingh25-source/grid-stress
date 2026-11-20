"""Offline no-network tests for original Ridge 13-feature current API preview."""

import json
import math
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from pilot.ridge_feature_snapshot import (
    FILTERS, EXPECTED_FEATURES, PilotUnavailable,
    current_feature_snapshot, easter_sunday, fetch_exact_hours,
    fetch_json, nationwide_holiday,
)
from pilot.smard_daily_pilot import daily_hours_utc

DAY = date(2026, 11, 21)
INDEX_BASE = datetime(2025, 12, 28, 23, tzinfo=timezone.utc)
WEEKS = [int((INDEX_BASE + timedelta(days=7 * n)).timestamp() * 1000) for n in range(56)]
VALUE = {
    FILTERS["residual"]: 15000.0,
    FILTERS["grid_actual"]: 53000.0,
    FILTERS["wind_off_actual"]: 10000.0,
    FILTERS["wind_on_actual"]: 6000.0,
    FILTERS["solar_actual"]: 2000.0,
    FILTERS["grid_forecast"]: 53500.0,
    FILTERS["wind_solar_forecast"]: 19100.0,
    FILTERS["wind_off_capacity"]: 30000.0,
    FILTERS["wind_on_capacity"]: 60000.0,
    FILTERS["solar_capacity"]: 80000.0,
}


def fake_preview(day=DAY):
    return {
        "status": "RESEARCH_PREVIEW_ONLY",
        "delivery_date": day.isoformat(),
        "source_vintage_verified": False,
        "model_inference": "NOT_AVAILABLE",
        "ensemble_forecast": None,
        "public_release_authorized": False,
        "hours": [
            {
                "hour_start_utc": h.isoformat(),
                "hour_start_europe_berlin": h.isoformat(),
                "forecast_load_mwh": 55000.0,
                "forecast_wind_solar_mwh": 15000.0,
            }
            for h in daily_hours_utc(day)
        ],
    }


def fake_smard_json(*, missing=None, duplicate=None, bad=None, changed_capacity=False, neg_residual=False):
    def get_json(path):
        fields = path.strip("/").split("/")
        filter_id = int(fields[0])
        if fields[1] != "DE":
            raise AssertionError("Wrong region")
        if fields[2] == "index_hour.json":
            return {"timestamps": WEEKS}
        package = int(fields[2].removesuffix(".json").rsplit("_", 1)[1])
        if package not in WEEKS:
            raise AssertionError(f"Unknown week package {package}")
        rows = []
        for offset in range(7 * 24):
            hour = datetime.fromtimestamp(package / 1000, timezone.utc) + timedelta(hours=offset)
            if missing is not None and (filter_id, hour) == missing:
                continue
            value = VALUE[filter_id]
            if neg_residual and filter_id == FILTERS["residual"]:
                value = -250.0
            if bad is not None and (filter_id, hour) == bad:
                value = None
            if changed_capacity and filter_id == FILTERS["solar_capacity"] and hour.year == 2026 and hour.month >= 10:
                value = 90000.0
            rows.append([int(hour.timestamp() * 1000), value])
        if duplicate is not None:
            fid, hour = duplicate
            if fid == filter_id and package <= int(hour.timestamp() * 1000) < package + 7 * 24 * 3600 * 1000:
                rows.append([int(hour.timestamp() * 1000), VALUE[filter_id]])
        return {"series": rows}
    return get_json


class RidgeFullFeatureTests(unittest.TestCase):
    def test_complete_non_dsts_day_is_13_column_unverified_not_predicted(self):
        result = current_feature_snapshot(fake_preview(), fake_smard_json())
        self.assertEqual(result["status"], "RIDGE_13_FEATURES_CURRENT_SNAPSHOT_UNVERIFIED")
        self.assertEqual(result["original_alpha"], 0.01)
        self.assertEqual(result["feature_count"], 13)
        self.assertEqual(result["hour_count"], 24)
        self.assertEqual(result["recent_error_hours"], 24)
        self.assertEqual(len(result["feature_rows"]), 24)
        self.assertEqual(tuple(result["feature_rows"][0])[1:], EXPECTED_FEATURES)
        for row in result["feature_rows"]:
            self.assertEqual(row["hour_start_utc"][:10], "2026-11-20" if row["hour"] == 0 else row["hour_start_utc"][:10])
            self.assertEqual(row["is_weekend"], 1)
            self.assertEqual(row["holiday"], 0)
            self.assertEqual(row["rl_lag_48h"], 15000)
            self.assertEqual(row["rl_lag_168h"], 15000)
            self.assertEqual(row["rl_last_available"], 15000)
            self.assertEqual(row["err_grid_load_recent"], 500)
            self.assertEqual(row["err_renewables_recent"], 1100)
            self.assertEqual(row["cap_total"], 170000)
        self.assertIsNone(result["ridge_predictions"])
        self.assertIsNone(result["ensemble_predictions"])
        self.assertFalse(result["safe_to_publish"])
        self.assertFalse(result["forecast_issue_vintage_verified"])
        self.assertFalse(result["historical_actuals_as_of_cutoff_verified"])
        self.assertFalse(result["capacity_publication_vintage_verified"])
        self.assertFalse(result["holiday_calendar_equivalence_verified"])

    def test_negative_observed_residual_allowed(self):
        result = current_feature_snapshot(fake_preview(), fake_smard_json(neg_residual=True))
        self.assertEqual(result["feature_rows"][0]["rl_lag_48h"], -250)

    def test_missing_smard_hour_rejected(self):
        hour = daily_hours_utc(date(2026, 11, 19))[0]
        with self.assertRaisesRegex(PilotUnavailable, "missing"):
            current_feature_snapshot(
                fake_preview(),
                fake_smard_json(missing=(FILTERS["residual"], hour)),
            )

    def test_null_or_duplicate_source_hours_rejected(self):
        hour = daily_hours_utc(date(2026, 11, 19))[0]
        with self.assertRaisesRegex(PilotUnavailable, "invalid"):
            current_feature_snapshot(
                fake_preview(),
                fake_smard_json(bad=(FILTERS["residual"], hour)),
            )
        with self.assertRaisesRegex(PilotUnavailable, "duplicate"):
            current_feature_snapshot(
                fake_preview(),
                fake_smard_json(duplicate=(FILTERS["residual"], hour)),
            )

    def test_year_capacity_change_rejected(self):
        with self.assertRaisesRegex(PilotUnavailable, "capacity series changed"):
            current_feature_snapshot(fake_preview(), fake_smard_json(changed_capacity=True))

    def test_future_or_historical_misleading_preview_rejected(self):
        for field, value in [
            ("status", "HISTORICAL_COMPONENT_PREVIEW_ONLY"),
            ("source_vintage_verified", True),
            ("model_inference", "TRAINED_RIDGE"),
            ("ensemble_forecast", [1]),
            ("public_release_authorized", True),
        ]:
            with self.subTest(field=field):
                preview = fake_preview()
                preview[field] = value
                with self.assertRaises(PilotUnavailable):
                    current_feature_snapshot(preview, lambda _: self.fail("must not fetch"))

    def test_dst_target_and_history_days_rejected(self):
        for day in [date(2027, 3, 28), date(2027, 10, 31), date(2027, 3, 30)]:
            with self.subTest(day=day), self.assertRaisesRegex(PilotUnavailable, "DST"):
                current_feature_snapshot(fake_preview(day), lambda _: self.fail("must not fetch"))

    def test_yearly_nationwide_holiday_calendar_basics(self):
        self.assertEqual(easter_sunday(2026), date(2026, 4, 5))
        self.assertEqual(easter_sunday(2027), date(2027, 3, 28))
        for d in [date(2026, 1, 1), date(2026, 4, 3), date(2026, 4, 6),
                  date(2026, 5, 1), date(2026, 5, 14), date(2026, 5, 25),
                  date(2026, 10, 3), date(2026, 12, 25), date(2026, 12, 26)]:
            with self.subTest(day=d):
                self.assertTrue(nationwide_holiday(d))
        for d in [date(2026, 11, 21), date(2026, 5, 15)]:
            self.assertFalse(nationwide_holiday(d))

    def test_smard_allowlist_refuses_arbitrary_sources(self):
        for bad in ["/4359/DE/../index_hour.json", "/4359/DE/index_hour.json?a=1",
                    "/999/DE/index_hour.json", "/4359/XX/index_hour.json",
                    "https://evil.example/4359/DE/index_hour.json",
                    "/4359/DE/411_DE_hour_1780000000000.json"]:
            with self.subTest(path=bad), self.assertRaisesRegex(PilotUnavailable, "allowlisted|filter mismatch"):
                fetch_json(bad)

    def test_model_artifacts_never_loaded(self):
        source = (Path(__file__).resolve().parents[1] / "pilot/ridge_feature_snapshot.py").read_text()
        self.assertNotIn("joblib.load(", source)
        self.assertNotIn("pickle.load(", source)
        self.assertNotIn("Ridge(", source)
        self.assertIn('"safe_to_publish": False', source)


if __name__ == "__main__":
    unittest.main()
