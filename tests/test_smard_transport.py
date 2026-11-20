"""Offline tests for conservative SMARD HTTPS retry and rate-limit boundaries."""

import io
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from pilot.smard_daily_pilot import PilotUnavailable as OriginalException
from pilot import smard_transport as transport

PATH = "/411/DE/index_hour.json"


class TransportTests(unittest.TestCase):
    def test_existing_failure_exception_identity_is_preserved(self):
        self.assertIs(OriginalException, transport.PilotUnavailable)

    def test_valid_json_uses_https_and_bounded_response(self):
        with patch.object(transport, "urlopen", return_value=io.BytesIO(b'{"timestamps":[123]}')) as opener:
            result = transport.fetch_public_smard_json(PATH, user_agent="GridStress-test")
        self.assertEqual(result, {"timestamps": [123]})
        self.assertEqual(opener.call_count, 1)
        request = opener.call_args.args[0]
        self.assertEqual(request.full_url, "https://www.smard.de/app/chart_data" + PATH)
        self.assertEqual(opener.call_args.kwargs["timeout"], 20)

    def test_timeout_once_then_success_with_one_bounded_retry(self):
        problem = URLError(TimeoutError("_ssl.c:989: The handshake operation timed out"))
        with patch.object(transport, "urlopen", side_effect=[
            problem, io.BytesIO(b'{"timestamps":[123]}'),
        ]) as opener, patch.object(transport, "sleep") as pause:
            data = transport.fetch_public_smard_json(PATH, user_agent="GridStress-test")
        self.assertEqual(data["timestamps"], [123])
        self.assertEqual(opener.call_count, 2)
        pause.assert_called_once_with(1.0)

    def test_two_timeouts_fail_closed_with_filter_path(self):
        problem = URLError(TimeoutError("The handshake operation timed out"))
        with patch.object(transport, "urlopen", side_effect=[problem, problem]) as opener, \
             patch.object(transport, "sleep") as pause:
            with self.assertRaisesRegex(transport.PilotUnavailable, "HTTPS timeout on /411/DE/index_hour.json after 2 attempts"):
                transport.fetch_public_smard_json(PATH, user_agent="GridStress-test")
        self.assertEqual(opener.call_count, 2)
        pause.assert_called_once()

    def test_http_429_stops_immediately_without_retry(self):
        problem = HTTPError("https://www.smard.de/app/chart_data" + PATH,
                            429, "Too Many Requests", {}, None)
        with patch.object(transport, "urlopen", side_effect=problem) as opener, \
             patch.object(transport, "sleep") as pause:
            with self.assertRaisesRegex(transport.PilotUnavailable, "429 rate limit"):
                transport.fetch_public_smard_json(PATH, user_agent="GridStress-test")
        opener.assert_called_once()
        pause.assert_not_called()

    def test_http_503_retries_once_then_succeeds(self):
        problem = HTTPError("https://www.smard.de/app/chart_data" + PATH,
                            503, "Unavailable", {}, None)
        with patch.object(transport, "urlopen", side_effect=[
            problem, io.BytesIO(b'{"timestamps":[123]}')
        ]) as opener, patch.object(transport, "sleep") as pause:
            result = transport.fetch_public_smard_json(PATH, user_agent="GridStress-test")
        self.assertEqual(result["timestamps"], [123])
        self.assertEqual(opener.call_count, 2)
        pause.assert_called_once()

    def test_bad_certificate_is_never_ignored_or_retried(self):
        with patch.object(transport, "urlopen",
                          side_effect=URLError("certificate verify failed")) as opener, \
             patch.object(transport, "sleep") as pause:
            with self.assertRaisesRegex(transport.PilotUnavailable, "TLS validation remains enabled"):
                transport.fetch_public_smard_json(PATH, user_agent="GridStress-test")
        opener.assert_called_once()
        pause.assert_not_called()

    def test_invalid_payload_and_too_large_payload_do_not_retry(self):
        for data in (b"not-json", b"[]", b"x" * 33):
            with self.subTest(data_len=len(data)), \
                 patch.object(transport, "urlopen", return_value=io.BytesIO(data)) as opener, \
                 patch.object(transport, "sleep") as pause:
                with self.assertRaises(transport.PilotUnavailable):
                    transport.fetch_public_smard_json(
                        PATH, user_agent="GridStress-test", max_bytes=32
                    )
                opener.assert_called_once()
                pause.assert_not_called()

    def test_untrusted_or_non_smard_paths_are_rejected_preflight(self):
        for path in ("https://bad.example", "//example.com/foo.json",
                     "/411/DE/../secret.json", "/411/DE/index_hour.json?a=1",
                     "/411/DE/index_hour.json#fragment", "/\\evil.example/x.json"):
            with self.subTest(path=path), patch.object(transport, "urlopen") as opener:
                with self.assertRaisesRegex(transport.PilotUnavailable, "unsafe"):
                    transport.fetch_public_smard_json(path, user_agent="GridStress-test")
                opener.assert_not_called()


if __name__ == "__main__":
    unittest.main()
