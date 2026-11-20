"""Offline tests for the bounded SMARD historical residual-load preflight."""

from datetime import date, datetime, timedelta, timezone
import unittest
from unittest.mock import patch

from pilot.smard_actuals_preflight import (
    ACTUAL_RESIDUAL_FILTER,
    PilotUnavailable,
    fetch_observed_residual,
    get_actuals_json,
    observed_history_report,
    required_actual_hours,
)

DAY = date(2026, 11, 21)
PACKAGE_A = datetime(2026, 11, 8, 23, tzinfo=timezone.utc)
PACKAGE_B = datetime(2026, 11, 15, 23, tzinfo=timezone.utc)
PACKAGES = [int(PACKAGE_A.timestamp() * 1000), int(PACKAGE_B.timestamp() * 1000)]


def preview(day=DAY):
    return {
        "status": "RESEARCH_PREVIEW_ONLY",
        "delivery_date": day.isoformat(),
        "source_vintage_verified": False,
        "model_inference": "NOT_AVAILABLE",
        "ensemble_forecast": None,
        "public_release_authorized": False,
    }


def stub(missing=None, duplicate=None, corrupt=None, negative=False):
    lag_map = required_actual_hours(DAY)
    wanted = set().union(*(set(values) for values in lag_map.values()))
    rows = []
    for hour in sorted(wanted):
        value = -123.45 if negative and hour == min(wanted) else 18000.0
        if missing is not None and hour == missing:
            continue
        if corrupt is not None and hour == corrupt:
            value = None
        rows.append([int(hour.timestamp() * 1000), value])
    if duplicate is not None:
        rows.append([int(duplicate.timestamp() * 1000), 45678.0])

    def get_json(path):
        if path == f"/{ACTUAL_RESIDUAL_FILTER}/DE/index_hour.json":
            return {"timestamps": PACKAGES}
        for i, package in enumerate(PACKAGES):
            filename = (
                f"/{ACTUAL_RESIDUAL_FILTER}/DE/"
                f"{ACTUAL_RESIDUAL_FILTER}_DE_hour_{package}.json"
            )
            if path == filename:
                start = datetime.fromtimestamp(package / 1000, timezone.utc)
                end = datetime.fromtimestamp(PACKAGES[i + 1] / 1000, timezone.utc) if i + 1 < len(PACKAGES) else datetime(2026, 11, 23, tzinfo=timezone.utc)
                return {
                    "series": [
                        row for row in rows
                        if start <= datetime.fromtimestamp(row[0] / 1000, timezone.utc) < end
                    ]
                }
        raise AssertionError(f"unexpected SMARD request: {path}")
    return get_json


class ObservedHistoryTests(unittest.TestCase):
    def test_exact_original_lag_and_cutoff_hour_counts(self):
        hours = required_actual_hours(DAY)
        self.assertEqual(len(hours["rl_lag_48h"]), 24)
        self.assertEqual(len(hours["rl_lag_168h"]), 24)
        self.assertEqual(len(hours["rl_last_available"]), 1)
        self.assertEqual(len(set().union(*(set(x) for x in hours.values()))), 49)
        self.assertEqual(
            hours["rl_last_available"][0].isoformat(),
            "2026-11-20T14:00:00+00:00",
        )

    def test_current_snapshot_coverage_never_claims_historical_eligibility(self):
        report = observed_history_report(preview(), stub())
        self.assertEqual(report["required_unique_actual_hours"], 49)
        self.assertEqual(report["input_coverage"], {
            "rl_lag_48h": 24,
            "rl_lag_168h": 24,
            "rl_last_available": 1,
        })
        self.assertEqual(report["status"], "HISTORICAL_ACTUALS_CURRENT_SNAPSHOT_ONLY")
        self.assertFalse(report["actuals_as_of_cutoff_verified"])
        self.assertFalse(report["source_vintage_verified"])
        self.assertFalse(report["safe_to_publish"])
        self.assertFalse(report["fitted_estimator_available"])
        self.assertIsNone(report["ridge_predictions"])
        self.assertIsNone(report["ensemble_predictions"])

    def test_negative_residual_is_acceptable(self):
        report = observed_history_report(preview(), stub(negative=True))
        self.assertEqual(report["required_unique_actual_hours"], 49)

    def test_missing_history_hour_fails(self):
        first = required_actual_hours(DAY)["rl_lag_168h"][0]
        with self.assertRaisesRegex(PilotUnavailable, "missing 1 required"):
            observed_history_report(preview(), stub(missing=first))

    def test_duplicate_history_hour_fails(self):
        first = required_actual_hours(DAY)["rl_lag_48h"][0]
        with self.assertRaisesRegex(PilotUnavailable, "duplicate"):
            observed_history_report(preview(), stub(duplicate=first))

    def test_null_history_hour_fails(self):
        first = required_actual_hours(DAY)["rl_lag_48h"][0]
        with self.assertRaisesRegex(PilotUnavailable, "invalid observed"):
            observed_history_report(preview(), stub(corrupt=first))

    def test_bad_preview_contract_is_not_used_to_fetch_actuals(self):
        for field, value in (
            ("status", "HISTORICAL_COMPONENT_PREVIEW_ONLY"),
            ("source_vintage_verified", True),
            ("model_inference", "READY"),
            ("ensemble_forecast", [1]),
            ("public_release_authorized", True),
        ):
            with self.subTest(field=field):
                data = preview()
                data[field] = value
                with self.assertRaisesRegex(PilotUnavailable, "untrusted"):
                    observed_history_report(data, lambda _: self.fail("HTTP should not be called"))

    def test_dst_boundary_is_not_assumed_equivalent_to_original_local_index(self):
        for day in (date(2027, 3, 28), date(2027, 10, 31), date(2027, 3, 30)):
            with self.subTest(day=day):
                with self.assertRaisesRegex(PilotUnavailable, "DST"):
                    required_actual_hours(day)

    def test_only_observed_residual_load_endpoint_allowed(self):
        for path in (
            "/411/DE/index_hour.json",
            "/4359/DE/../../fake.json",
            "https://evil.example/index_hour.json",
            "/4359/DE/index_hour.json?anything=true",
        ):
            with self.subTest(path=path):
                with self.assertRaisesRegex(PilotUnavailable, "not allowlisted"):
                    get_actuals_json(path)


if __name__ == "__main__":
    unittest.main()
