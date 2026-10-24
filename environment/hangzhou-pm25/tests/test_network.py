import importlib
import io
import unittest
from http.client import IncompleteRead
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from test_pm25 import station


class NetworkTests(unittest.TestCase):
    def test_transient_failure_retries_and_post_is_a_read_query(self):
        p = importlib.import_module("providers")
        response = io.BytesIO(b'{"ok": true}')
        with (
            patch(
                "providers.urlopen", side_effect=[URLError("temporary"), response]
            ) as request,
            patch("providers.time.sleep"),
        ):
            self.assertEqual(p.fetch_json(p.CNEMC_URL, post=True), {"ok": True})
            self.assertEqual(request.call_count, 2)
            sent = request.call_args.args[0]
            self.assertEqual(sent.get_method(), "POST")
            self.assertEqual(sent.data, b"")
            self.assertEqual(request.call_args.kwargs["timeout"], 20)

    def test_not_found_is_not_retried(self):
        p = importlib.import_module("providers")
        with patch(
            "providers.urlopen",
            side_effect=HTTPError(p.AIR_URL, 404, "missing", {}, None),
        ) as request:
            with self.assertRaises(HTTPError):
                p.fetch_json(p.AIR_URL)
            self.assertEqual(request.call_count, 1)

    def test_truncated_http_response_does_not_discard_other_sources(self):
        p = importlib.import_module("providers")

        def source(url, post=False):
            if url.startswith(p.AIR_URL):
                raise IncompleteRead(b"partial")
            if post:
                return [station(), dict(station("other"), CityCode=310100)]
            return {"weather": "kept"}

        with patch("providers.fetch_json", side_effect=source):
            result = p.fetch_snapshot()
        self.assertIsNone(result["air"])
        self.assertIn("air", result["errors"])
        self.assertEqual(len(result["observations"]), 1)
        self.assertEqual(result["weather"], {"weather": "kept"})


if __name__ == "__main__":
    unittest.main()
