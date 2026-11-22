"""Offline regression checks for manual append-only SMARD daily source captures."""

import hashlib
import json
import os
import stat
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from pilot.smard_daily_pilot import daily_hours_utc
from pilot.smard_history_fingerprint import ORIGINAL_SERIES
from pilot.smard_incremental_ingestion import (
    PilotUnavailable, capture_completed_day, compare_capture,
    receipt_payload, save_capture,
)

DAY = date(2026, 11, 21)
NOW = datetime(2026, 11, 22, 10, tzinfo=timezone.utc)
FILTER_IDS = [filter_id for filter_id, _, _ in ORIGINAL_SERIES]


def fake_provider(day=DAY, *, missing=None, null=None, duplicate=None,
                  broken_index=False, negative=None, invalid=None, revision=None):
    hours = daily_hours_utc(day)
    package = int((hours[0] - timedelta(days=2)).timestamp() * 1000)
    following = package + 7 * 24 * 3600 * 1000
    calls = []

    def get_json(path):
        calls.append(path)
        parts = path.strip("/").split("/")
        filter_id = int(parts[0])
        if filter_id not in FILTER_IDS or parts[1] != "DE":
            raise AssertionError(f"invalid request {path}")
        if parts[2] == "index_hour.json":
            return {"timestamps": [package, following] if not broken_index
                    else [package, package]}
        if parts[2] != f"{filter_id}_DE_hour_{package}.json":
            raise AssertionError(f"wrong weekly package path {path}")
        rows = []
        for hour in hours:
            match = (filter_id, hour)
            if match == missing:
                continue
            value = float(filter_id * 10 + 100)
            if filter_id in (4359, 4362):
                value = -100.0
            if match == null:
                value = None
            if match == negative:
                value = -123.0
            if match == invalid:
                value = float("nan")
            if match == revision:
                value = 12345.0
            rows.append([int(hour.timestamp() * 1000), value])
        if duplicate and duplicate[0] == filter_id:
            rows.append([int(duplicate[1].timestamp() * 1000), 999.0])
        return {"series": rows}
    return get_json, calls


def capture(day=DAY, now=NOW, **options):
    provider, calls = fake_provider(day, **options)
    return capture_completed_day(day, now, provider, clock=lambda: now), calls


class DailyIngestionTests(unittest.TestCase):
    def test_complete_11_filter_24_hour_source_capture_is_nonpublishable(self):
        result, calls = capture()
        self.assertEqual(result["status"], "COMPLETE_CURRENT_SOURCE_ONLY")
        self.assertEqual(result["hour_count"], 24)
        self.assertEqual(result["source_document_count"], 22)
        self.assertEqual(len(calls), 22)
        self.assertEqual(len(result["source_documents_decoded_json"]), 22)
        self.assertEqual(result["original_filter_ids"], FILTER_IDS)
        self.assertTrue(result["all_series_complete"])
        self.assertEqual(len(result["hours"]), 24)
        self.assertEqual(len(result["hours"][0]["values"]), 11)
        self.assertEqual(result["hours"][0]["values"]["residual_load"], -100.0)
        self.assertEqual(result["hours"][0]["values"]["fc_residual_load"], -100.0)
        self.assertFalse(result["historic_issue_time_vintage_verified"])
        self.assertFalse(result["original_publication_time_verified"])
        self.assertFalse(result["eligible_as_of_16h_cutoff_verified"])
        self.assertFalse(result["source_bytes_exactly_preserved"])
        self.assertFalse(result["model_training_authorized"])
        self.assertIsNone(result["model_predictions"])
        self.assertFalse(result["safe_to_publish"])
        self.assertGreater(len(receipt_payload(result)), 1000)

    def test_missing_hour_is_retained_as_incomplete_not_fabricated(self):
        hour = daily_hours_utc(DAY)[5]
        result, _ = capture(missing=(410, hour))
        self.assertEqual(result["status"], "INCOMPLETE_CURRENT_SOURCE_ONLY")
        self.assertFalse(result["all_series_complete"])
        self.assertEqual(result["source_summary"][3]["missing_hour_count"], 1)
        self.assertIsNone(result["hours"][5]["values"]["grid_load"])
        self.assertFalse(result["safe_to_publish"])
        self.assertTrue(receipt_payload(result))

    def test_null_source_value_stays_null_and_incomplete(self):
        hour = daily_hours_utc(DAY)[10]
        result, _ = capture(null=(4068, hour))
        self.assertEqual(result["source_summary"][2]["null_value_count"], 1)
        self.assertIsNone(result["hours"][10]["values"]["solar"])
        self.assertFalse(result["all_series_complete"])

    def test_dst_days_preserve_23_or_25_utc_physical_hours(self):
        for day, count in ((date(2027, 3, 28), 23), (date(2027, 10, 31), 25)):
            with self.subTest(day=day):
                now = datetime.combine(day + timedelta(days=1), datetime.min.time(), timezone.utc) + timedelta(hours=8)
                result, _ = capture(day, now=now)
                self.assertEqual(result["hour_count"], count)
                self.assertEqual(len({r["hour_start_utc"] for r in result["hours"]}), count)
                self.assertEqual(len(result["hours"]), count)
                self.assertTrue(result["all_series_complete"])

    def test_rejects_today_other_past_day_and_future_before_network(self):
        provider, calls = fake_provider()
        for day in (date(2026, 11, 22), date(2026, 11, 20), date(2026, 11, 23)):
            with self.subTest(day=day), self.assertRaisesRegex(PilotUnavailable, "only yesterday"):
                capture_completed_day(day, NOW, provider)
        self.assertEqual(calls, [])

    def test_duplicate_or_corrupt_source_fails_without_receipt(self):
        hour = daily_hours_utc(DAY)[6]
        for options, phrase in (
            ({"duplicate": (410, hour)}, "duplicated"),
            ({"invalid": (4359, hour)}, "invalid SMARD source value"),
            ({"negative": (4068, hour)}, "invalid SMARD source value"),
            ({"broken_index": True}, "weekly SMARD index"),
        ):
            with self.subTest(options=options), self.assertRaisesRegex(PilotUnavailable, phrase):
                capture(**options)

    def test_revisions_are_comparable_but_never_overwrite_prior_values(self):
        hour = daily_hours_utc(DAY)[3]
        first, _ = capture()
        later, _ = capture(revision=(410, hour))
        old_sha = hashlib.sha256(receipt_payload(first)).hexdigest()
        audit = compare_capture(first, later)
        self.assertEqual(audit["comparison_status"], "REVISIONS_DETECTED")
        self.assertEqual(audit["current_source_value_changes"], 1)
        self.assertEqual(audit["prior_receipt_sha256"], old_sha)
        self.assertEqual(audit["changes"][0]["field"], "grid_load")
        self.assertEqual(audit["changes"][0]["hour_start_utc"], hour.isoformat())
        self.assertFalse(audit["safe_to_train_or_publish"])
        self.assertNotEqual(first["hours"][3]["values"]["grid_load"], later["hours"][3]["values"]["grid_load"])
        self.assertEqual(compare_capture(first, first)["comparison_status"], "UNCHANGED")

    def test_comparison_refuses_unrelated_delivery_day(self):
        first, _ = capture()
        prior_day = date(2026, 11, 20)
        now = datetime(2026, 11, 21, 10, tzinfo=timezone.utc)
        other, _ = capture(prior_day, now=now)
        with self.assertRaisesRegex(PilotUnavailable, "different days"):
            compare_capture(first, other)

    def test_atomic_append_only_receipt_and_checksum(self):
        data, _ = capture()
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "receipts"
            meta = save_capture(data, target)
            file = Path(meta["path"])
            self.assertTrue(file.is_file())
            self.assertEqual(file.read_bytes(), receipt_payload(data))
            self.assertEqual(hashlib.sha256(file.read_bytes()).hexdigest(), meta["sha256"])
            self.assertEqual(meta["physical_hours"], 24)
            self.assertEqual(meta["source_documents"], 22)
            self.assertFalse(meta["safe_to_train_or_publish"])
            self.assertEqual(len(list(target.glob("*.json"))), 1)
            self.assertEqual(len(list(target.glob(".*"))), 0)
            if os.name == "posix":
                self.assertEqual(stat.S_IMODE(file.stat().st_mode), 0o600)
            with self.assertRaisesRegex(PilotUnavailable, "already exists"):
                save_capture(data, target)
            self.assertEqual(len(list(target.glob("*.json"))), 1)

    def test_incomplete_capture_may_be_archived_but_never_training_ready(self):
        hour = daily_hours_utc(DAY)[1]
        data, _ = capture(null=(4359, hour))
        with tempfile.TemporaryDirectory() as folder:
            meta = save_capture(data, Path(folder))
            self.assertEqual(meta["capture_status"], "INCOMPLETE_CURRENT_SOURCE_ONLY")
            self.assertFalse(meta["all_series_complete"])
            self.assertFalse(meta["safe_to_train_or_publish"])

    def test_tampered_source_checksum_fails_before_writing(self):
        data, _ = capture()
        data["source_documents_decoded_json"][0]["document"]["timestamps"][0] = 42
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(PilotUnavailable, "checksum mismatch"):
                save_capture(data, Path(folder))
            self.assertEqual(list(Path(folder).glob("*.json")), [])

    def test_fake_training_or_published_flags_are_rejected(self):
        for field, value in (
            ("safe_to_publish", True),
            ("model_training_authorized", True),
            ("historic_issue_time_vintage_verified", True),
            ("eligible_as_of_16h_cutoff_verified", True),
            ("original_publication_time_verified", True),
            ("model_predictions", [1]),
            ("source_bytes_exactly_preserved", True),
        ):
            with self.subTest(field=field):
                result, _ = capture()
                result[field] = value
                with self.assertRaisesRegex(PilotUnavailable, "unsafe"):
                    receipt_payload(result)

    def test_symlink_receipt_directory_is_refused(self):
        data, _ = capture()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            parent = root / "real"
            parent.mkdir()
            linked = root / "link"
            try:
                linked.symlink_to(parent, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("symlinks unavailable")
            with self.assertRaisesRegex(PilotUnavailable, "symlink"):
                save_capture(data, linked)

    def test_gitignore_and_manual_only_contract(self):
        root = Path(__file__).resolve().parents[1]
        self.assertIn("ingestion_receipts/", (root / "pilot/.gitignore").read_text())
        source = (root / "pilot/smard_incremental_ingestion.py").read_text()
        self.assertIn("V1 captures only yesterday", source)
        self.assertNotIn("scheduler.add_job", source)
        self.assertNotIn("subprocess.run", source)
        self.assertNotIn("joblib.load", source)
        self.assertNotIn("croniter", source)
        self.assertIn("os.link(temp, final)", source)


if __name__ == "__main__":
    unittest.main()
