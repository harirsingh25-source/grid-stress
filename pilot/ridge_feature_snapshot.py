"""Build all 13 original Ridge inputs as an UNVERIFIED current-SMARD snapshot.

The original team developed the modelling and feature convention. This
independent, read-only research adapter reproduces a single ordinary
(non-DST) target day using the *currently served* public SMARD API.

IMPORTANT: the API may revise both forecasts and observations. Complete
numeric features are not evidence of availability by the model's original
16:00 cutoff. Never fit, predict, compare MAE, or publish from this module.
No model artifact, scheduler, cloud resource, or public endpoint is created.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from datetime import date, datetime, time, timedelta, timezone
from functools import lru_cache
from pathlib import Path

from .ridge_readiness import EXPECTED_FEATURES, PilotUnavailable, readiness_report
from .smard_transport import fetch_public_smard_json
from .smard_actuals_preflight import required_actual_hours
from .smard_daily_pilot import LOCAL, build_preview, daily_hours_utc

# All filter identifiers come from the ORIGINAL TEAM's notebooks/API-connection.ipynb.
FILTERS = {
    "residual": 4359,
    "grid_actual": 410,
    "wind_off_actual": 1225,
    "wind_on_actual": 4067,
    "solar_actual": 4068,
    "grid_forecast": 411,
    "wind_solar_forecast": 5097,
    "wind_off_capacity": 4076,
    "wind_on_capacity": 186,
    "solar_capacity": 188,
}
ALLOWED_IDS = frozenset(FILTERS.values())
BASE = "https://www.smard.de/app/chart_data"
MAX_PACKAGES = 4
MAX_BYTES = 5_000_000


def fetch_json(path: str) -> dict:
    """Fetch ONLY an allowlisted public SMARD weekly-index or package URL."""
    match = re.fullmatch(r"/([0-9]+)/DE/(index_hour|[0-9]+_DE_hour_[0-9]+)\.json", path)
    if match is None or int(match.group(1)) not in ALLOWED_IDS:
        raise PilotUnavailable("SMARD feature request not allowlisted")
    token = match.group(2)
    if token != "index_hour" and not token.startswith(f"{match.group(1)}_DE_hour_"):
        raise PilotUnavailable("SMARD package filter mismatch")
    return fetch_public_smard_json(
        path, user_agent="GridStress-ridge-research/0.1", max_bytes=MAX_BYTES
    )


def fetch_exact_hours(filter_id: int, requested: set[datetime], get_json=fetch_json) -> dict:
    """Read bounded weekly packages; refuse missing, duplicate and invalid values.

    Values for observed residual load may be negative. All other selected
    energy and installed-capacity series must be finite and nonnegative.
    Caller must supply real UTC timestamps, never local ambiguous hours.
    """
    if filter_id not in ALLOWED_IDS or not requested:
        raise PilotUnavailable("unknown feature series or empty requested hours")
    hours = set()
    for ts in requested:
        if not isinstance(ts, datetime) or ts.tzinfo is None or ts.utcoffset() is None:
            raise PilotUnavailable("feature request must use timezone-aware hours")
        canonical = ts.astimezone(timezone.utc)
        if canonical.minute or canonical.second or canonical.microsecond:
            raise PilotUnavailable("feature request must use hour starts")
        hours.add(canonical)
    starts = get_json(f"/{filter_id}/DE/index_hour.json").get("timestamps")
    if (
        not isinstance(starts, list) or not starts
        or any(type(x) is not int for x in starts)
        or len(set(starts)) != len(starts)
    ):
        raise PilotUnavailable("invalid SMARD feature weekly index")
    indexes = sorted(starts)
    lower = int(min(hours).timestamp() * 1000)
    upper = int((max(hours) + timedelta(hours=1)).timestamp() * 1000)
    packages = [
        x for i, x in enumerate(indexes)
        if x < upper and (i + 1 == len(indexes) or indexes[i + 1] > lower)
    ]
    if not 1 <= len(packages) <= MAX_PACKAGES:
        raise PilotUnavailable("missing or excessive SMARD feature weekly packages")
    values = {}
    for package in packages:
        rows = get_json(
            f"/{filter_id}/DE/{filter_id}_DE_hour_{package}.json"
        ).get("series")
        if not isinstance(rows, list):
            raise PilotUnavailable("invalid SMARD feature series")
        for item in rows:
            if not isinstance(item, list) or len(item) != 2 or type(item[0]) is not int:
                raise PilotUnavailable("invalid SMARD feature row")
            hour = datetime.fromtimestamp(item[0] / 1000, timezone.utc)
            if hour not in hours:
                continue
            if hour in values:
                raise PilotUnavailable("duplicate SMARD feature hour")
            raw = item[1]
            if (
                type(raw) not in (int, float) or not math.isfinite(raw)
                or (filter_id != FILTERS["residual"] and raw < 0)
            ):
                raise PilotUnavailable("missing or invalid SMARD feature value")
            values[hour] = float(raw)
    missing = hours - values.keys()
    if missing:
        raise PilotUnavailable(f"missing {len(missing)} SMARD feature hours")
    return values


def easter_sunday(year: int) -> date:
    """Gregorian Easter; helper for German *nationwide* public holidays only."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    ell = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * ell) // 451
    month, day = divmod(h + ell - 7 * m + 114, 31)
    return date(year, month, day + 1)


def nationwide_holiday(day: date) -> bool:
    """Provisional calendar only; compare against team's holidays(DE) before training."""
    easter = easter_sunday(day.year)
    moving = {
        easter - timedelta(days=2),  # Good Friday
        easter + timedelta(days=1),  # Easter Monday
        easter + timedelta(days=39),  # Ascension
        easter + timedelta(days=50),  # Whit Monday
    }
    fixed = {(1, 1), (5, 1), (10, 3), (12, 25), (12, 26)}
    return day in moving or (day.month, day.day) in fixed


def current_feature_snapshot(preview: dict, get_json=fetch_json, holiday_check=nationwide_holiday) -> dict:
    """Construct a 24x13 numerical table, deliberately NOT certifiable for inference."""
    readiness = readiness_report(preview)
    if readiness["status"] != "RIDGE_FEATURES_INCOMPLETE":
        raise PilotUnavailable("Ridge readiness gate failed")
    day = date.fromisoformat(preview["delivery_date"])
    target_hours = daily_hours_utc(day)
    if len(target_hours) != 24:
        raise PilotUnavailable("DST day requires original team's local-index alignment")
    lag_map = required_actual_hours(day)
    issue_day = day - timedelta(days=1)
    for check_day in (issue_day, issue_day - timedelta(days=1)):
        if len(daily_hours_utc(check_day)) != 24:
            raise PilotUnavailable("recent-error DST window requires verification")
    latest_history = datetime.combine(issue_day, time(15), LOCAL).astimezone(timezone.utc)
    recent_hours = {
        latest_history - timedelta(hours=offset) for offset in range(24)
    }
    if len(recent_hours) != 24:
        raise PilotUnavailable("recent forecast-error window malformed")

    # One small, run-local cache per feature snapshot. Avoid redownloading
    # the same weekly package/index for repeated capacity-hour probes.
    # Never persist this cache across separate captures or application runs.
    @lru_cache(maxsize=64)
    def get_once(path: str) -> dict:
        return get_json(path)

    actual_needed = set().union(*(set(v) for v in lag_map.values()))
    residual = fetch_exact_hours(FILTERS["residual"], actual_needed, get_once)
    grid_actual = fetch_exact_hours(FILTERS["grid_actual"], recent_hours, get_once)
    wind_off = fetch_exact_hours(FILTERS["wind_off_actual"], recent_hours, get_once)
    wind_on = fetch_exact_hours(FILTERS["wind_on_actual"], recent_hours, get_once)
    solar = fetch_exact_hours(FILTERS["solar_actual"], recent_hours, get_once)
    grid_forecast = fetch_exact_hours(FILTERS["grid_forecast"], recent_hours, get_once)
    wind_solar_forecast = fetch_exact_hours(FILTERS["wind_solar_forecast"], recent_hours, get_once)

    errors_load = [
        grid_forecast[h] - grid_actual[h] for h in sorted(recent_hours)
    ]
    errors_renewables = [
        wind_solar_forecast[h] - (wind_off[h] + wind_on[h] + solar[h])
        for h in sorted(recent_hours)
    ]
    mean_grid_error = math.fsum(errors_load) / 24
    mean_renewables_error = math.fsum(errors_renewables) / 24

    # The original team treats calendar-year capacity as published on Jan 1.
    # Probe two points in the year; this is NOT proof of publication vintage.
    issue_year = issue_day.year
    year_probe = datetime(issue_year, 1, 1, 12, tzinfo=LOCAL).astimezone(timezone.utc)
    current_probe = datetime.combine(issue_day, time(12), LOCAL).astimezone(timezone.utc)
    cap_parts = []
    for key in ("wind_off_capacity", "wind_on_capacity", "solar_capacity"):
        filter_id = FILTERS[key]
        initial = fetch_exact_hours(filter_id, {year_probe}, get_once)[year_probe]
        current = fetch_exact_hours(filter_id, {current_probe}, get_once)[current_probe]
        if not math.isclose(initial, current, abs_tol=0.01, rel_tol=0):
            raise PilotUnavailable("annual installed-capacity series changed; team assumption fails")
        cap_parts.append(current)
    capacity_total_mw = math.fsum(cap_parts)

    lag48 = lag_map["rl_lag_48h"]
    lag168 = lag_map["rl_lag_168h"]
    last_actual = residual[lag_map["rl_last_available"][0]]
    if len(lag48) != len(target_hours) or len(lag168) != len(target_hours):
        raise PilotUnavailable("target-to-history lag mapping incomplete")

    feature_rows = []
    for i, (hour, inputs) in enumerate(zip(target_hours, preview["hours"])):
        local = hour.astimezone(LOCAL)
        if datetime.fromisoformat(inputs["hour_start_utc"]) != hour:
            raise PilotUnavailable("SMARD preview hours differ from model target hours")
        row = {
            "hour": local.hour,
            "dow": local.weekday(),
            "month": local.month,
            "is_weekend": float(local.weekday() >= 5),
            "holiday": float(holiday_check(local.date())),
            "fc_grid_load": float(inputs["forecast_load_mwh"]),
            "fc_gen_wind_solar": float(inputs["forecast_wind_solar_mwh"]),
            "rl_lag_48h": residual[lag48[i]],
            "rl_lag_168h": residual[lag168[i]],
            "rl_last_available": last_actual,
            "err_grid_load_recent": mean_grid_error,
            "err_renewables_recent": mean_renewables_error,
            "cap_total": capacity_total_mw,
        }
        if tuple(row) != EXPECTED_FEATURES or not all(
            type(value) in (int, float) and math.isfinite(value)
            for value in row.values()
        ):
            raise PilotUnavailable("Ridge feature schema or numeric values invalid")
        feature_rows.append({"hour_start_utc": hour.isoformat(), **row})

    return {
        "status": "RIDGE_13_FEATURES_CURRENT_SNAPSHOT_UNVERIFIED",
        "delivery_date": day.isoformat(),
        "captured_at_utc": datetime.now(timezone.utc).isoformat(timespec="microseconds"),
        "source": "Bundesnetzagentur | SMARD.de",
        "original_model": readiness["model"],
        "original_alpha": readiness["saved_alpha"],
        "issue_time_europe_berlin": readiness["issue_time_europe_berlin"],
        "actuals_cutoff_europe_berlin": readiness["actuals_cutoff_europe_berlin"],
        "last_eligible_actual_hour_start": readiness["last_eligible_actual_hour_start"],
        "capacity_reference_year": issue_year,
        "recent_errors_window_utc": {
            "first_hour": min(recent_hours).isoformat(),
            "last_hour": max(recent_hours).isoformat(),
        },
        "original_feature_order": list(EXPECTED_FEATURES),
        "feature_count": len(EXPECTED_FEATURES),
        "hour_count": len(target_hours),
        "recent_error_hours": len(recent_hours),
        "current_source_feature_values_complete": True,
        "historical_actuals_as_of_cutoff_verified": False,
        "forecast_issue_vintage_verified": False,
        "capacity_publication_vintage_verified": False,
        "holiday_calendar_equivalence_verified": False,
        "trained_ridge_estimator_available": False,
        "ridge_predictions": None,
        "ensemble_predictions": None,
        "safe_to_publish": False,
        "warning": (
            "A complete 13-column numerical table from *current* SMARD "
            "snapshots is not an as-of-cutoff dataset. Past forecast/actual "
            "values and annual capacity may have been revised. This is not "
            "a trained model or an out-of-sample forecast."
        ),
        "feature_rows": feature_rows,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--delivery-date", required=True,
                        help="Tomorrow in Europe/Berlin; after 18:15 local")
    parser.add_argument("--save-local", action="store_true",
                        help="Write a hash-verified local-only, Git-ignored source capture")
    args = parser.parse_args(argv)
    try:
        day = date.fromisoformat(args.delivery_date)
        preview = build_preview(day, datetime.now(timezone.utc))
        report = current_feature_snapshot(preview)
        if args.save_local:
            from .snapshot_receipt import save_local_receipt
            receipt = save_local_receipt(report)
            print(json.dumps(receipt, indent=2))
            return 0
    except (PilotUnavailable, ValueError, KeyError, OSError, json.JSONDecodeError) as exc:
        print(f"RIDGE_FEATURES_NOT_AVAILABLE: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
