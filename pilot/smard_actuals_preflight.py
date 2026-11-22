"""Read-only observed residual-load coverage preflight for original GridStress Ridge.

This probes the *currently served* SMARD observed residual load (filter 4359).
It does NOT establish these observations were available at the original
forecast's 16:00 local cutoff. SMARD responses can be revised; therefore
this cannot certify historic issue-time source vintages, compute validated
Ridge features, fit an estimator, publish, or schedule any job.

Run from the personal fork checkout, after the tomorrow-only SMARD preflight:
    python3 -m pilot.smard_actuals_preflight --delivery-date YYYY-MM-DD

Only ordinary (24-hour) local target/history days are evaluated here.
DST-day source alignment needs separate correspondence with the team
notebook's local-time index and is deliberately rejected.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import date, datetime, time, timedelta, timezone
from urllib.request import Request, urlopen

from .smard_daily_pilot import (
    LOCAL,
    PilotUnavailable,
    build_preview,
    daily_hours_utc,
)

ACTUAL_RESIDUAL_FILTER = 4359  # The original team's notebooks/API-connection.ipynb
BASE = f"https://www.smard.de/app/chart_data/{ACTUAL_RESIDUAL_FILTER}/DE"
MAX_PACKAGES = 4
MAX_RESPONSE_BYTES = 5_000_000


def get_actuals_json(path: str) -> dict:
    """Only GET the single fixed, public SMARD observed-residual-load filter."""
    prefix = f"/{ACTUAL_RESIDUAL_FILTER}/DE/"
    if (
        not path.startswith(prefix)
        or not path.endswith(".json")
        or ".." in path
        or "?" in path
        or "#" in path
    ):
        raise PilotUnavailable("SMARD observed-actual request is not allowlisted")
    req = Request(
        f"https://www.smard.de/app/chart_data{path}",
        headers={"Accept": "application/json", "User-Agent": "GridStress-research-preflight/0.1"},
    )
    with urlopen(req, timeout=20) as response:
        body = response.read(MAX_RESPONSE_BYTES + 1)
    if len(body) > MAX_RESPONSE_BYTES:
        raise PilotUnavailable("oversized observed actuals response")
    result = json.loads(body)
    if not isinstance(result, dict):
        raise PilotUnavailable("invalid SMARD actuals JSON")
    return result


def required_actual_hours(day: date) -> dict:
    """Map target hours to historical local-clock lags without using future rows.

    Original team notebook reindexes naive local hourly timestamps using
    -48h and -168h Timedelta. This equivalence is checked only on ordinary
    dates; ambiguous or missing DST-hour mappings are intentionally refused.
    """
    target_hours = daily_hours_utc(day)
    for check_day in (day, day - timedelta(days=2), day - timedelta(days=7)):
        if len(daily_hours_utc(check_day)) != 24:
            raise PilotUnavailable("DST boundary requires original-team local-index verification")
    last_actual_day = day - timedelta(days=1)
    if len(daily_hours_utc(last_actual_day)) != 24:
        raise PilotUnavailable("DST cutoff day requires original-team local-index verification")

    lags = {}
    for delta, key in ((2, "rl_lag_48h"), (7, "rl_lag_168h")):
        mapped = []
        for target in target_hours:
            local_target = target.astimezone(LOCAL)
            naive_hour = local_target.replace(tzinfo=None) - timedelta(days=delta)
            history_hour = naive_hour.replace(tzinfo=LOCAL).astimezone(timezone.utc)
            mapped.append(history_hour)
        if len(set(mapped)) != 24:
            raise PilotUnavailable("ambiguous historical lag target")
        lags[key] = mapped

    cutoff_day = day - timedelta(days=1)
    last_eligible_hour_local = datetime.combine(cutoff_day, time(15), LOCAL)
    lags["rl_last_available"] = [last_eligible_hour_local.astimezone(timezone.utc)]
    return lags


def fetch_observed_residual(wanted_hours: set[datetime], get_json=get_actuals_json) -> dict:
    """Fetch a few weekly packages and require all requested observed hours."""
    if not wanted_hours or any(
        h.tzinfo is None or h.utcoffset() is None for h in wanted_hours
    ):
        raise PilotUnavailable("observed actuals target timestamps must be timezone-aware")
    wanted = {hour.astimezone(timezone.utc) for hour in wanted_hours}
    earliest = min(wanted)
    latest = max(wanted) + timedelta(hours=1)
    first_ms = int(earliest.timestamp() * 1000)
    end_ms = int(latest.timestamp() * 1000)
    index = get_json(f"/{ACTUAL_RESIDUAL_FILTER}/DE/index_hour.json").get("timestamps")
    if (
        not isinstance(index, list)
        or not index
        or any(type(start) is not int for start in index)
        or len(set(index)) != len(index)
    ):
        raise PilotUnavailable("invalid SMARD observed-residual weekly index")
    packages = sorted(index)
    needed = [
        start for i, start in enumerate(packages)
        if start < end_ms and (i + 1 == len(packages) or packages[i + 1] > first_ms)
    ]
    if not 1 <= len(needed) <= MAX_PACKAGES:
        raise PilotUnavailable("missing or excessive observed-residual packages")

    values = {}
    for start in needed:
        doc = get_json(
            f"/{ACTUAL_RESIDUAL_FILTER}/DE/"
            f"{ACTUAL_RESIDUAL_FILTER}_DE_hour_{start}.json"
        )
        series = doc.get("series")
        if not isinstance(series, list):
            raise PilotUnavailable("invalid observed-residual series")
        for pair in series:
            if not isinstance(pair, (list, tuple)) or len(pair) != 2:
                raise PilotUnavailable("invalid observed-residual record")
            stamp_ms, raw = pair
            if type(stamp_ms) is not int:
                raise PilotUnavailable("invalid observed-residual timestamp")
            stamp = datetime.fromtimestamp(stamp_ms / 1000, timezone.utc)
            if stamp not in wanted:
                continue
            if stamp in values:
                raise PilotUnavailable("duplicate observed-residual timestamp")
            # Residual load is allowed to be negative; reject null and nonfinite.
            if type(raw) not in (int, float) or not math.isfinite(raw):
                raise PilotUnavailable("missing or invalid observed residual load")
            values[stamp] = float(raw)

    missing = wanted - set(values)
    if missing:
        raise PilotUnavailable(
            f"missing {len(missing)} required observed-residual hours"
        )
    return values


def observed_history_report(preview: dict, get_json=get_actuals_json) -> dict:
    """Read-only source coverage report; never assert as-of-cutoff eligibility."""
    if (
        preview.get("status") != "RESEARCH_PREVIEW_ONLY"
        or preview.get("source_vintage_verified") is not False
        or preview.get("model_inference") != "NOT_AVAILABLE"
        or preview.get("ensemble_forecast") is not None
        or preview.get("public_release_authorized") is not False
    ):
        raise PilotUnavailable("untrusted SMARD day-ahead preview contract")
    day = date.fromisoformat(preview["delivery_date"])
    lags = required_actual_hours(day)
    sources = set().union(*[set(hours) for hours in lags.values()])
    actuals = fetch_observed_residual(sources, get_json)
    if len(actuals) != len(sources):
        raise PilotUnavailable("observed residual load not complete")
    now = datetime.now(timezone.utc)
    return {
        "status": "HISTORICAL_ACTUALS_CURRENT_SNAPSHOT_ONLY",
        "delivery_date": day.isoformat(),
        "observed_at_utc": now.isoformat(),
        "source": "Bundesnetzagentur | SMARD.de",
        "source_filter": ACTUAL_RESIDUAL_FILTER,
        "required_unique_actual_hours": len(sources),
        "input_coverage": {
            feature: len(hours) for feature, hours in lags.items()
        },
        "issue_time_europe_berlin": (
            datetime.combine(day - timedelta(days=1), time(18), LOCAL).isoformat()
        ),
        "actuals_cutoff_europe_berlin": (
            datetime.combine(day - timedelta(days=1), time(16), LOCAL).isoformat()
        ),
        "actuals_as_of_cutoff_verified": False,
        "source_vintage_verified": False,
        "fitted_estimator_available": False,
        "ridge_predictions": None,
        "ensemble_predictions": None,
        "safe_to_publish": False,
        "warning": (
            "Current SMARD observed residual-load values may have been "
            "published or revised after the original 16:00 information cutoff; "
            "no proof of historical as-of eligibility or fitted model."
        ),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--delivery-date", required=True)
    args = parser.parse_args(argv)
    try:
        delivery_day = date.fromisoformat(args.delivery_date)
        day_preview = build_preview(delivery_day, datetime.now(timezone.utc))
        report = observed_history_report(day_preview)
    except (PilotUnavailable, ValueError, KeyError, OSError, json.JSONDecodeError) as exc:
        print(f"HISTORICAL_ACTUALS_NOT_AVAILABLE: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
