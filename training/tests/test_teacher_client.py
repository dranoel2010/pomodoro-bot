from __future__ import annotations

import json
import os
import random
import unittest
from unittest.mock import patch

from training.teacher import TeacherClient


class _FakeHTTPResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class TeacherClientTests(unittest.TestCase):
    def test_ollama_provider_success(self) -> None:
        client = TeacherClient(model="qwen3:14b", provider="ollama")

        def _fake_urlopen(request, timeout=0):  # noqa: ANN001
            self.assertIn("/api/generate", request.full_url)
            return _FakeHTTPResponse({"response": '{"paraphrase": "Bitte pausiere den Timer."}'})

        with patch("urllib.request.urlopen", side_effect=_fake_urlopen):
            text, used = client.paraphrase(
                user_text="Pausiere den Timer.",
                intent_class="pause_timer",
                target_tool_name="pause_timer",
                rng=random.Random(1),
            )

        self.assertTrue(used)
        self.assertEqual("Bitte pausiere den Timer.", text)

    def test_auto_prefers_ollama_when_available(self) -> None:
        client = TeacherClient(model="qwen3:14b", provider="auto")

        def _fake_urlopen(request, timeout=0):  # noqa: ANN001
            if request.full_url.endswith("/api/tags"):
                return _FakeHTTPResponse({"models": []})
            if request.full_url.endswith("/api/generate"):
                return _FakeHTTPResponse({"response": '{"paraphrase": "Zeig mir bitte Termine morgen."}'})
            raise AssertionError(f"Unexpected URL: {request.full_url}")

        with patch.dict(os.environ, {"OPENAI_API_KEY": ""}, clear=False):
            with patch("urllib.request.urlopen", side_effect=_fake_urlopen):
                text, used = client.paraphrase(
                    user_text="Zeig Termine morgen.",
                    intent_class="show_upcoming_events",
                    target_tool_name="show_upcoming_events",
                    rng=random.Random(2),
                )

        self.assertTrue(used)
        self.assertEqual("Zeig mir bitte Termine morgen.", text)

    def test_ollama_failure_falls_back_to_local(self) -> None:
        client = TeacherClient(model="qwen3:14b", provider="ollama")

        with patch("urllib.request.urlopen", side_effect=OSError("connection failed")):
            with patch("training.teacher._local_paraphrase", return_value="LOCAL_FALLBACK"):
                text, used = client.paraphrase(
                    user_text="Stoppe den Timer.",
                    intent_class="stop_timer",
                    target_tool_name="stop_timer",
                    rng=random.Random(3),
                )

        self.assertFalse(used)
        self.assertEqual("LOCAL_FALLBACK", text)


if __name__ == "__main__":
    unittest.main()
