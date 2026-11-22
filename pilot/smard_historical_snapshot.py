"""Historical SMARD component forecast preview, separate from live day-ahead inference.

This module reads the current SMARD API snapshot for a *past* calendar day.
Values may have been revised since their original issuance: DO NOT use this
data as proof of an original historical forecast vintage or model performance.
No trained model, ensemble, scheduling or publication is implemented.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Callable

from .smard_daily_pilot import (
    FILTER_LOAD,
    FILTER_RENEWABLES,
    LOCAL,
    PilotUnavailable,
    daily_hours_utc,
    fetch_forecast_series,
    smard_json,
)


def build_historical_snapshot(
    delivery_day: date,
    as_of: datetime,
    get_json: Callable[[str], dict] = smard_json,
) -> dict:
    """Return complete historical component forecasts or fail without fallback."""
    if not isinstance(delivery_day, date) or isinstance(delivery_day, datetime):
        raise PilotUnavailable("invalid historical delivery day")
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise PilotUnavailable("as-of must be timezone-aware")
    local_today = as_of.astimezone(LOCAL).date()
    if delivery_day < date(2019, 1, 1) or delivery_day >= local_today:
        raise PilotUnavailable("select a completed historical day, 2019-01-01 through yesterday")

    hours = daily_hours_utc(delivery_day)
    load = fetch_forecast_series(FILTER_LOAD, hours, get_json)
    wind_solar = fetch_forecast_series(FILTER_RENEWABLES, hours, get_json)

    return {
        "status": "HISTORICAL_COMPONENT_PREVIEW_ONLY",
        "source": "Bundesnetzagentur | SMARD.de",
        "delivery_date": delivery_day.isoformat(),
        "retrieved_at_utc": as_of.isoformat(),
        "source_vintage_verified": False,
        "forecast_warning": (
            "Current SMARD API values may be revised. These are not verified "
            "original issue-time forecasts or out-of-sample predictions."
        ),
        "model_inference": "NOT_AVAILABLE",
        "ensemble_forecast": None,
        "public_release_authorized": False,
        "hours": [
            {
                "hour_start_utc": hour.isoformat(),
                "hour_start_europe_berlin": hour.astimezone(LOCAL).isoformat(),
                "forecast_load_mwh": load[hour],
                "forecast_wind_solar_mwh": wind_solar[hour],
                "derived_component_residual_mwh": load[hour] - wind_solar[hour],
            }
            for hour in hours
        ],
    }
