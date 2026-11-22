"""Offline audit of original-team month fingerprint protocol; no SMARD network."""

import importlib.util
import json
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from pilot.smard_daily_pilot import LOCAL
from pilot.smard_history_fingerprint import (
    ORIGINAL_SERIES, ORIGINAL_CONFIG, PilotUnavailable,
    _fingerprint, compare_reference, fetch_one_series,
    reproduce_frames, selected_period,
)

PANDAS_AVAILABLE = importlib.util.find_spec("pandas") is not None
START = datetime(2026, 8, 31, tzinfo=timezone.utc)
END = datetime(2026, 9, 7, tzinfo=timezone.utc)
START_MS = int(START.timestamp() * 1000)
BEFORE_MS = START_MS - 7 * 24 * 3600 * 1000
END_MS = int(END.timestamp() * 1000)
VALUE = {filter_id: float(i * 1000 + 200)
         for i, (filter_id, _, _) in enumerate(ORIGINAL_SERIES, 1)}
# Model's observed/forecast residual load may have a negative value.
VALUE[4359] = -80.0
VALUE[4362] = -20.0


def fake_api(*, bad_index=False, missing=False, null_value=False, nonfinite=False):
    def fetch(path):
        words = path.strip("/").split("/")
        filter_id = int(words[0])
        if filter_id not in VALUE or words[1] != "DE":
            raise AssertionError(f"unexpected filter request: {path}")
        if words[2] == "index_hour.json":
            return {"timestamps": [BEFORE_MS, START_MS, END_MS]
                    if not bad_index else [START_MS, START_MS]}
        expected_file = f"{filter_id}_DE_hour_{START_MS}.json"
        if words[2] != expected_file:
            raise AssertionError(f"unexpected SMARD package: {path}")
        hourly = []
        hour = START
        while hour < END:
            stamp = int(hour.timestamp() * 1000)
            value = VALUE[filter_id]
            if null_value and filter_id == 4359 and hour.hour == 12:
                value = None
            if nonfinite and filter_id == 4359 and hour.hour == 12:
                value = float("inf")
            if not (missing and filter_id == 4359 and hour.hour == 12):
                hourly.append([stamp, value])
            hour += timedelta(hours=1)
        return {"series": hourly}
    return fetch


class OneMonthProbeTests(unittest.TestCase):
    def test_september_reference_window_is_six_days_only(self):
        a, b = selected_period("2026-09")
        self.assertEqual(a.isoformat(), "2026-09-01T00:00:00+02:00")
        self.assertEqual(b.isoformat(), "2026-09-07T00:00:00+02:00")
        self.assertEqual((b.astimezone(timezone.utc) - a.astimezone(timezone.utc)).total_seconds(), 144 * 3600)

    def test_bad_or_out_of_range_month_fails_without_network(self):
        for month in ["2026-10", "2018-12", "2026-13", "2026-00",
                      "2026/09", "202609", "2026-9", "", "2027-01"]:
            with self.subTest(month=month), self.assertRaises(PilotUnavailable):
                selected_period(month)

    def test_original_eleven_filters_are_in_saved_input_order(self):
        self.assertEqual(len(ORIGINAL_SERIES), 11)
        self.assertEqual([x[0] for x in ORIGINAL_SERIES],
                         [1225, 4067, 4068, 410, 4359, 5097, 411, 4362, 4076, 186, 188])
        self.assertTrue(ORIGINAL_CONFIG.is_file())

    def test_single_source_requires_exactly_one_bounded_weekly_package(self):
        a, b = selected_period("2026-09")
        calls = []
        delegate = fake_api()

        def fetch(path):
            calls.append(path)
            return delegate(path)

        result = fetch_one_series(4359, a, b, fetch)
        self.assertEqual(len(result), 144)
        self.assertEqual(list(result.values()), [-80.0] * 144)
        self.assertEqual(len(calls), 2)

    def test_bad_index_or_nonfinite_value_fail_closed(self):
        a, b = selected_period("2026-09")
        with self.assertRaisesRegex(PilotUnavailable, "weekly index"):
            fetch_one_series(4359, a, b, fake_api(bad_index=True))
        with self.assertRaisesRegex(PilotUnavailable, "nonfinite"):
            fetch_one_series(4359, a, b, fake_api(nonfinite=True))

    def test_nulls_are_preserved_as_missing_not_fabricated(self):
        a, b = selected_period("2026-09")
        observed = fetch_one_series(4359, a, b, fake_api(null_value=True))
        self.assertEqual(len(observed), 144)
        self.assertTrue(any(v is None for v in observed.values()))

    def test_absent_source_hours_are_not_filled(self):
        a, b = selected_period("2026-09")
        observed = fetch_one_series(4359, a, b, fake_api(missing=True))
        self.assertEqual(len(observed), 138)  # one hour-of-day excluded on six days

    @unittest.skipUnless(PANDAS_AVAILABLE, "pandas not installed in test interpreter")
    def test_rebuilds_exact_144_by_11_frame_and_hourly_errors(self):
        frame, errors = reproduce_frames("2026-09", fake_api())
        self.assertEqual(frame.shape, (144, 11))
        self.assertEqual(errors.shape, (144, 5))
        self.assertTrue(all(dtype.kind == "f" for dtype in frame.dtypes))
        self.assertEqual(frame.index[0].strftime("%Y-%m-%d %H:%M"), "2026-09-01 00:00")
        self.assertEqual(frame.index[-1].strftime("%Y-%m-%d %H:%M"), "2026-09-06 23:00")
        self.assertTrue((frame["residual_load"] == -80.0).all())
        self.assertTrue((errors["err_residual_load"]
                         == frame["fc_residual_load"] - frame["residual_load"]).all())
        self.assertEqual(len(_fingerprint(frame)), 16)

    @unittest.skipUnless(PANDAS_AVAILABLE, "pandas not installed in test interpreter")
    def test_matching_and_mismatching_reference_are_both_nonpublishable(self):
        frame, errors = reproduce_frames("2026-09", fake_api())
        ref = {
            "model": "linear_direct",
            "run_on": {
                "smard.csv": {"month_hashes": {"2026-09": _fingerprint(frame)}},
                "smard_forecast_errors_hourly.csv": {
                    "month_hashes": {"2026-09": _fingerprint(errors)}
                },
            },
            "versions": {"pandas": "synthetic test"},
        }
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "config.json"
            path.write_text(json.dumps(ref), encoding="utf-8")
            matched = compare_reference("2026-09", fake_api(), path)
            self.assertEqual(matched["status"], "ONE_MONTH_REFERENCE_MATCH")
            self.assertFalse(matched["original_training_data_recovered"])
            self.assertFalse(matched["historic_issue_time_vintage_verified"])
            self.assertFalse(matched["safe_to_publish"])
            ref["run_on"]["smard.csv"]["month_hashes"]["2026-09"] = "0" * 16
            path.write_text(json.dumps(ref), encoding="utf-8")
            unmatched = compare_reference("2026-09", fake_api(), path)
            self.assertEqual(unmatched["status"], "ONE_MONTH_REFERENCE_MISMATCH")
            self.assertFalse(unmatched["safe_to_publish"])

    @unittest.skipUnless(PANDAS_AVAILABLE, "pandas not installed in test interpreter")
    def test_missing_one_source_series_does_not_create_fake_values(self):
        frame, errors = reproduce_frames("2026-09", fake_api(missing=True))
        self.assertEqual(len(frame), 144)
        self.assertEqual(int(frame["residual_load"].isna().sum()), 6)
        self.assertEqual(int(errors["residual_load"].isna().sum()), 6)


if __name__ == "__main__":
    unittest.main()
