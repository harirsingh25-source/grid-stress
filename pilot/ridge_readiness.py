"""Read-only, fail-closed readiness check for the original GridStress Ridge model.

This does not fit a Ridge estimator, deserialize saved joblib, compute an ML
prediction, score a model, or schedule/publish a forecast. It checks which
features are truly present in a verified-hours SMARD input snapshot and
reports missing issue-time feature dependencies. Source vintage remains
unverified even if all numerical values exist in the current SMARD API.

Run from the repository root (after 18:15 Europe/Berlin on day-1):
    python3 -m pilot.ridge_readiness --delivery-date YYYY-MM-DD
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from .smard_daily_pilot import (
    PilotUnavailable,
    build_preview,
    daily_hours_utc,
)

ROOT = Path(__file__).resolve().parents[1]
ORIGINAL_RIDGE_CONFIG = ROOT / "data/models/linear_direct/config.json"
BERLIN = ZoneInfo("Europe/Berlin")

# Must agree in both identity and ORDER with the saved original team's config.
EXPECTED_FEATURES = (
    "hour", "dow", "month", "is_weekend", "holiday",
    "fc_grid_load", "fc_gen_wind_solar",
    "rl_lag_48h", "rl_lag_168h", "rl_last_available",
    "err_grid_load_recent", "err_renewables_recent", "cap_total",
)

# These cannot be inferred from just tomorrow's two forecast series.
MISSING_DEPENDENCIES = {
    "holiday": "German nationwide public-holiday calendar, consistent with the original holidays library",
    "rl_lag_48h": "historical observed residual load exactly 48 physical hours before each target hour",
    "rl_lag_168h": "historical observed residual load exactly 168 physical hours before each target hour",
    "rl_last_available": "last residual-load actual published by the previous-day 16:00 cutoff (hour ending 16:00)",
    "err_grid_load_recent": "24h rolling mean of eligible historical SMARD load forecast errors as of issue cutoff",
    "err_renewables_recent": "24h rolling mean of eligible historical SMARD renewables forecast errors as of issue cutoff",
    "cap_total": "wind onshore, wind offshore and solar installed capacity with publication-time provenance",
}

AVAILABLE_FEATURES = (
    "hour", "dow", "month", "is_weekend",
    "fc_grid_load", "fc_gen_wind_solar",
)


def load_original_contract(path: Path = ORIGINAL_RIDGE_CONFIG) -> dict:
    """Read JSON only; never open unsafe joblib/pickle model artifacts."""
    obj = json.loads(path.read_text(encoding="utf-8"))
    settings = obj.get("settings", {})
    if obj.get("model") != "linear_direct":
        raise PilotUnavailable("unexpected saved model identity")
    if settings.get("family") != "linear" or settings.get("architecture") != "direct":
        raise PilotUnavailable("unexpected saved Ridge family or architecture")
    if tuple(settings.get("features", [])) != EXPECTED_FEATURES:
        raise PilotUnavailable("original saved Ridge feature schema changed; review required")
    alpha = obj.get("selected", {}).get("alpha")
    if type(alpha) not in (int, float) or not math.isfinite(alpha) or alpha <= 0:
        raise PilotUnavailable("no valid frozen Ridge alpha in saved configuration")
    if settings.get("data_info") != {
        "issue_days_before": "24h",
        "issue_clock": "18h",
        "actuals_lag": "2h",
        "capacity_published_after": "0h",
    }:
        raise PilotUnavailable("Ridge information-cutoff contract changed; review required")
    if settings.get("feature_windows", {}).get("recent_smard_error") != "24h":
        raise PilotUnavailable("Ridge recent-error window changed; review required")
    return {"model": obj["model"], "selected_alpha": float(alpha),
            "features": list(EXPECTED_FEATURES)}


def readiness_report(snapshot: dict, contract: dict | None = None) -> dict:
    """Audit a tomorrow-only SMARD preview; no values are substituted."""
    contract = contract if contract is not None else load_original_contract()
    if snapshot.get("status") != "RESEARCH_PREVIEW_ONLY":
        raise PilotUnavailable("not a tomorrow-only SMARD preview")
    if snapshot.get("source_vintage_verified") is not False:
        raise PilotUnavailable("source-vintage field is not explicitly unverified")
    if snapshot.get("model_inference") != "NOT_AVAILABLE":
        raise PilotUnavailable("input snapshot must not claim a fitted model")
    if snapshot.get("ensemble_forecast") is not None:
        raise PilotUnavailable("input snapshot must not include an ensemble prediction")
    if snapshot.get("public_release_authorized") is not False:
        raise PilotUnavailable("input snapshot must not authorize public release")

    delivery_day = date.fromisoformat(snapshot["delivery_date"])
    hours = daily_hours_utc(delivery_day)
    rows = snapshot.get("hours")
    if not isinstance(rows, list) or len(rows) != len(hours):
        raise PilotUnavailable("incomplete or invalid SMARD hourly source snapshot")

    seen = set()
    for expected_hour, row in zip(hours, rows):
        if not isinstance(row, dict):
            raise PilotUnavailable("invalid SMARD hourly record")
        try:
            parsed = datetime.fromisoformat(row["hour_start_utc"])
        except (ValueError, TypeError, KeyError) as exc:
            raise PilotUnavailable("invalid SMARD UTC hour") from exc
        if parsed.tzinfo is None or parsed.astimezone(timezone.utc) != expected_hour:
            raise PilotUnavailable("out-of-order or incorrect UTC hour")
        if parsed in seen:
            raise PilotUnavailable("duplicate SMARD hour")
        seen.add(parsed)
        for field in ("forecast_load_mwh", "forecast_wind_solar_mwh"):
            value = row.get(field)
            if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
                raise PilotUnavailable(f"missing or invalid SMARD input {field}")

    issue_time = datetime.combine(delivery_day - timedelta(days=1), time(18), BERLIN)
    cutoff = issue_time - timedelta(hours=2)
    last_usable_actual = cutoff - timedelta(hours=1)
    columns = contract["features"]
    if tuple(columns) != EXPECTED_FEATURES:
        raise PilotUnavailable("Ridge feature list does not match frozen team contract")

    return {
        "status": "RIDGE_FEATURES_INCOMPLETE",
        "delivery_date": snapshot["delivery_date"],
        "model": contract["model"],
        "saved_alpha": contract["selected_alpha"],
        "issue_time_europe_berlin": issue_time.isoformat(),
        "actuals_cutoff_europe_berlin": cutoff.isoformat(),
        "last_eligible_actual_hour_start": last_usable_actual.isoformat(),
        "smard_target_hour_count": len(hours),
        "feature_total": len(columns),
        "feature_names_in_original_order": columns,
        "available_feature_names": list(AVAILABLE_FEATURES),
        "unavailable_features": [
            {"feature": field, "required": MISSING_DEPENDENCIES[field]}
            for field in columns if field in MISSING_DEPENDENCIES
        ],
        "source_vintage_verified": False,
        "trained_estimator_available": False,
        "ridge_predictions": None,
        "ensemble_predictions": None,
        "safe_to_publish": False,
        "next_step": (
            "Reconstruct all missing issue-time features from published historical "
            "records and original training logic; fit and independently validate "
            "the original Ridge pipeline before forecasting."
        ),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--delivery-date", required=True,
                        help="Tomorrow's date in Europe/Berlin (YYYY-MM-DD)")
    args = parser.parse_args(argv)
    try:
        day = date.fromisoformat(args.delivery_date)
        preview = build_preview(day, datetime.now(timezone.utc))
        report = readiness_report(preview)
    except (PilotUnavailable, ValueError, KeyError, OSError, json.JSONDecodeError) as exc:
        print(f"RIDGE_NOT_AVAILABLE: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
