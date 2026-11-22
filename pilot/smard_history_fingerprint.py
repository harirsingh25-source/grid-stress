"""Compare ONE month of current SMARD history with original-team fingerprints.

No trained model, full-history download, output file, scheduler or publication.
Current API values may have been revised. Equality of one month does not certify
historical issue-time vintages or the other months of the original dataset.

Run from the fork root with pandas installed:
    ./.venv/bin/python -m pilot.smard_history_fingerprint --month 2026-09
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import re
import sys
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

from .smard_daily_pilot import LOCAL
from .smard_transport import PilotUnavailable, fetch_public_smard_json

# IDs, order, and headers match original notebooks/API-connection.ipynb.
ORIGINAL_SERIES = (
    (1225, "Wind Offshore", "wind_off"),
    (4067, "Wind Onshore", "wind_on"),
    (4068, "Solar", "solar"),
    (410, "Grid Load", "grid_load"),
    (4359, "Residual Load", "residual_load"),
    (5097, "Forecast Wind + Solar", "fc_gen_wind_solar"),
    (411, "Forecast Grid Load", "fc_grid_load"),
    (4362, "Forecast Residual Load", "fc_residual_load"),
    (4076, "Capacity Wind Offshore", "cap_wind_off"),
    (186, "Capacity Wind Onshore", "cap_wind_on"),
    (188, "Capacity Solar", "cap_solar"),
)
ORIGINAL_START = date(2019, 1, 1)
ORIGINAL_END_EXCLUSIVE = date(2026, 9, 7)
MAX_PACKAGES_PER_SERIES = 8
ORIGINAL_CONFIG = Path(__file__).resolve().parents[1] / "data/models/linear_direct/config.json"
ERROR_COLUMNS = (
    "residual_load", "fc_residual_load", "err_residual_load",
    "err_grid_load", "err_renewables",
)
HOURLY_ERROR_COLUMNS = (
    "residual_load", "fc_residual_load", "err_residual_load",
    "grid_load", "fc_grid_load", "err_grid_load",
    "renewables", "fc_gen_wind_solar", "err_renewables",
)


def selected_period(month: str) -> tuple[datetime, datetime]:
    """Select one local-time month intersecting the ORIGINAL TEAM dataset."""
    if not isinstance(month, str) or not re.fullmatch(r"\d{4}-\d{2}", month):
        raise PilotUnavailable("month must be YYYY-MM")
    year, number = map(int, month.split("-"))
    if number not in range(1, 13):
        raise PilotUnavailable("invalid month number")
    try:
        first = date(year, number, 1)
    except ValueError as exc:
        raise PilotUnavailable("invalid calendar month") from exc
    next_month = date(year + (number == 12), (number % 12) + 1, 1)
    start, end = max(first, ORIGINAL_START), min(next_month, ORIGINAL_END_EXCLUSIVE)
    if not start < end:
        raise PilotUnavailable("month lies outside the original team's training-data extent")
    return datetime.combine(start, time.min, LOCAL), datetime.combine(end, time.min, LOCAL)


def _json(path: str) -> dict:
    """All transport safety/retry rules are inherited from the pilot."""
    return fetch_public_smard_json(
        path, user_agent="GridStress-one-month-fingerprint/0.1"
    )


def fetch_one_series(
    filter_id: int, start: datetime, end: datetime, get_json=_json
) -> dict[datetime, float | None]:
    """Follow original team timestamp/dictionary handling for one limited month."""
    if filter_id not in {x[0] for x in ORIGINAL_SERIES}:
        raise PilotUnavailable("historical probe filter not allowlisted")
    if start.tzinfo is None or end.tzinfo is None or not start < end:
        raise PilotUnavailable("invalid historical source interval")
    lower, upper = int(start.timestamp() * 1000), int(end.timestamp() * 1000)
    index = get_json(f"/{filter_id}/DE/index_hour.json").get("timestamps")
    if (
        not isinstance(index, list)
        or not index
        or any(type(p) is not int for p in index)
        or len(set(index)) != len(index)
    ):
        raise PilotUnavailable("invalid historical weekly index")
    packages = sorted(index)
    needed = [
        p for i, p in enumerate(packages)
        if p < upper and (i + 1 == len(packages) or packages[i + 1] > lower)
    ]
    if not 1 <= len(needed) <= MAX_PACKAGES_PER_SERIES:
        raise PilotUnavailable("missing or excessive historical weekly packages")
    values = {}
    for package in needed:
        response = get_json(
            f"/{filter_id}/DE/{filter_id}_DE_hour_{package}.json"
        )
        rows = response.get("series")
        if not isinstance(rows, list):
            raise PilotUnavailable("invalid historical series response")
        for row in rows:
            if not isinstance(row, (list, tuple)) or len(row) != 2 or type(row[0]) is not int:
                raise PilotUnavailable("invalid historical hourly row")
            stamp_ms, raw = row
            if not lower <= stamp_ms < upper:
                continue
            if raw is not None and (
                type(raw) not in (int, float) or not math.isfinite(raw)
            ):
                raise PilotUnavailable("invalid or nonfinite historical source value")
            local = datetime.fromtimestamp(stamp_ms / 1000, timezone.utc).astimezone(LOCAL)
            # Original notebook stores values in a dict keyed by local aware
            # datetimes; repeated autumn wall-clock hours follow its semantics.
            values[local] = None if raw is None else float(raw)
    return values


def reproduce_frames(month: str, get_json=_json):
    """Return team-compatible input and error columns for ONE month only.

    pandas is imported here so stdlib-only pilot tests need not install it.
    """
    try:
        import pandas as pd
    except ImportError as exc:
        raise PilotUnavailable("pandas required for original model-data fingerprinting") from exc
    start, end = selected_period(month)
    source = {}
    for filter_id, original_header, _ in ORIGINAL_SERIES:
        source[original_header] = fetch_one_series(filter_id, start, end, get_json)
    frame = pd.DataFrame(source)
    frame.index.name = "timestamp"
    frame = frame.sort_index()

    # Faithful round-trip: original team saved local timestamps without offsets,
    # German CSV separators/decimals and then read every numeric column as float.
    export = frame.copy()
    export.index = export.index.strftime("%Y-%m-%d %H:%M")
    csv_content = export.to_csv(sep=";", decimal=",")
    loaded = pd.read_csv(io.StringIO(csv_content), sep=";", dtype=str)
    loaded["timestamp"] = pd.to_datetime(
        loaded["timestamp"], format="%Y-%m-%d %H:%M"
    )
    for _, original_header, _ in ORIGINAL_SERIES:
        loaded[original_header] = (
            loaded[original_header].str.replace(",", ".", regex=False).astype(float)
        )
    loaded = loaded.set_index("timestamp").sort_index()
    renames = {header: key for _, header, key in ORIGINAL_SERIES}
    time_series = loaded.rename(columns=renames)
    ordered = [key for _, _, key in ORIGINAL_SERIES]
    time_series = time_series[ordered]
    expected_labels = set()
    stamp = start.astimezone(timezone.utc)
    until = end.astimezone(timezone.utc)
    while stamp < until:
        expected_labels.add(stamp.astimezone(LOCAL).strftime("%Y-%m-%d %H:%M"))
        stamp += timedelta(hours=1)
    if len(time_series) != len(expected_labels) or set(
        time_series.index.strftime("%Y-%m-%d %H:%M")
    ) != expected_labels:
        raise PilotUnavailable(
            "current SMARD month does not cover all original local-clock hours"
        )

    errors = pd.DataFrame(index=time_series.index)
    renewables = time_series[["wind_on", "wind_off", "solar"]].sum(axis=1)
    for actual, forecast in (
        ("residual_load", "fc_residual_load"),
        ("grid_load", "fc_grid_load"),
        ("renewables", "fc_gen_wind_solar"),
    ):
        errors[actual] = renewables if actual == "renewables" else time_series[actual]
        errors[forecast] = time_series[forecast]
        errors[f"err_{actual}"] = errors[forecast] - errors[actual]

    # The original errors notebook writes CSV and the model notebook reads it
    # back. Reproduce that float parsing and column selection before hashing.
    hourly_csv = errors[list(HOURLY_ERROR_COLUMNS)].rename_axis("timestamp").to_csv()
    read_back = pd.read_csv(io.StringIO(hourly_csv), index_col="timestamp",
                            parse_dates=["timestamp"])
    return time_series, read_back[list(ERROR_COLUMNS)]


def _fingerprint(frame) -> str:
    """Exact saved-config algorithm: pandas row hashes -> SHA256 first 16."""
    import pandas as pd
    row_hash = pd.util.hash_pandas_object(frame, index=True)
    return hashlib.sha256(row_hash.to_numpy().tobytes()).hexdigest()[:16]


def compare_reference(month: str, get_json=_json, config_path: Path = ORIGINAL_CONFIG) -> dict:
    """Compare fingerprints only; never overwrite original training CSVs."""
    selected_period(month)
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if config.get("model") != "linear_direct":
        raise PilotUnavailable("unexpected original Ridge reference model")
    on = config.get("run_on", {})
    expected_data = on.get("smard.csv", {}).get("month_hashes", {})
    expected_errors = on.get("smard_forecast_errors_hourly.csv", {}).get("month_hashes", {})
    if month not in expected_data or month not in expected_errors:
        raise PilotUnavailable("month has no frozen original-team reference hashes")
    full, errors = reproduce_frames(month, get_json)
    actual_data, actual_errors = _fingerprint(full), _fingerprint(errors)
    matches = {
        "smard.csv": {
            "expected": expected_data[month],
            "current_source": actual_data,
            "matches": actual_data == expected_data[month],
        },
        "smard_forecast_errors_hourly.csv": {
            "expected": expected_errors[month],
            "current_source": actual_errors,
            "matches": actual_errors == expected_errors[month],
        },
    }
    exact_match = all(x["matches"] for x in matches.values())
    return {
        "status": "ONE_MONTH_REFERENCE_MATCH" if exact_match
                  else "ONE_MONTH_REFERENCE_MISMATCH",
        "month": month,
        "rows": len(full),
        "series": len(ORIGINAL_SERIES),
        "source": "Bundesnetzagentur | SMARD current API",
        "original_reference": "team linear_direct/config.json run_on monthly hashes",
        "pandas_version": __import__("pandas").__version__,
        "reference_pandas_version": config.get("versions", {}).get("pandas"),
        "fingerprints": matches,
        "original_training_data_recovered": False,
        "full_history_verified": False,
        "historic_issue_time_vintage_verified": False,
        "ridge_model_trained": False,
        "ensemble_trained": False,
        "safe_to_publish": False,
        "interpretation": (
            "A mismatch can reflect API revisions, CSV/float/DST semantics "
            "or library-version differences; a match is only for this month. "
            "Neither result proves original forecast publication-time vintages."
        ),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--month", required=True, help="single YYYY-MM, e.g. 2026-09")
    args = parser.parse_args(argv)
    try:
        report = compare_reference(args.month)
    except (PilotUnavailable, ValueError, OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(f"HISTORICAL_FINGERPRINT_NOT_AVAILABLE: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
