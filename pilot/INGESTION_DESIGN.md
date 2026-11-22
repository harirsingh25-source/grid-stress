# GridStress research data ingestion and model-refresh design

**Status:** PROPOSED ONLY · Not implemented, scheduled, deployed, merged, or enabled.
**Branch:** `feature/live-smard-ensemble-pilot-20261120` (draft PR #1).
**Date:** 2026-11-22 (Europe/Berlin).
**Authorship:** independent follow-on research by Hari Raj Singh; original collaborative
GridStress capstone attribution remains **Robert, Marco, Hari, Monica**.

## Latest verified evidence

- Owner Mac: **74/74 offline tests pass** at head `b0650d89e22f4878030d3306f9d3c253c3acefac`.
- Live 2026-11-21 24×13 feature capture with a local SHA-256 receipt succeeded
  on 2026-11-20. That snapshot is **current-source research only**, not a
  fitted Ridge forecast or proven source-vintage record.
- `python -m pilot.smard_history_fingerprint --month 2026-09` produced
  `ONE_MONTH_REFERENCE_MISMATCH`, 144 hours, 11 source series, pandas
  3.1.1 vs original saved pandas 3.0.5. SMARD source hash expected
  `69ea89d3a1242fa9`, current `bbdb2bdfdb920ff6`; error-series hash
  expected `3e5455dcd4711497`, current `10812dafe2c54932`.
  Causes remain **unresolved**: source revisions, transforms, CSV/dtypes or
  pandas version. No original historical data restored.
- Original `data/smard.csv` and `data/metrics/smard_forecast_errors_hourly.csv`
  are **missing** from the owner's checked Mac folders, and are Git-ignored.
  The disconnected LaCie drive was not searched.
- Original team frozen Ridge contract:
  issue at **18:00 Europe/Berlin DAY−1**; historical actuals availability
  cutoff **16:00 DAY−1** with **15:00** as last eligible hourly start;
  **36 calendar months** of training history, **7-day** model refits,
  **30-day** walk-forward tuning spacing; saved selected
  `linear_direct` alpha **0.01**. Treat these as reproduction targets,
  not proof of the current pipeline.

## Separate four independent processes

| Process | Suggested cadence after verification | Acceptance / scientific boundary |
| --- | --- | --- |
| Forecast snapshot ingestion | Daily after 18:15 Europe/Berlin, with bounded retry | Capture tomorrow's **all 23/24/25 physical hours** as delivered by SMARD. Retrieval timestamp is not a verified SMARD publication timestamp. Fail closed on missing fields or HTTP 429. |
| Observed-actual ingestion | Daily once yesterday's actuals are complete and publication-lag checks pass; revisit recent days | Keep all source readings and their first-seen retrieval times. Do not claim values were present before the original 16:00 issue cutoff without independent evidence. |
| Model fit / refit | Weekly after history and leakage tests are certified | Match original 36-month training and 7-day refit semantics. Do not retrain from unapproved revised history, or treat historical `results.joblib` as a fitted predictor. |
| Reconciliation / reporting | Monthly | Re-fetch only a bounded revision horizon, diff by source key, flag changes, gaps, DST, drift and quality. Produce **separate** model evaluation and data-quality reports; do not overwrite earlier vintages. |

Model quality may be evaluated after actuals become available; weekly model retraining
is a **proposed** initial cadence matching the team notebook, not proof that
weekly retraining is best for a newly reconstructed dataset.

## Data zones

1. **Raw snapshots (immutable):** original public source document bytes, exact
   allowlisted request path, source filter ID, response arrival time in UTC,
   retrieval/HTTP status, SHA-256, and tool/version metadata. Never overwrite;
   keep any unavailable or error response out of feature calculations.
2. **Validated observations (append-only revisions):** UTC physical
   `hour_start`, `filter_id`, `resolution`, value, unit, first and latest
   acquisition receipts, source hash and validation status. Separate forecast
   issue snapshots from actual observations. Same hour/filter may legitimately
   have **multiple vintage records**.
3. **Curated training sets (immutable versions):** input receipt IDs, feature
   definition version, calendar/annual-capacity versions, analysis cutoff,
   historical corrections policy, missingness/coverage report and
   reproducible dataset SHA-256. Never write directly into the original
   team-ignored `data/smard.csv` path during reconstruction.
4. **Model runs (separately versioned):** selected training dataset version,
   exact pipeline and library versions, fit cutoff, hyperparameters, validation
   period, held-out test period, artifact checksum and experiment metrics.
   No public "forecast" status until the model has fitted and passed the
   separate scientific release gate.

The locally saved `pilot/snapshots/` research files **do not yet implement**
these four production-grade zones. They only supply a useful first receipt.

## Initial historical backfill: a new dataset, not a recreation claim

The 2026-09 fingerprint mismatch blocks claims that re-downloaded 2019–2026
data reproduce the original team's saved result. If original files remain
unavailable, build a clearly labeled `historical_reconstruction_v2`
dataset **in a separate Git-ignored directory**:

- Iterate the eleven exact team SMARD filters, bounded by week/month and
  respecting the provider's rate limits. Track per-filter cursors and
  resumable success records; no large unbounded single-job request.
- Validate every physical hour, null, duplicate and DST behavior. Preserve
  raw source and calculation receipts.
- For **every 2019–2026 month**, compare saved team source and error
  fingerprints with the new hashes; produce a revision/processing-difference
  report. Compare pandas 3.0.5 vs 3.1.1 *offline*, if warranted, before
  attributing hash differences to SMARD revisions.
- Freeze `historical_reconstruction_v2` independently and **train/validate
  a new model on that version**. Old model MAE benchmarks must be identified
  as historical team evidence, not asserted as reproduced scores.
- Do not use new as-retrieved historical source values as if they were
  *as-issued* 18:00 forecasts or 16:00-available observations. Continuous
  prospective captures starting now are the evidence needed for forward
  point-in-time evaluation; recovered historical publication archives, if
  available, are stronger evidence for retrospective issue-time tests.

## Safety and activation gates

1. **Design review:** current 74 test receipt, one-month mismatch and
   immutable raw-source schemas acknowledged; no source-data overwrite.
2. **Local implementation only:** build one-day increment in a separate
   isolated path; offline tests for idempotency, revisions, retries, data
   loss, cutoff leakage, DST and incomplete inputs. Simulate schedules
   manually. Unit tests do not prove live network success.
3. **Local shadow run:** repeated private manual captures without published
   predictions; diagnose source latency, outages and revision behavior.
4. **Forecast research validation:** independent Ridge trained estimator,
   strict out-of-sample evaluation, then each additional model and
   validation-only ensemble weight selection, including performance
   monitoring and provenance.
5. **Explicit owner release approval:** only then decide where to run
   recurring jobs, service cost limits, cloud credentials, logging retention,
   failure notifications, hosting and whether to publish to
   hari-raj-singh.com. No cron, GitHub Actions schedule, Cloudflare Worker,
   merge, deployment or paid service is authorized by this design.

**Next exact action:** implement and offline-test a *single-day append-only
capture* with raw source receipts and data-revision records; leave its
automatic trigger off. Do not start a full-history backfill until the
September hash mismatch and allowable source cadence are understood.
