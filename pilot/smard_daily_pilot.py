"""Read-only SMARD tomorrow-input preflight for a future GridStress ensemble.

This does NOT run a trained model, claim historical forecast vintage, schedule a job,
write to the website, or publish any result. Missing data always fails closed.

Usage after 18:15 Europe/Berlin on the day before delivery:
    python -m pilot.smard_daily_pilot --delivery-date YYYY-MM-DD

STDOUT is structured JSON with status RESEARCH_PREVIEW_ONLY. This is a private
research preflight; the API may return revised snapshots rather than point-in-time
issue-date values. Do not deploy or advertise output as a live validated forecast.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import date, datetime, time, timedelta, timezone
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

BASE = 'https://www.smard.de/app/chart_data'
LOCAL = ZoneInfo('Europe/Berlin')
FILTER_LOAD = 411                 # Forecast grid load; team notebook identifier
FILTER_RENEWABLES = 5097         # Forecast wind + solar; team notebook identifier
REGION = 'DE'
RESOLUTION = 'hour'
MAX_PACKAGES = 4


class PilotUnavailable(ValueError):
    """Input validation failed; no forecast or fallback may be published."""


def daily_hours_utc(day: date) -> list[datetime]:
    """Generate the real physical hourly slots of a local day, including DST."""
    start = datetime.combine(day, time.min, LOCAL).astimezone(timezone.utc)
    end = datetime.combine(day + timedelta(days=1), time.min, LOCAL).astimezone(timezone.utc)
    hours = []
    while start < end:
        hours.append(start)
        start += timedelta(hours=1)
    if len(hours) not in (23, 24, 25):
        raise PilotUnavailable('unexpected local day length')
    return hours


def smard_json(path: str) -> dict:
    """Fetch only allowlisted, path-only, public SMARD JSON, with a bounded timeout."""
    if not path.startswith('/') or '..' in path or '?' in path:
        raise PilotUnavailable('invalid SMARD path')
    allowed = (f'/{FILTER_LOAD}/DE/', f'/{FILTER_RENEWABLES}/DE/')
    if not path.startswith(allowed) or not path.endswith('.json'):
        raise PilotUnavailable('SMARD request not allowlisted')
    req = Request(BASE + path, headers={
        'Accept': 'application/json',
        'User-Agent': 'GridStress-research-preflight/0.1 (read-only)',
    })
    with urlopen(req, timeout=20) as response:
        data = response.read(5_000_001)
    if len(data) > 5_000_000:
        raise PilotUnavailable('oversized SMARD response')
    result = json.loads(data)
    if not isinstance(result, dict):
        raise PilotUnavailable('invalid SMARD JSON object')
    return result


def fetch_forecast_series(filter_id: int, hours: list[datetime], get_json=smard_json) -> dict[datetime, float]:
    """Read bounded weekly packages and require one valid value for every target hour."""
    if filter_id not in (FILTER_LOAD, FILTER_RENEWABLES) or not hours:
        raise PilotUnavailable('invalid series or target window')
    index_path = f'/{filter_id}/{REGION}/index_{RESOLUTION}.json'
    index = get_json(index_path)
    raw_starts = index.get('timestamps')
    if not isinstance(raw_starts, list) or not raw_starts or not all(type(v) is int for v in raw_starts):
        raise PilotUnavailable('invalid SMARD weekly index')
    stamps = sorted(raw_starts)
    if len(stamps) != len(set(stamps)):
        raise PilotUnavailable('duplicate SMARD weekly index packages')
    begin = int(hours[0].timestamp() * 1000)
    end = int((hours[-1] + timedelta(hours=1)).timestamp() * 1000)
    needed = [start for i, start in enumerate(stamps)
              if start < end and (i + 1 == len(stamps) or stamps[i + 1] > begin)]
    if not 1 <= len(needed) <= MAX_PACKAGES:
        raise PilotUnavailable('missing or excessive SMARD weekly packages')
    wanted = set(hours)
    values: dict[datetime, float] = {}
    for package in needed:
        path = f'/{filter_id}/{REGION}/{filter_id}_{REGION}_{RESOLUTION}_{package}.json'
        response = get_json(path)
        rows = response.get('series')
        if not isinstance(rows, list):
            raise PilotUnavailable('invalid SMARD series')
        for item in rows:
            if not isinstance(item, (list, tuple)) or len(item) != 2 or type(item[0]) is not int:
                raise PilotUnavailable('invalid SMARD hourly record')
            timestamp = datetime.fromtimestamp(item[0] / 1000, tz=timezone.utc)
            if timestamp not in wanted:
                continue
            if timestamp in values:
                raise PilotUnavailable('duplicate SMARD value for hour')
            value = item[1]
            if type(value) not in (float, int) or not math.isfinite(float(value)) or value < 0:
                raise PilotUnavailable('invalid or missing SMARD forecast value')
            values[timestamp] = float(value)
    if len(values) != len(hours):
        missing = [h.isoformat() for h in hours if h not in values]
        raise PilotUnavailable(f'SMARD forecast missing {len(missing)} target hours: {missing[:3]}')
    return values


def build_preview(delivery_day: date, now: datetime, get_json=smard_json) -> dict:
    """Construct private research snapshot, with no model prediction or publication."""
    if now.tzinfo is None or now.utcoffset() is None:
        raise PilotUnavailable('as-of must be timezone-aware')
    local_now = now.astimezone(LOCAL)
    if delivery_day != local_now.date() + timedelta(days=1):
        raise PilotUnavailable('delivery date must be tomorrow in Europe/Berlin')
    if local_now.time() < time(18, 15):
        raise PilotUnavailable('do not fetch tomorrow data before 18:15 Europe/Berlin')
    hours = daily_hours_utc(delivery_day)
    demand = fetch_forecast_series(FILTER_LOAD, hours, get_json)
    renewables = fetch_forecast_series(FILTER_RENEWABLES, hours, get_json)
    records = [{
        'hour_start_utc': hour.isoformat(),
        'hour_start_europe_berlin': hour.astimezone(LOCAL).isoformat(),
        'forecast_load_mwh': demand[hour],
        'forecast_wind_solar_mwh': renewables[hour],
        'smard_component_residual_mwh': demand[hour] - renewables[hour],
    } for hour in hours]
    return {
        'status': 'RESEARCH_PREVIEW_ONLY',
        'dataset': 'Bundesnetzagentur | SMARD.de',
        'delivery_date': delivery_day.isoformat(),
        'as_of_europe_berlin': local_now.isoformat(),
        'source_vintage_verified': False,
        'source_warning': 'SMARD API may serve revised values; historic issue-time vintage is unverified',
        'model_inference': 'NOT_AVAILABLE',
        'ensemble_forecast': None,
        'public_release_authorized': False,
        'hours': records,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--delivery-date', required=True, help='Tomorrow in Europe/Berlin: YYYY-MM-DD')
    args = parser.parse_args(argv)
    try:
        delivery_day = date.fromisoformat(args.delivery_date)
        result = build_preview(delivery_day, datetime.now(timezone.utc))
    except (PilotUnavailable, ValueError, OSError, json.JSONDecodeError) as exc:
        print(f'NOT_AVAILABLE: {exc}', file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
