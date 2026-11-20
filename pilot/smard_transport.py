"""Bounded HTTPS transport for allowlisted, read-only SMARD JSON requests.

Paths must first be validated against the feature-specific allowlists.
Only transient TLS/network timeouts and 502/503/504 responses are retried,
ONCE. Explicit 429 rate limiting is never retried. TLS verification is never
disabled. No persistent cache, scheduler, uploads, or publication.
"""

from __future__ import annotations

import json
import socket
from time import sleep
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

class PilotUnavailable(ValueError):
    """Source data or transport is unavailable; do not publish or substitute."""

BASE = "https://www.smard.de/app/chart_data"
MAX_ATTEMPTS = 2
TIMEOUT_SECONDS = 20
RETRY_DELAY_SECONDS = 1.0


def _timed_out(exc: BaseException) -> bool:
    reason = exc.reason if isinstance(exc, URLError) else exc
    return isinstance(reason, (TimeoutError, socket.timeout)) or "timed out" in str(reason).lower()


def fetch_public_smard_json(path: str, *, user_agent: str, max_bytes: int = 5_000_000) -> dict:
    """Get one public JSON document, rejecting non-SMARD paths and unsafe responses.

    A caller must also enforce its *filter-specific* path allowlist.
    """
    if (
        not isinstance(path, str)
        or not path.startswith("/")
        or ".." in path
        or "?" in path
        or "#" in path
        or "\\" in path
        or not path.endswith(".json")
        or len(path) > 180
        or type(max_bytes) is not int
        or not 1 <= max_bytes <= 5_000_000
    ):
        raise PilotUnavailable("unsafe SMARD HTTPS request")
    request = Request(
        BASE + path,
        headers={"Accept": "application/json", "User-Agent": user_agent},
    )
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            with urlopen(request, timeout=TIMEOUT_SECONDS) as response:
                body = response.read(max_bytes + 1)
        except HTTPError as exc:
            if exc.code == 429:
                raise PilotUnavailable(
                    f"SMARD HTTP 429 rate limit on {path}; stop and retry later manually"
                ) from exc
            if exc.code in (502, 503, 504) and attempt < MAX_ATTEMPTS:
                sleep(RETRY_DELAY_SECONDS)
                continue
            raise PilotUnavailable(
                f"SMARD HTTP {exc.code} on {path} after {attempt} attempt(s)"
            ) from exc
        except (URLError, OSError) as exc:
            if _timed_out(exc) and attempt < MAX_ATTEMPTS:
                sleep(RETRY_DELAY_SECONDS)
                continue
            if _timed_out(exc):
                raise PilotUnavailable(
                    f"SMARD HTTPS timeout on {path} after {attempt} attempts; "
                    "no partial source data saved"
                ) from exc
            raise PilotUnavailable(
                f"SMARD HTTPS transport error on {path} ({type(exc).__name__}); "
                "TLS validation remains enabled"
            ) from exc
        if len(body) > max_bytes:
            raise PilotUnavailable(f"oversized SMARD JSON on {path}")
        try:
            document = json.loads(body)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise PilotUnavailable(f"invalid SMARD JSON on {path}") from exc
        if not isinstance(document, dict):
            raise PilotUnavailable(f"invalid SMARD object on {path}")
        return document
    raise PilotUnavailable(f"SMARD request limit reached for {path}")
