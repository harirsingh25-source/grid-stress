"""Offline tests for immutable local-only GridStress research-source receipts."""

import hashlib
import json
import os
import stat
import tempfile
import unittest
from pathlib import Path

from pilot.snapshot_receipt import canonical_bytes, save_local_receipt, PilotUnavailable


def sample_report():
    return {
        "status": "RIDGE_13_FEATURES_CURRENT_SNAPSHOT_UNVERIFIED",
        "delivery_date": "2026-11-21",
        "captured_at_utc": "2026-11-20T18:56:01.123456+00:00",
        "feature_count": 13,
        "hour_count": 24,
        "feature_rows": [{"hour": i, "fc_grid_load": 123.4} for i in range(24)],
        "trained_ridge_estimator_available": False,
        "forecast_issue_vintage_verified": False,
        "historical_actuals_as_of_cutoff_verified": False,
        "ridge_predictions": None,
        "ensemble_predictions": None,
        "safe_to_publish": False,
    }


class LocalReceiptTests(unittest.TestCase):
    def test_immutable_file_sha_matches_serialized_payload(self):
        report = sample_report()
        with tempfile.TemporaryDirectory() as folder:
            receipt = save_local_receipt(report, Path(folder))
            path = Path(receipt["path"])
            self.assertTrue(path.is_file())
            self.assertEqual(path.parent, Path(folder))
            self.assertIn("smard-ridge-20261121-", path.name)
            payload = path.read_bytes()
            self.assertEqual(payload, canonical_bytes(report))
            self.assertEqual(hashlib.sha256(payload).hexdigest(), receipt["sha256"])
            self.assertEqual(len(payload), receipt["bytes"])
            self.assertFalse(receipt["safe_to_publish"])
            self.assertFalse(receipt["historical_issue_time_vintage_verified"])
            if os.name == "posix":
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)

    def test_repeated_receipt_must_not_overwrite_original_file(self):
        report = sample_report()
        with tempfile.TemporaryDirectory() as folder:
            save_local_receipt(report, Path(folder))
            with self.assertRaisesRegex(PilotUnavailable, "already exists"):
                save_local_receipt(report, Path(folder))
            self.assertEqual(len(list(Path(folder).glob("*.json"))), 1)

    def test_fake_verified_or_published_snapshot_rejected(self):
        for field, altered in (
            ("status", "TRAINED_MODEL"),
            ("safe_to_publish", True),
            ("trained_ridge_estimator_available", True),
            ("forecast_issue_vintage_verified", True),
            ("historical_actuals_as_of_cutoff_verified", True),
            ("ridge_predictions", [100]),
            ("ensemble_predictions", [100]),
            ("feature_count", 12),
            ("hour_count", 23),
        ):
            report = sample_report()
            report[field] = altered
            with self.subTest(field=field), self.assertRaises(PilotUnavailable):
                canonical_bytes(report)

    def test_payload_has_no_nonfinite_json_numbers(self):
        report = sample_report()
        report["feature_rows"][0]["fc_grid_load"] = float("nan")
        with self.assertRaises(ValueError):
            canonical_bytes(report)

    def test_local_capture_directory_is_gitignored(self):
        root = Path(__file__).resolve().parents[1]
        self.assertIn("snapshots/", (root / "pilot/.gitignore").read_text())
        script = (root / "pilot/ridge_feature_snapshot.py").read_text()
        self.assertIn('parser.add_argument("--save-local"', script)
        self.assertIn("save_local_receipt(report)", script)

    def test_symlink_directory_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            true_dir = base / "true"
            true_dir.mkdir()
            linked_dir = base / "link"
            try:
                linked_dir.symlink_to(true_dir, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("symlinks unsupported in this test environment")
            with self.assertRaisesRegex(PilotUnavailable, "symlink"):
                save_local_receipt(sample_report(), linked_dir)


if __name__ == "__main__":
    unittest.main()
