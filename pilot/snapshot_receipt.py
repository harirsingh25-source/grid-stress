"""Immutable local research receipt for a nonpublishable GridStress source snapshot.

Do not commit output. The captured current-SMARD values are NOT proof of
original issue-time availability, nor a trained ML forecast. This tool has
no scheduler, network requests, overwrite capability or cloud integration.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

from .smard_daily_pilot import PilotUnavailable


def canonical_bytes(report: dict) -> bytes:
    if (
        report.get("status") != "RIDGE_13_FEATURES_CURRENT_SNAPSHOT_UNVERIFIED"
        or report.get("safe_to_publish") is not False
        or report.get("trained_ridge_estimator_available") is not False
        or report.get("ridge_predictions") is not None
        or report.get("ensemble_predictions") is not None
        or report.get("forecast_issue_vintage_verified") is not False
        or report.get("historical_actuals_as_of_cutoff_verified") is not False
    ):
        raise PilotUnavailable("snapshot must be explicitly uncertified, unpublished research only")
    day = report.get("delivery_date")
    captured = report.get("captured_at_utc")
    if (
        not isinstance(day, str)
        or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day)
        or not isinstance(captured, str)
        or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}\+00:00", captured)
        or report.get("feature_count") != 13
        or report.get("hour_count") != 24
        or not isinstance(report.get("feature_rows"), list)
        or len(report["feature_rows"]) != 24
    ):
        raise PilotUnavailable("missing or invalid snapshot receipt metadata")
    data = json.dumps(report, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False).encode("utf-8") + b"\n"
    if len(data) > 1_000_000:
        raise PilotUnavailable("snapshot too large for bounded local research receipt")
    return data


def save_local_receipt(report: dict, directory: Path | None = None) -> dict:
    """Write only a new file, owner-readable, never overwrite, no symlinks."""
    data = canonical_bytes(report)
    base = directory or Path(__file__).resolve().parent / "snapshots"
    base = base.resolve()
    base.mkdir(parents=True, exist_ok=True, mode=0o700)
    if not base.is_dir() or base.is_symlink():
        raise PilotUnavailable("snapshot folder must be an ordinary directory")
    date_part = report["delivery_date"].replace("-", "")
    date_time = report["captured_at_utc"].replace("-", "").replace(":", "").replace(".", "").replace("+00", "Z")
    digest = hashlib.sha256(data).hexdigest()
    name = f"smard-ridge-{date_part}-{date_time}-{digest[:12]}.json"
    path = base / name
    if path.exists() or path.is_symlink():
        raise PilotUnavailable("same snapshot already exists; overwriting is forbidden")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    try:
        fd = os.open(path, flags, 0o600)
    except FileExistsError as exc:
        raise PilotUnavailable("snapshot filename already exists") from exc
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return {
        "status": "LOCAL_RESEARCH_RECEIPT_ONLY",
        "path": str(path),
        "sha256": digest,
        "bytes": len(data),
        "historical_issue_time_vintage_verified": False,
        "safe_to_publish": False,
    }
