# Live SMARD + Ensemble Research Pilot (NOT DEPLOYED)

This directory is a **new, isolated experiment in Hari Raj Singh's public GitHub fork** of the original collaborative GridStress Team Capstone. It does not change the original seven-page team Streamlit app, notebooks, or historical saved results.

## Where the eventual live research should appear

After independently verifying scheduled model inference and publication controls, add a clearly-labelled **Live Research Forecast** section to the website's Team Capstone page at https://hari-raj-singh.com/general/gridstress/capstone/ . This would link to a separate data dashboard showing tomorrow's hour-by-hour SMARD baseline, individual Ridge/LightGBM/XGBoost/Random Forest predictions, and the validated regime-weighted ensemble, with timestamps, uncertainties, source provenance and NOT_AVAILABLE states. The existing team application remains a historical collaborative project.

## Milestone 0: Implemented and locally tested

- Source: Bundesnetzagentur | SMARD.de, via the public weekly-package API used by notebooks/API-connection.ipynb.
- Fields: filter 411 is the published grid-load forecast; filter 5097 is the published wind + solar forecast. The component baseline is load minus wind+solar. This baseline is NOT an independently trained GridStress prediction.
- The read-only script pilot/smard_daily_pilot.py checks only tomorrow's German local delivery date, refuses calls before 18:15 on the previous day, accepts only allowlisted SMARD endpoints, caps fetched weekly packages, verifies every physical hour, and refuses invalid/missing values. It treats daylight saving time explicitly (23/24/25 real UTC hours).
- The output always says RESEARCH_PREVIEW_ONLY, source_vintage_verified false, model_inference NOT_AVAILABLE, ensemble_forecast null and public_release_authorized false.
- No scheduler, public route, infrastructure, storage, AI service, model execution, auto-retraining, or paid cloud resource is created.

### Use in VS Code

Open this fork's branch feature/live-smard-ensemble-pilot-20261120, open a terminal at the repository root, and run:

    python -m unittest discover -s tests -v
    python -m pilot.smard_daily_pilot --delivery-date YYYY-MM-DD

The second command is only appropriate after **18:15 Europe/Berlin**, where YYYY-MM-DD is the actual **next local calendar day**. It makes real, read-only SMARD HTTP requests, prints research-preview JSON, and creates no files. Before that time, missing data, or any invalid response, it exits with NOT_AVAILABLE and nonzero status. Tests use local synthetic responses and require no network.

## Local Streamlit preview (already implemented, NOT HOSTED)

File: `pilot/smard_streamlit.py`. This is a **separate local read-only UI** that plots the two SMARD component forecasts and their arithmetic residual for a **completed historical day**. It deliberately **does not** show a predicted ensemble or live publication, does not call the pilot's tomorrow-only pathway and does not change the original team Streamlit app.

From the repo root, without VS Code, run:

    python3 -m unittest discover -s tests -v
    python3 -m venv .venv
    ./.venv/bin/python -m pip install --upgrade pip
    ./.venv/bin/python -m pip install streamlit pandas plotly
    ./.venv/bin/python -m streamlit run pilot/smard_streamlit.py

**Intel Mac wheel workaround, local research only.** On some Intel Macs,
pip chooses a recent PyArrow source archive instead of a compatible binary
wheel. Source compilation can fail with `can't find Rust compiler` while
building a transitive `libcst` dependency. The Streamlit dependency
allows PyArrow 17.0.0, which provides a CPython 3.11 wheel for macOS
10.15+ x86-64 (unlike recent PyArrow wheels that require macOS 12+).
Only if your `python3` reports CPython 3.11 and `uname -m` reports
`x86_64`, prefer this **non-production** workaround, which rejects
source archives rather than compiling native dependencies:

    cd "$HOME/Repositories/grid-stress"
    ./.venv/bin/python -m pip install --upgrade pip
    ./.venv/bin/python -m pip install --only-binary=:all: "pyarrow==17.0.0" "streamlit==1.67.0" "pandas==3.1.1" "plotly==7.1.0"
    ./.venv/bin/python -m pip check
    ./.venv/bin/streamlit run pilot/smard_streamlit.py --server.address 127.0.0.1

If no compatible wheel is found, **stop** and report
`sw_vers -productVersion`, `uname -m` and `./.venv/bin/python -V`
rather than installing Rust or using `--no-binary`.
PyArrow 17 is a compatibility fallback for a **localhost-only preview**,
not a production security baseline. A hosted research dashboard must use
a supported environment and freshly reviewed dependencies.

On the Mac that exposed the issue (2026-11-20), the full test suite
passed 14/14, but Streamlit installation **failed before launch** on
`pyarrow 26.0.1` source build / `libcst` Rust requirement. The
workaround above is proposed; do not count the UI as verified until
its package install, import, launch and first browser rendering succeed.

Then visit the loopback URL printed by Streamlit (typically http://localhost:8501). Select a completed historical day such as 2026-11-19 and click **Fetch SMARD historical inputs**. The explorer prints source provenance, UTC acquisition time, full-hour coverage, interactive Plotly lines, an hourly table and an optional CSV download. Only the deliberate button click fetches data, with a ten-minute cache. Streamlit's port remains local unless you deliberately configure network access. Keep it local-only for this pilot.

**Not a historical forecast-vintage archive:** the current SMARD API can return revised values. The page describes a *historical input preview*; no claims of backtested skill, operational grid risk, a 2026-11-21 model forecast, or daily automatic service are supported.

## Two local Streamlit views (20 November 2026)

The same `pilot/smard_streamlit.py` now offers a choice between
**Past-day SMARD API snapshot** and **Tomorrow's SMARD input preview**.
The tomorrow mode calls the already-tested `build_preview` function
**only after 18:15 Europe/Berlin** and **only after a manual Fetch click**.
It checks the complete 23/24/25 physical-hour delivery day and shows
SMARD load, SMARD wind+solar and the arithmetic residual side by side,
with a local-time Plotly graph, table, and optional CSV export.

An actual Mac user run at **20 November 2026 18:17 CET** returned all
24 SMARD grid-load and wind/solar forecast values for **21 November 2026**
from the official public API, with `RESEARCH_PREVIEW_ONLY` and no ensemble.
The new UI now exposes a manual on-demand view of those inputs, but
**its post-change browser render has not yet been certified**.

When restarting, make sure the previous Streamlit terminal is still
running or restart it and leave it open:

    cd "$HOME/Repositories/grid-stress"
    git pull --ff-only origin feature/live-smard-ensemble-pilot-20261120
    python3 -m unittest discover -s tests -v
    ./.venv/bin/streamlit run pilot/smard_streamlit.py --server.address 127.0.0.1

Enter `http://127.0.0.1:8501` directly in Safari. Safari's
`can't connect` when the listener process has exited is a local
server-availability issue, not evidence of an SMARD failure.
The new mode is **on demand, not a recurring job**; the six fitted
estimators, ensemble weights, immutable source vintages, automatic
retraining, regular scheduler and public dashboard still do not exist.
No recurring API traffic, new Cloudflare usage or website release is
introduced. Retain the prominent original four-person team attribution.

## Original four-person team credit and import fix (20 Nov 2026)

The canonical original Streamlit `streamlit/app_pages/about.py` lists
the **four human team members** as **Robert, Marco, Hari and Monica**.
The independent pilot displays these names prominently at the top
(before any data fetch), links to the [original team capstone](https://github.com/fruchtgummikauer/grid-stress),
and separately identifies Hari's research fork. It never represents
the other three team members as authors or approvers of the new pilot.
Only the first names supplied by the original team are used; surnames are
not invented. The original team app's own `Who are we?` page remains intact.

The first user browser launch succeeded in installing Streamlit but hit
`ModuleNotFoundError: No module named 'pilot'`. Streamlit's script runner
did not include the repository root on the Python import path. The pilot
entrypoint now derives that root from its own source file and inserts it
before package imports. This is contained to the pilot app.

To pick up the fix, stop the existing local Streamlit process with
**Ctrl+C**, then use these commands from the repository root:

    git pull --ff-only origin feature/live-smard-ensemble-pilot-20261120
    python3 -m unittest discover -s tests -v
    ./.venv/bin/streamlit run pilot/smard_streamlit.py --server.address 127.0.0.1

Open `http://127.0.0.1:8501` in your browser. The explicit
`--server.address 127.0.0.1` binds the preview to the Mac itself
rather than exposing the port to other devices on the local network,
which is important because the earlier default server log displayed
a LAN Network URL. No reinstall or new service is needed if
`pip check` already passed.

**Verification status:** User Mac reported 14/14 pre-fix tests green and
successful Streamlit package installation, but a browser import failure.
The 3 new import/credit contract tests and successful post-fix browser
render still require a local rerun. Do not call the UI verified until then.

## Limits to understand before going live

- **Historical revision / forecast vintage:** Public SMARD endpoints can contain revisions. A post-18:00 fetch alone cannot prove each series represents exactly the values originally available at the issue time. We need immutable snapshots with acquisition receipts, publication-time checks, source digests and backtests.
- **Saved model files:** The team's data/models/*/results.joblib contain saved historical run results, not a verified online inference endpoint. Do NOT load unfamiliar joblib/pickle files: deserialization may execute code. Reconstruct verified fitted estimators with trusted dependencies and provenance.
- **Ensemble:** The historic regime-weighted ensemble learns weights from validation data and includes SMARD among its default members. It must not select weights or thresholds from the test year or silently fall back to a different model.
- **Scope:** National residual-load forecasts are NOT operational warnings about local congestion, grid security, frequency or blackout risk. No forecast may be presented as current if the pipeline failed or source data are stale.

## Planned milestones (not yet performed)

1. Observe and validate actual SMARD API responses and the publication/vintage contract, including DST and revisions.
2. Reproduce the historical 36-month training windows, information cutoff and source feature set against verified original data, then train and version the six true estimators.
3. Prove complete hourly inference from live inputs and an independently validated, fixed regime-weighted ensemble.
4. Add a bounded, **private** daily shadow-run after publication and evaluate forecasts after actuals arrive. Do not schedule or publish until this is verified.
5. Implement a stable, low-cost read-only dashboard and integrate an attributed Team Capstone link only after separate authorization, cost safeguards and route/browser checks.

## Provenance

Original team repository: https://github.com/fruchtgummikauer/grid-stress (MIT). Personal archival fork: https://github.com/harirsingh25-source/grid-stress. The independent GridStress V1/V2 research is separate. This pilot is not a claim that the original team developed or approved a live operational service.

Do not commit private API tokens, raw personal data, unreviewed model binaries or snapshots mislabelled as current; do not modify the main website, its MDR publication guards or Cloudflare deployments from this branch.
