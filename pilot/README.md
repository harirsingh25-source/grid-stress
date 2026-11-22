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

## Manual append-only completed-day ingestion (22 Nov 2026; not scheduled)

The new `pilot/smard_incremental_ingestion.py` is the **first manually
invoked ingestion implementation** from `INGESTION_DESIGN.md`.
It captures **yesterday's completed delivery day** in Europe/Berlin,
with all the team's original **11 public SMARD hourly filter IDs** and
the true 23/24/25 physical UTC hours. It does **not** retrieve the
2019–2026 history or alter the original team's CSVs.

Usage after checking out the draft pilot branch:

    cd "$HOME/Repositories/grid-stress"
    git pull --ff-only origin feature/live-smard-ensemble-pilot-20261120
    ./.venv/bin/python -m unittest discover -s tests -v
    ./.venv/bin/python -m pilot.smard_incremental_ingestion

The CLI chooses the previous local day automatically (for example,
on 22 November 2026 this is 21 November 2026). You may also supply
`--day 2026-11-21` **on 22 November only**. There is no backfill
option; the narrow one-day constraint prevents unintended bulk
requests. It is **manual**, not triggered by cron, Actions or a cloud
job. The eleven source filters normally need at least one weekly
index and one hourly package each, so this makes about **22 public
GET requests**, with the project's bounded HTTPS timeout/retry and
rate-limit safeguards.

On success it writes an **append-only, owner-readable** JSON research
receipt into Git-ignored `pilot/ingestion_receipts/` and prints the
path, physical-hour count, SHA-256 and completion status. The receipt
preserves **decoded JSON source documents**, their canonical-JSON
hashes, each local receipt time in UTC, the complete normalized
hourly values or explicit null/missing-hour flags, and the original
eleven filter identifiers. It is **not byte-for-byte HTTP response
capture** and does not know when SMARD first published each value.

All reported source values and completeness counts are cross-checked
against the archived JSON documents before the final immutable file
is created. The file is written to a new temporary path and atomically
hard-linked into a final never-overwritten path; failures leave the
original source receipts untouched. An incomplete provider day may
still be archived with `INCOMPLETE_CURRENT_SOURCE_ONLY`, but it
**cannot** be used as training-eligible data.

For a second capture of the **same** completed day, the user may
explicitly supply `--compare /full/path/to/older-receipt.json`;
the new receipt records any changed/null-to-value original series
hours and the older receipt SHA-256. Neither vintage is overwritten.
If the provider fails or rate-limits, do not run in a tight loop.

**Boundaries:** no change to `data/smard.csv` or
`data/metrics/smard_forecast_errors_hourly.csv`, no automatic schedule,
no fitted model, no ensemble prediction, no AI-ready or historically
as-of-certified training table, no public website output, and no
cloud cost. Every receipt explicitly says
`original_publication_time_verified=false`,
`historic_issue_time_vintage_verified=false`,
`eligible_as_of_16h_cutoff_verified=false`,
`model_training_authorized=false`, `safe_to_publish=false`.

The last owner Mac verification was **74/74 passing** at the earlier
head, while the September 2026 saved-team fingerprint comparison
returned **mismatching** source and error hashes. The additional
**16 offline ingestion regression tests** are now included in the
draft branch, bringing the expected total to **90**, but this exact
head and the live completed-day ingestion are **not yet verified on
the Mac**. Do not claim a successful daily archive until that receipt
has been observed and checked.

## Proposed future ingestion cadence (not enabled)

The next GridStress research architecture is documented in
[`INGESTION_DESIGN.md`](INGESTION_DESIGN.md): **daily** append-only,
timestamped forecast and observed-data receipts, **weekly** Ridge/model
refitting after independent scientific validation, and **monthly**
revision/quality audits. First stage is a manually invoked single-day
capture only; **no scheduler, data-source overwrite, new cloud bill,
website publication or merge is authorized**.

The owner's latest Mac verification was **74/74 tests passed**. A
read-only 2026-09 144-hour/11-filter SMARD source comparison returned
`ONE_MONTH_REFERENCE_MISMATCH` for **both** saved team hash prefixes;
the original historical training CSVs remain missing. Consequently
the eventual historical backfill must use a newly versioned research
dataset rather than presenting revised source data as the original
training dataset, and it must not claim the old published model scores
have been independently reproduced.

## Recovering original training data: one-month provenance probe (22 Nov 2026)

The owner searched the current Mac's Documents, Desktop, Downloads and
Repositories; **neither** `data/smard.csv` nor
`data/metrics/smard_forecast_errors_hourly.csv` was found. The old
course/UniProjects directories were absent on this Mac, and only
`Macintosh HD` appeared under `/Volumes`, so the former LaCie
backup was **not mounted**. No claim is made that the files were
deleted from other machines or backups.

We must **not** invent a trained Ridge model from the 24-hour preview
receipt: the original notebook's 36-month training window requires
`data/smard.csv` and a matching hourly errors CSV, both ignored by Git.

### Minimal data-lineage comparison (no files written)

The original team's `notebooks/API-connection.ipynb` fetched exactly
11 public hourly SMARD series for **2019-01-01 to 2026-09-07
(exclusive)**, exported local wall-time timestamps, semicolon CSV and
German decimal commas. The modeling notebook `regression-models-claude`
expects **67,336** observed rows through 2026-09-06 23:00, with **93
independently saved monthly SHA-256 prefixes** for both source and
forecast-error data in `data/models/linear_direct/config.json`.

Before triggering thousands of historical SMARD API requests, run a
small **September 2026 six-day fingerprint probe**:

    cd "$HOME/Repositories/grid-stress"
    git pull --ff-only origin feature/live-smard-ensemble-pilot-20261120
    ./.venv/bin/python -m unittest discover -s tests -v
    ./.venv/bin/python -m pilot.smard_history_fingerprint --month 2026-09

This **read-only** `pilot/smard_history_fingerprint.py` script:
- requests only **one selected month**, through the verified
  bounded SMARD TLS transport (never the whole 2019–2026 history);
- uses all 11 series in the original team's declared order;
- reproduces the original local-time German-CSV read-back, required
  feature-column order, hourly error definitions and
  `pandas.util.hash_pandas_object(..., index=True)` with SHA-256
  truncation to 16 hex characters;
- compares the two newly computed month fingerprints against the
  frozen original team's `run_on` fingerprints;
- prints a structured **`ONE_MONTH_REFERENCE_MATCH`** or
  **`ONE_MONTH_REFERENCE_MISMATCH`** with both reference and new hash
  values. The result does **not** create, replace, install, publish,
  train, or schedule anything. No source CSV is written.

A full match would establish only *one-month numerical lineage*,
not the other 92 months or original day-ahead forecast issue vintages.
A mismatch is **not proof of malicious changes or a bad model**:
possible explanations include revised SMARD observations/forecasts,
differences in pandas versions, local-time/DST representation and
float/CSV round-trip semantics. Original saved config records pandas
3.0.5; the pilot Mac environment may have another version. All
outputs retain `safe_to_publish=false` and
`ridge_model_trained=false`.

If the probe fails because of SMARD HTTP 429 or another network
problem, stop and investigate that error, do not repeatedly retry.
If it succeeds, decide whether to restore the original historic files
from an authorized backup or to reconstruct a **new, separately
versioned** full history; never overwrite canonical training data
or claim old model scores without a verified dataset match.

The last verified owner Mac milestone was **64/64 tests passing** plus
a local SHA-256 research snapshot for delivery 2026-11-21. The
new one-month probe and its 10 offline tests are **not yet verified
on the owner Mac**. The expected total is **74 tests**.

## Bounded SMARD HTTPS timeout recovery (20 Nov 2026)

**Owner Mac exact-head receipt:** At `02ac7928e8874787f8252978dffd8fd4561d4a5d`,
the user pulled this branch and ran **54/54 offline tests successfully**.
The first real `pilot.ridge_feature_snapshot --save-local` run then
failed before producing an output with
`RIDGE_FEATURES_NOT_AVAILABLE: <urlopen error _ssl.c:989:
The handshake operation timed out>`. That is an HTTPS connection
timeout, **not** a model-training or feature-contract failure. The
full live 24×13 input table and immutable snapshot were **not verified
or saved** by this attempt.

The follow-on `pilot/smard_transport.py` now provides a single
security-preserving, bounded network helper:
- default Python TLS certificate verification stays **enabled**;
- reads at most 5 MB of one allowed SMARD JSON resource;
- retries **one** transient TLS/network timeout or HTTP
  502/503/504 response after a one-second pause;
- **HTTP 429 stops immediately** to respect upstream rate limiting;
- invalid JSON, missing series, certificate errors, non-SMARD paths
  and all other failures **stop**, without substituting data;
- on final timeout, the error **identifies the SMARD request path** so
  we can diagnose the failing source.

The full Ridge builder also caches identical SMARD weekly index and
package documents **within the single feature-capture call only**.
No persistent cross-day or cross-run cache is introduced, avoiding a
false sense of source vintage. It remains read-only, manual-on-request
and unfit for public forecasting until the original publication
cutoff and model are verified.

Exact Mac rerun commands (after **18:15 Europe/Berlin**):

    cd "$HOME/Repositories/grid-stress"
    git pull --ff-only origin feature/live-smard-ensemble-pilot-20261120
    python3 -m unittest discover -s tests -v
    TARGET_DAY="$(TZ=Europe/Berlin date -v+1d +%F)"
    python3 -m pilot.ridge_feature_snapshot --delivery-date "$TARGET_DAY" --save-local

If the live request still fails, **do not run it in a tight loop**.
Report the new HTTP status or source path to diagnose the issue. Do
not disable TLS/certificate checks, install a custom root CA, alter
SMARD API hosts, bypass publication cutoffs or switch on Cloudflare.

The new transport tests are **offline**. The exact-head local Python
test suite, real full-source request and browser checks must be run
before calling this fix verified. The complete numerical table, if
captured, must still carry
`RIDGE_13_FEATURES_CURRENT_SNAPSHOT_UNVERIFIED`,
`ridge_predictions=null`, `ensemble_predictions=null`, and
`safe_to_publish=false`. Source vintage, independently trained Ridge
inference, ensemble and daily automation remain outstanding.

## First full original Ridge feature-table prototype (current API snapshots ONLY)

**Exact verified starting point:** on **20 November 2026**, the owner
fast-forwarded the pilot branch to `d31c6c099aad5c4e410474577b54c5b0be81fc7d`.
The owner Mac confirmed **37/37 offline tests passing** and received
all **49 historical residual-load observations** from the live SMARD API
for delivery **21 November 2026**. The current-source actuals retrieval
was at 19:43 CET, **after** the original 16:00 information cutoff.
These observations are **not** historically as-of certified.

The new `pilot/ridge_feature_snapshot.py` goes beyond the coverage
check and reconstructs the **13 numeric columns of the original team
Ridge direct input schema**, using the source identifiers in the team's
`notebooks/API-connection.ipynb` and formulas in its modeling and
forecast-metrics notebooks:

- **6 calendar + target-forecast inputs:** hour, weekday, month,
  weekend, target SMARD grid load, target SMARD wind+solar;
- **1 nationwide German holiday flag:** independent deterministic
  calendar; equivalence to the team's `holidays.country_holidays("DE")`
  is **not yet certified**;
- **3 observed residual inputs:** same-local-hour `DAY−2` and
  `DAY−7`, plus the 15:00 residual actual on the issue day;
- **2 recent forecast-error inputs:** the preceding 24 complete hours
  ending at issue-day 15:00, using `forecast − actual` for grid load
  and wind+solar, as in the original team's sign convention;
- **1 published installed capacity input:** onshore+offshore wind and
  solar from the issue-year 1 January through the issue-day probes.
  This spot check cannot prove complete historical publication vintage.

The adapter is deliberately restricted to **ordinary 24-hour target
and history days** until the team's naive local-time timestamp
semantics across DST have been reproduced exactly. It rejects missing,
duplicate, nonfinite, negative physical component inputs, inconsistent
capacity probes and unsupported URL paths. The main script uses
read-only requests with small bounded weekly-package windows.

**Run locally on the Mac**, after 18:15 Berlin time on the day before
the target day (example specifically for Friday 20 Nov 2026):

    cd "$HOME/Repositories/grid-stress"
    git pull --ff-only origin feature/live-smard-ensemble-pilot-20261120
    python3 -m unittest discover -s tests -v
    python3 -m pilot.ridge_feature_snapshot --delivery-date 2026-11-21

To **opt in** to a local immutable research snapshot, run the same
command with `--save-local`:

    python3 -m pilot.ridge_feature_snapshot --delivery-date 2026-11-21 --save-local

The second command writes one original, owner-readable JSON file under
`pilot/snapshots/` with a SHA-256 receipt; `pilot/.gitignore`
excludes these snapshots from version control. Overwriting the same
snapshot is not allowed. No capture is scheduled, uploaded, publicly
linked or deployed; snapshots accumulate only on a deliberately
invoked local run. Output preserves the source and capture timestamp,
forecast issue and cutoff, source input values and model identity.

**Scientific status stays blocked:** even with all 13 finite numerical
feature values, `status=RIDGE_13_FEATURES_CURRENT_SNAPSHOT_UNVERIFIED`,
`historical_actuals_as_of_cutoff_verified=false`,
`forecast_issue_vintage_verified=false`,
`capacity_publication_vintage_verified=false`,
`holiday_calendar_equivalence_verified=false`,
`trained_ridge_estimator_available=false`,
`ridge_predictions=null`, `ensemble_predictions=null`, and
`safe_to_publish=false`. This prototype uses currently served
SMARD values, which can be revised or published after the
information cutoff; **it is not a trustworthy point-in-time
backtest or a trained model forecast**.

The next required work is source-vintage receipts at the actual
issuance time, reconstruction of the original full historical training
frame, 36-month training window, seven-day refit and strictly held-out
validation; only then may actual Ridge inference be privately compared
with SMARD. The other five fitted models and regime-weighted ensemble
must independently pass the same evidence gates.

**New test receipt status:** 11 synthetic feature-extraction tests plus
6 immutable-capture tests have been added on top of the last 37
owner-verified tests. **54 are expected but have not yet been executed
on this draft head**. Do not mistake static GitHub code review
for a passing Python suite or an end-to-end model run.

## Original SMARD residual-load actuals: coverage preflight (new, read-only)

**Verified user Mac receipt (20 November 2026):** the exact previous
draft head `8d8274de07b873426166743061e1a4367edd4a97` was pulled
successfully and **28 of 28 offline tests passed**. The live Ridge
readiness command for delivery 2026-11-21 returned 24 complete target
hours, the original frozen `linear_direct` 13-feature configuration
(`alpha=0.01`), six day-ahead/calendar inputs available and seven
missing. It correctly reported `RIDGE_FEATURES_INCOMPLETE`,
`trained_estimator_available=false`, no Ridge/ensemble predictions and
`safe_to_publish=false`.

**Next research input check:** the team's original API notebook identifies
SMARD filter **4359** as **observed residual load**. The new
`pilot/smard_actuals_preflight.py` independently fetches only this
public hourly filter, for the original Ridge features
`rl_lag_48h`, `rl_lag_168h`, and `rl_last_available`.
For an ordinary 24-hour delivery day, the expected source-hour set is
**24 + 24 + 1 = 49 distinct observations**. The final hour starts
at **15:00 Europe/Berlin** on the day before delivery, per the original
team's 18:00 issue/16:00 actuals cutoff convention.

To inspect source completeness on the development Mac, after a
successful tomorrow-only SMARD preflight and **after 18:15 local**:

    cd "$HOME/Repositories/grid-stress"
    git pull --ff-only origin feature/live-smard-ensemble-pilot-20261120
    python3 -m unittest discover -s tests -v
    python3 -m pilot.smard_actuals_preflight --delivery-date 2026-11-21

The date above is applicable only to the 20 November 2026 issuance;
on other dates, supply the actual next day in `Europe/Berlin`.
The new nine tests use entirely synthetic weekly-package SMARD
responses; they verify all 49 requested hours, rejection of missing,
duplicate and null values, negative residual acceptance, endpoint
allowlisting and DST refusal.

**Critical scientific boundary:** successful API retrieval only
demonstrates that hourly observations are **currently served**; it
does **not** demonstrate they were originally **published at or before**
the 16:00 cutoff, because the public API may have late publications or
revisions. This separate read-only audit is not included as additional
**validated** Ridge features, does not alter the 6/13 readiness
result, does not fit a model and never schedules or publishes anything.
DST-day local-time lag equivalence with the team's naive timestamp
index is deliberately refused pending independent verification.
The next engineering work remains reconstructing trustworthy
`as_of` snapshots, validated lag features, recent forecast errors,
calendar holiday and capacity publication rules, and training the
actual fitted estimator.

## Ridge model feature-readiness gate (new, read-only)

The team saved `data/models/linear_direct/config.json` lists its original
Ridge-direct model as **13 specific features**, in a fixed order, with
`alpha=0.01`. This is a **tuning/configuration artifact**, not a
fitted-estimator serialization. Do not treat it or historical
`results.joblib` data as a real live predictor.

A new standard-library-only CLI reads that original JSON and today's
fresh SMARD preview, checks every physical target hour and both component
forecast values, and gives a conservative **feature-readiness report**:

    cd "$HOME/Repositories/grid-stress"
    git pull --ff-only origin feature/live-smard-ensemble-pilot-20261120
    python3 -m unittest discover -s tests -v
    python3 -m pilot.ridge_readiness --delivery-date 2026-11-21

The example command is relevant on **20 November 2026 after 18:15
Europe/Berlin**. On another day use that day's *next* date. It requires
no installation beyond the project's existing Python 3.11 and makes
read-only public SMARD API requests. The new 8 tests are offline and
exercise 13-feature schema consistency, selected hyperparameter,
cutoff/lag rule, missing and invalid hours, DST and fail-closed status.

**Ready from current two SMARD input series (6/13):** `hour`,
`dow`, `month`, `is_weekend`, `fc_grid_load`,
`fc_gen_wind_solar`. This is only input *availability*, not a
point-in-time model forecast.

**Not reconstructed (7/13):** `holiday`,
`rl_lag_48h`, `rl_lag_168h`, `rl_last_available`,
`err_grid_load_recent`, `err_renewables_recent`,
`cap_total`. These need independently verified German holiday
calendar, past actual residual-load hours, the recent 24-hour
SMARD forecast-error calculation and installed-capacity publication
rule. At day-ahead issue time 18:00 on DAY−1, the original team
uses a 2-hour actuals lag, a 16:00 availability cutoff and the
15:00 last eligible actual hour.

The tomorrow-only Streamlit view also includes an
**Original Ridge model · feature readiness** panel, which reports
**6/13 available** and displays a collapsible table naming the seven
missing inputs. It is informative rather than predictive; a chart of
SMARD input components must not be mistaken for an ML forecast.

A report must say `RIDGE_FEATURES_INCOMPLETE`, keep
`trained_estimator_available=false`, `ridge_predictions=null`,
`ensemble_predictions=null`, `source_vintage_verified=false`
and `safe_to_publish=false`. Do **not** convert this into a public
Ridge prediction, operational warning or live ensemble yet. This
readiness gate does not itself train or fit any model, add cron,
publish a dashboard or change the original team application.

In addition to the seven feature values, faithful future model
reproduction requires verifying previous-day forecast availability
at/after the 16:00 cutoff, the original 36-month training/refit
protocol, source snapshot provenance, and a real fitted Ridge
pipeline validated on strictly out-of-sample dates.

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
