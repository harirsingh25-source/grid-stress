"""Manual, one-completed-day append-only SMARD research ingestion (NO scheduler).

Uses the original team's eleven DE/hour filter identifiers. The output is an
immutable, Git-ignored SOURCE RECEIPT, not a validated training set or a
point-in-time as-issued forecast. Retrieval times do not prove publication
times. No fitted model, API credentials, cron, cloud or website side effects.

    python3 -m pilot.smard_incremental_ingestion
    python3 -m pilot.smard_incremental_ingestion --day 2026-11-21
    python3 -m pilot.smard_incremental_ingestion --compare /path/to/prior-receipt.json

V1 only accepts the PREVIOUS completed Europe/Berlin day. This deliberately
blocks full-history backfill or automatic catch-up until a separate design
and verification gate. Repeated manual captures yield separate vintages.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from .smard_daily_pilot import LOCAL, daily_hours_utc
from .smard_history_fingerprint import ORIGINAL_SERIES
from .smard_transport import PilotUnavailable, fetch_public_smard_json

FILTERS = {filter_id: key for filter_id, _, key in ORIGINAL_SERIES}
SIGNED_FILTERS = {4359, 4362}  # Observed and forecast residual load can be negative.
MAX_PACKAGES = 3
MAX_RECEIPT_BYTES = 8_000_000
DEFAULT_DIRECTORY = Path(__file__).resolve().parent / "ingestion_receipts"
ACCEPTED_STATUSES = {
    "COMPLETE_CURRENT_SOURCE_ONLY", "INCOMPLETE_CURRENT_SOURCE_ONLY"
}


def utc_stamp(value: datetime) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise PilotUnavailable("capture timestamps must be timezone-aware")
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds")


def canonical_json(value) -> bytes:
    try:
        return (json.dumps(
            value, ensure_ascii=False, sort_keys=True, allow_nan=False,
            separators=(",", ":")
        ) + "\n").encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise PilotUnavailable("invalid, non-JSON source capture") from exc


def _source_get(path: str) -> dict:
    return fetch_public_smard_json(
        path, user_agent="GridStress-manual-daily-ingestion/0.1"
    )


def capture_completed_day(
    day: date, now: datetime, get_json=_source_get,
    clock=None,
) -> dict:
    """Capture 11 unmodified decoded JSON API documents plus UTC-normalized rows.

    The *decoded JSON documents* are preserved and individually hashed.
    They are NOT byte-for-byte raw HTTP response bodies; TLS/HTTP headers
    and origin publication timestamps are not available via this helper.
    Nothing is written if any source/network/schema request raises.
    """
    if not isinstance(day, date) or isinstance(day, datetime):
        raise PilotUnavailable("delivery day must be a date")
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
        raise PilotUnavailable("as-of must be timezone-aware")
    local_now = now.astimezone(LOCAL)
    if day != local_now.date() - timedelta(days=1):
        raise PilotUnavailable("V1 captures only yesterday's completed Europe/Berlin day")
    if not callable(get_json):
        raise PilotUnavailable("source client must be callable")
    clock = clock or (lambda: datetime.now(timezone.utc))
    hours = daily_hours_utc(day)
    wanted = set(hours)
    lower_ms = int(hours[0].timestamp() * 1000)
    upper_ms = int((hours[-1] + timedelta(hours=1)).timestamp() * 1000)
    sources = []
    values = {hour: {} for hour in hours}
    source_summary = []

    def acquire(path: str) -> dict:
        # Only fixed filter/index paths constructed here; shared transport
        # independently enforces strict SMARD HTTPS URL allowlisting.
        document = get_json(path)
        if not isinstance(document, dict):
            raise PilotUnavailable("SMARD document must be a JSON object")
        payload = canonical_json(document)
        if len(payload) > 5_000_000:
            raise PilotUnavailable("decoded SMARD source document exceeds size bound")
        sources.append({
            "path": path,
            "retrieved_at_utc": utc_stamp(clock()),
            "sha256_canonical_json": hashlib.sha256(payload).hexdigest(),
            "document": document,
        })
        return document

    for filter_id, label, key in ORIGINAL_SERIES:
        index = acquire(f"/{filter_id}/DE/index_hour.json").get("timestamps")
        if (
            not isinstance(index, list) or not index
            or any(type(x) is not int for x in index)
            or len(set(index)) != len(index)
        ):
            raise PilotUnavailable(f"invalid weekly SMARD index for {filter_id}")
        packages = sorted(index)
        needed = [
            stamp for i, stamp in enumerate(packages)
            if stamp < upper_ms
            and (i + 1 == len(packages) or packages[i + 1] > lower_ms)
        ]
        if not 1 <= len(needed) <= MAX_PACKAGES:
            raise PilotUnavailable(f"unexpected weekly package count for {filter_id}")
        seen = {}
        for package in needed:
            path = f"/{filter_id}/DE/{filter_id}_DE_hour_{package}.json"
            rows = acquire(path).get("series")
            if not isinstance(rows, list):
                raise PilotUnavailable(f"invalid hourly SMARD series for {filter_id}")
            for pair in rows:
                if not isinstance(pair, (list, tuple)) or len(pair) != 2:
                    raise PilotUnavailable("invalid hourly source pair")
                millis, raw = pair
                if type(millis) is not int or millis % 3_600_000:
                    raise PilotUnavailable("invalid hourly UTC source timestamp")
                if not lower_ms <= millis < upper_ms:
                    continue
                hour = datetime.fromtimestamp(millis / 1000, tz=timezone.utc)
                if hour not in wanted or hour in seen:
                    raise PilotUnavailable(f"duplicated or unexpected source hour for {filter_id}")
                if raw is not None and (
                    type(raw) not in (float, int)
                    or not math.isfinite(raw)
                    or (filter_id not in SIGNED_FILTERS and raw < 0)
                ):
                    raise PilotUnavailable(f"invalid SMARD source value for {filter_id}")
                seen[hour] = None if raw is None else float(raw)
        missing_timestamps = len(wanted - seen.keys())
        nulls = sum(value is None for value in seen.values())
        for hour in hours:
            values[hour][key] = seen.get(hour)
        source_summary.append({
            "filter_id": filter_id,
            "original_header": label,
            "field": key,
            "retrieved_hour_count": len(seen),
            "missing_hour_count": missing_timestamps,
            "null_value_count": nulls,
            "complete": missing_timestamps == 0 and nulls == 0,
        })

    complete = all(spec["complete"] for spec in source_summary)
    records = [
        {
            "hour_start_utc": hour.isoformat(),
            "hour_start_europe_berlin": hour.astimezone(LOCAL).isoformat(),
            "values": values[hour],
        }
        for hour in hours
    ]
    return {
        "schema_version": 1,
        "status": "COMPLETE_CURRENT_SOURCE_ONLY" if complete
                  else "INCOMPLETE_CURRENT_SOURCE_ONLY",
        "research_mode": "MANUAL_CURRENT_API_COMPLETED_DAY",
        "delivery_date": day.isoformat(),
        "captured_at_utc": utc_stamp(clock()),
        "source": "Bundesnetzagentur | SMARD.de",
        "region": "DE",
        "resolution": "hour",
        "hour_count": len(hours),
        "original_filter_ids": [item[0] for item in ORIGINAL_SERIES],
        "source_document_count": len(sources),
        "all_series_complete": complete,
        "source_summary": source_summary,
        "hours": records,
        "source_documents_decoded_json": sources,
        "source_bytes_exactly_preserved": False,
        "original_publication_time_verified": False,
        "historic_issue_time_vintage_verified": False,
        "eligible_as_of_16h_cutoff_verified": False,
        "original_team_dataset_equivalent": False,
        "model_training_authorized": False,
        "model_predictions": None,
        "safe_to_publish": False,
        "revision_comparison": None,
    }


def receipt_payload(report: dict) -> bytes:
    """Require explicit nonpublishable provenance and complete structural schema."""
    if (
        report.get("schema_version") != 1
        or report.get("status") not in ACCEPTED_STATUSES
        or report.get("research_mode") != "MANUAL_CURRENT_API_COMPLETED_DAY"
        or report.get("model_training_authorized") is not False
        or report.get("original_publication_time_verified") is not False
        or report.get("historic_issue_time_vintage_verified") is not False
        or report.get("eligible_as_of_16h_cutoff_verified") is not False
        or report.get("original_team_dataset_equivalent") is not False
        or report.get("safe_to_publish") is not False
        or report.get("source_bytes_exactly_preserved") is not False
        or report.get("model_predictions") is not None
        or report.get("original_filter_ids") != [item[0] for item in ORIGINAL_SERIES]
    ):
        raise PilotUnavailable("unsafe or noncanonical research ingestion receipt")
    day = date.fromisoformat(report["delivery_date"])
    expected = daily_hours_utc(day)
    rows = report.get("hours")
    summary = report.get("source_summary")
    docs = report.get("source_documents_decoded_json")
    if (
        not isinstance(rows, list) or len(rows) != len(expected)
        or not isinstance(summary, list) or len(summary) != len(ORIGINAL_SERIES)
        or not isinstance(docs, list) or len(docs) != report.get("source_document_count")
        or report.get("hour_count") != len(expected)
        or report.get("all_series_complete") is not (report["status"] == "COMPLETE_CURRENT_SOURCE_ONLY")
    ):
        raise PilotUnavailable("incomplete research ingestion receipt schema")
    for row, hour in zip(rows, expected):
        if not isinstance(row, dict) or row.get("hour_start_utc") != hour.isoformat():
            raise PilotUnavailable("receipt has wrong UTC physical hours")
        if row.get("hour_start_europe_berlin") != hour.astimezone(LOCAL).isoformat():
            raise PilotUnavailable("receipt has wrong local hour mapping")
        if not isinstance(row.get("values"), dict) or set(row["values"]) != set(FILTERS.values()):
            raise PilotUnavailable("receipt has wrong SMARD source keys")

    # Reconstruct every requested normalized value from the archived source
    # documents, not just the stored output table. A checksum alone cannot
    # detect a table accidentally derived from different API responses.
    seen_doc_paths = set()
    index_filters = set()
    package_counts = {fid: 0 for fid in FILTERS}
    source_values = {fid: {} for fid in FILTERS}
    wanted = set(expected)
    for doc in docs:
        if not isinstance(doc, dict) or not isinstance(doc.get("document"), dict):
            raise PilotUnavailable("invalid decoded source document")
        computed = hashlib.sha256(canonical_json(doc["document"])).hexdigest()
        if doc.get("sha256_canonical_json") != computed:
            raise PilotUnavailable("source document checksum mismatch")
        path = doc.get("path")
        match = re.fullmatch(
            r"/([0-9]+)/DE/(index_hour|([0-9]+)_DE_hour_([0-9]+))\.json",
            path if isinstance(path, str) else "",
        )
        if (
            match is None or int(match.group(1)) not in FILTERS
            or (match.group(3) is not None and match.group(3) != match.group(1))
            or path in seen_doc_paths
        ):
            raise PilotUnavailable("unexpected or duplicate source-document request path")
        seen_doc_paths.add(path)
        fid = int(match.group(1))
        retrieved = doc.get("retrieved_at_utc")
        if not isinstance(retrieved, str):
            raise PilotUnavailable("source receipt retrieval time missing")
        try:
            parsed = datetime.fromisoformat(retrieved)
        except ValueError as exc:
            raise PilotUnavailable("invalid source retrieval timestamp") from exc
        if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
            raise PilotUnavailable("source retrieval time must be UTC")
        if match.group(2) == "index_hour":
            index_filters.add(fid)
            continue
        package_counts[fid] += 1
        series = doc["document"].get("series")
        if not isinstance(series, list):
            raise PilotUnavailable("invalid saved source series")
        for entry in series:
            if (
                not isinstance(entry, (list, tuple))
                or len(entry) != 2 or type(entry[0]) is not int
            ):
                raise PilotUnavailable("invalid saved source pair")
            timestamp_ms, value = entry
            hour = datetime.fromtimestamp(timestamp_ms / 1000, timezone.utc)
            if hour not in wanted:
                continue
            if hour in source_values[fid]:
                raise PilotUnavailable("duplicate saved source hour")
            if value is not None and (
                type(value) not in (int, float)
                or not math.isfinite(value)
                or (fid not in SIGNED_FILTERS and value < 0)
            ):
                raise PilotUnavailable("invalid saved source value")
            source_values[fid][hour] = None if value is None else float(value)
    if index_filters != set(FILTERS) or any(
        not 1 <= n <= MAX_PACKAGES for n in package_counts.values()
    ):
        raise PilotUnavailable("missing source index or weekly package")

    complete_all = True
    for i, (fid, label, key) in enumerate(ORIGINAL_SERIES):
        found = source_values[fid]
        missing = len(wanted - found.keys())
        nulls = sum(v is None for v in found.values())
        complete = missing == 0 and nulls == 0
        spec = summary[i]
        if (
            not isinstance(spec, dict)
            or spec.get("filter_id") != fid
            or spec.get("original_header") != label
            or spec.get("field") != key
            or spec.get("retrieved_hour_count") != len(found)
            or spec.get("missing_hour_count") != missing
            or spec.get("null_value_count") != nulls
            or spec.get("complete") is not complete
        ):
            raise PilotUnavailable("source-summary and document mismatch")
        complete_all &= complete
        for row, hour in zip(rows, expected):
            actual = row["values"][key]
            source_value = found.get(hour)
            if actual != source_value or (
                actual is not None and (
                    type(actual) not in (int, float) or not math.isfinite(actual)
                )
            ):
                raise PilotUnavailable("normalized source value disagrees with documents")
    if complete_all is not report["all_series_complete"]:
        raise PilotUnavailable("receipt completeness flag disagrees with sources")
    encoded = canonical_json(report)
    if len(encoded) > MAX_RECEIPT_BYTES:
        raise PilotUnavailable("daily raw source receipt exceeds size bound")
    return encoded


def compare_capture(previous: dict, current: dict) -> dict:
    """Compare same-day normalized values; retain both vintage receipts."""
    for value in (previous, current):
        receipt_payload(value)
    if previous["delivery_date"] != current["delivery_date"]:
        raise PilotUnavailable("cannot compare revisions for different days")
    changes = []
    for old, new in zip(previous["hours"], current["hours"]):
        for _, _, name in ORIGINAL_SERIES:
            a, b = old["values"][name], new["values"][name]
            if a != b:
                changes.append({
                    "hour_start_utc": old["hour_start_utc"],
                    "field": name,
                    "old_value": a,
                    "new_value": b,
                })
    return {
        "comparison_status": "REVISIONS_DETECTED" if changes else "UNCHANGED",
        "prior_receipt_sha256": hashlib.sha256(receipt_payload(previous)).hexdigest(),
        "current_source_value_changes": len(changes),
        "changes": changes,
        "current_source_only": True,
        "safe_to_train_or_publish": False,
    }


def save_capture(report: dict, directory: Path = DEFAULT_DIRECTORY) -> dict:
    """Atomic create-only file: never overwrite an earlier SMARD source vintage."""
    data = receipt_payload(report)
    if directory.is_symlink():
        raise PilotUnavailable("receipt directory cannot be a symlink")
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    if not directory.is_dir():
        raise PilotUnavailable("receipt directory is not a folder")
    sha = hashlib.sha256(data).hexdigest()
    captured = datetime.fromisoformat(report["captured_at_utc"])
    if captured.tzinfo is None or captured.utcoffset() != timedelta(0):
        raise PilotUnavailable("capture stamp must have UTC offset")
    stamp = captured.strftime("%Y%m%dT%H%M%S%fZ")
    day_part = report["delivery_date"].replace("-", "")
    final = directory / f"smard-current-{day_part}-{stamp}-{sha[:12]}.json"
    temp = directory / f".stage-{day_part}-{stamp}-{sha[:12]}.json"
    fd = None
    created_temp = False
    try:
        fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        created_temp = True
        with os.fdopen(fd, "wb") as handle:
            fd = None
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        # Creating a second hard link to the completed file is atomic and
        # fails if this final name already exists: no replace/no overwrite.
        os.link(temp, final)
    except FileExistsError as exc:
        raise PilotUnavailable("capture already exists; refusing to overwrite") from exc
    finally:
        if fd is not None:
            os.close(fd)
        # Never delete an existing temp file made by another process/run.
        if created_temp:
            temp.unlink(missing_ok=True)
    return {
        "status": "LOCAL_APPEND_ONLY_CAPTURE",
        "day": report["delivery_date"],
        "capture_status": report["status"],
        "path": str(final),
        "sha256": sha,
        "bytes": len(data),
        "physical_hours": report["hour_count"],
        "source_documents": report["source_document_count"],
        "all_series_complete": report["all_series_complete"],
        "revision_comparison": report["revision_comparison"],
        "safe_to_train_or_publish": False,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--day", help="Yesterday in Europe/Berlin; default is yesterday")
    parser.add_argument("--compare", type=Path,
                        help="Optional prior same-day receipt; new capture includes revision audit")
    args = parser.parse_args(argv)
    now = datetime.now(timezone.utc)
    local_yesterday = now.astimezone(LOCAL).date() - timedelta(days=1)
    try:
        day = date.fromisoformat(args.day) if args.day else local_yesterday
        capture = capture_completed_day(day, now)
        if args.compare:
            previous = json.loads(args.compare.read_text(encoding="utf-8"))
            audit = compare_capture(previous, capture)
            capture["revision_comparison"] = audit
        result = save_capture(capture)
    except (PilotUnavailable, OSError, ValueError, KeyError, TypeError,
            json.JSONDecodeError) as exc:
        print(f"SMARD_DAILY_INGESTION_NOT_AVAILABLE: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
