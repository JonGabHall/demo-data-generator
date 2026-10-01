import json
import unittest

from indoors_demo_generator.narratives import LocalJsonNarrator, narrative_run_metadata


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return None

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


class LocalJsonNarratorTests(unittest.TestCase):
    def test_accepts_valid_ollama_json_text(self):
        requests = []

        def opener(request, timeout):
            requests.append((request, timeout))
            return _Response({"response": '{"text":"Filter inspected; no defects observed."}'})

        narrator = LocalJsonNarrator(
            "http://localhost:11434/api/generate", "llama3.1:8b", opener=opener
        )

        result = narrator.narrate("inspection", {"condition": "Operational"}, "fallback")

        self.assertEqual(result, "Filter inspected; no defects observed.")
        request_body = json.loads(requests[0][0].data)
        self.assertEqual(request_body["format"], "json")
        self.assertFalse(request_body["stream"])
        self.assertEqual(narrator.stats.accepted_responses, 1)
        self.assertEqual(narrator.stats.fallback_responses, 0)

    def test_uses_fallback_for_malformed_or_extra_fields(self):
        payloads = iter(
            [
                {"response": "not json"},
                {"response": '{"text":"okay","asset_id":"invented"}'},
            ]
        )
        narrator = LocalJsonNarrator(
            "http://127.0.0.1:11434/api/generate",
            "test",
            max_requests=2,
            opener=lambda *_args, **_kwargs: _Response(next(payloads)),
        )

        self.assertEqual(narrator.narrate("inspection", {}, "fallback one"), "fallback one")
        self.assertEqual(narrator.narrate("repair", {}, "fallback two"), "fallback two")
        self.assertEqual(narrator.stats.invalid_response_fallbacks, 2)

    def test_enforces_request_budget_and_local_endpoint(self):
        narrator = LocalJsonNarrator(
            "http://localhost:8000/v1/chat/completions", "test", max_requests=0
        )
        self.assertEqual(narrator.narrate("inspection", {}, "fallback"), "fallback")
        self.assertEqual(narrator.stats.budget_fallbacks, 1)
        self.assertEqual(narrator.stats.requests_sent, 0)
        with self.assertRaisesRegex(ValueError, "localhost"):
            LocalJsonNarrator("https://example.com/v1/chat/completions", "test")
        with self.assertRaisesRegex(ValueError, "model"):
            LocalJsonNarrator("http://localhost:11434/api/generate", " ")

    def test_reports_transport_fallbacks(self):
        narrator = LocalJsonNarrator(
            "http://localhost:11434/api/generate",
            "test",
            opener=lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("offline")),
        )

        self.assertEqual(narrator.narrate("inspection", {}, "fallback"), "fallback")
        self.assertEqual(narrator.stats.request_error_fallbacks, 1)
        self.assertEqual(narrator.stats.total_calls, 1)

    def test_builds_manifest_metadata_for_enabled_and_disabled_runs(self):
        narrator = LocalJsonNarrator(
            "http://localhost:11434/api/generate",
            "test",
            max_requests=1,
            opener=lambda *_args, **_kwargs: _Response({"response": '{"text":"Accepted."}'}),
        )
        narrator.narrate("inspection", {}, "fallback")

        enabled = narrative_run_metadata(narrator)
        disabled = narrative_run_metadata(None)

        self.assertTrue(enabled["enabled"])
        self.assertEqual(enabled["endpoint"], "http://localhost:11434/api/generate")
        self.assertEqual(enabled["statistics"]["accepted_responses"], 1)
        self.assertFalse(disabled["enabled"])
        self.assertEqual(disabled["statistics"]["total_calls"], 0)


if __name__ == "__main__":
    unittest.main()