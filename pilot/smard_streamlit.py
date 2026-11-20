"""Local-only Streamlit SMARD historical-data explorer.

Run at the repository root after installing its declared Streamlit dependencies:
    python -m streamlit run pilot/smard_streamlit.py

This app makes on-demand, read-only SMARD requests. It never schedules work,
loads model binaries, computes an ML forecast, or publishes to hari-raj-singh.com.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import sys

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# Streamlit executes this file as a script and puts pilot/ on sys.path, not
# necessarily the repository root. Make the package imports independent of
# the shell's PYTHONPATH while keeping the existing pilot modules unchanged.
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from pilot.smard_daily_pilot import LOCAL, PilotUnavailable
from pilot.smard_historical_snapshot import build_historical_snapshot
from pilot.team_credits import (
    ORIGINAL_TEAM_MEMBERS, ORIGINAL_TEAM_REPOSITORY, PERSONAL_RESEARCH_FORK,
)


st.set_page_config(
    page_title="GridStress | SMARD research preview",
    page_icon="⚡",
    layout="wide",
)

st.title("⚡ GridStress | SMARD input explorer")
st.caption("Research prototype · German electricity market · local-only preview")

st.markdown(
    "**Original collaborative GridStress Team Capstone (neuefische): "
    + " · ".join(ORIGINAL_TEAM_MEMBERS)
    + ".**"
)
st.caption(
    "This experimental SMARD explorer is independent follow-on work in Hari's "
    "personal research fork. The original team is credited for the capstone; "
    "this pilot does not imply the other members developed or endorsed it."
)
st.markdown(
    f"[Original team repository]({ORIGINAL_TEAM_REPOSITORY}) · "
    f"[Personal research fork]({PERSONAL_RESEARCH_FORK})"
)

st.warning(
    "**Historical SMARD component forecasts only.** The API may serve revised "
    "values, so this is not an archived issue-time forecast or a live, tested "
    "GridStress model. No ensemble predictions, automatic daily updates, or "
    "public deployment have been enabled.",
    icon="⚠️",
)

today = datetime.now(LOCAL).date()
latest_historical = today - timedelta(days=1)
if latest_historical < date(2019, 1, 1):
    st.error("No eligible historical date.")
    st.stop()

selected_day = st.date_input(
    "Historical delivery date (Europe/Berlin)",
    value=latest_historical,
    min_value=date(2019, 1, 1),
    max_value=latest_historical,
    help="Only completed days. Dates are selected in Germany's local timezone.",
)

if not st.button("Fetch SMARD historical inputs", type="primary"):
    st.info("Choose a completed day and press **Fetch SMARD historical inputs**.")
    st.stop()


@st.cache_data(ttl=600, show_spinner=False)
def cached_historical_snapshot(day_iso: str) -> dict:
    day = date.fromisoformat(day_iso)
    return build_historical_snapshot(day, datetime.now(timezone.utc))


try:
    with st.spinner("Fetching two public SMARD component forecast series…"):
        snapshot = cached_historical_snapshot(selected_day.isoformat())
except (PilotUnavailable, ValueError, OSError, KeyError) as exc:
    st.error(f"SMARD data unavailable: {exc}")
    st.stop()

rows = snapshot["hours"]
frame = pd.DataFrame(rows)
frame["hour_start_europe_berlin"] = pd.to_datetime(
    frame["hour_start_europe_berlin"], utc=True
).dt.tz_convert(LOCAL)
frame = frame.sort_values("hour_start_utc")

st.caption(
    f"Retrieved at {snapshot['retrieved_at_utc']} · "
    f"Delivery day {snapshot['delivery_date']} · "
    "Bundesnetzagentur / SMARD.de"
)

kpi1, kpi2, kpi3 = st.columns(3)
kpi1.metric("Hourly load inputs", f"{len(frame)}/{len(frame)}")
kpi2.metric("Hourly wind + solar inputs", f"{len(frame)}/{len(frame)}")
kpi3.metric("Trained ensemble", "Not available")

fig = go.Figure()
for key, label, color in [
    ("forecast_load_mwh", "SMARD forecast: grid load", "#D94F43"),
    ("forecast_wind_solar_mwh", "SMARD forecast: wind + solar", "#1A9C89"),
    ("derived_component_residual_mwh", "Derived load − renewables", "#5368C5"),
]:
    fig.add_trace(
        go.Scatter(
            x=frame["hour_start_europe_berlin"],
            y=frame[key],
            mode="lines+markers",
            name=label,
            line={"color": color, "width": 2},
            hovertemplate="%{x|%Y-%m-%d %H:%M %Z}: %{y:,.1f} MWh<extra>%{fullData.name}</extra>",
        )
    )
fig.update_layout(
    title="Historical SMARD forecast components (current API snapshot)",
    xaxis_title="Germany local time (Europe/Berlin)",
    yaxis_title="MWh per hour",
    legend={"orientation": "h", "y": -0.25},
    margin={"t": 55, "r": 25, "b": 100, "l": 25},
)
st.plotly_chart(fig, use_container_width=True)

st.subheader("Hourly source values")
st.dataframe(
    frame[
        [
            "hour_start_europe_berlin",
            "forecast_load_mwh",
            "forecast_wind_solar_mwh",
            "derived_component_residual_mwh",
        ]
    ],
    hide_index=True,
    use_container_width=True,
)

st.download_button(
    "Download historical SMARD component preview (CSV)",
    data=frame.to_csv(index=False).encode("utf-8"),
    file_name=f"smard_historical_components_{selected_day.isoformat()}.csv",
    mime="text/csv",
)

st.caption(
    "Source: Bundesnetzagentur SMARD (filter 411, grid-load forecast; filter 5097, "
    "wind+solar forecast). The derived residual is an arithmetic difference; "
    "it is not a separately fitted model or proof of SMARD's issue-time "
    "published residual-load forecast."
)
st.caption(
    "GridStress Team Capstone: " + ", ".join(ORIGINAL_TEAM_MEMBERS)
    + " (neuefische). Data: Bundesnetzagentur | SMARD.de. "
    + "Independent local research pilot; not the original team's deployment."
)
