from __future__ import annotations

import json
import pickle
import unittest

from llm.types import LLMResult, PipelineMetrics


class PipelineMetricsTests(unittest.TestCase):
    def test_to_json_event_key(self) -> None:
        metrics = PipelineMetrics(stt_ms=100, llm_ms=500, tts_ms=200, tokens=42, tok_per_sec=84.0, e2e_ms=800)
        data = json.loads(metrics.to_json())
        self.assertEqual("pipeline_metrics", data["event"])

    def test_to_json_all_fields_present(self) -> None:
        metrics = PipelineMetrics(stt_ms=100, llm_ms=500, tts_ms=200, tokens=42, tok_per_sec=84.0, e2e_ms=800)
        data = json.loads(metrics.to_json())
        self.assertEqual(100, data["stt_ms"])
        self.assertEqual(500, data["llm_ms"])
        self.assertEqual(200, data["tts_ms"])
        self.assertEqual(42, data["tokens"])
        self.assertEqual(84.0, data["tok_per_sec"])
        self.assertEqual(800, data["e2e_ms"])

    def test_to_json_fast_path_zeroed_fields(self) -> None:
        metrics = PipelineMetrics(stt_ms=50, llm_ms=0, tts_ms=150, tokens=0, tok_per_sec=0.0, e2e_ms=200)
        data = json.loads(metrics.to_json())
        self.assertEqual(0, data["llm_ms"])
        self.assertEqual(0, data["tokens"])
        self.assertEqual(0.0, data["tok_per_sec"])

    def test_to_json_is_valid_json(self) -> None:
        metrics = PipelineMetrics(stt_ms=100, llm_ms=500, tts_ms=200, tokens=42, tok_per_sec=84.0, e2e_ms=800)
        result = metrics.to_json()
        parsed = json.loads(result)  # must not raise
        self.assertIsInstance(parsed, dict)

    def test_to_json_compact_no_spaces(self) -> None:
        metrics = PipelineMetrics(stt_ms=1, llm_ms=2, tts_ms=3, tokens=4, tok_per_sec=2.0, e2e_ms=6)
        result = metrics.to_json()
        self.assertNotIn(" ", result)

    def test_metrics_is_frozen(self) -> None:
        from dataclasses import FrozenInstanceError
        metrics = PipelineMetrics(stt_ms=100, llm_ms=500, tts_ms=200, tokens=42, tok_per_sec=84.0, e2e_ms=800)
        with self.assertRaises(FrozenInstanceError):
            metrics.stt_ms = 999  # type: ignore[misc]


class LLMResultTests(unittest.TestCase):
    def test_llm_result_round_trips_via_pickle(self) -> None:
        """LLMResult must survive pickle/unpickle — it crosses the subprocess boundary via multiprocessing."""
        response: dict[str, object] = {"assistant_text": "hello", "tool_call": None}
        original = LLMResult(response=response, tokens=42)
        restored = pickle.loads(pickle.dumps(original))
        self.assertEqual(original.tokens, restored.tokens)
        self.assertEqual(original.response, restored.response)

    def test_llm_result_is_frozen(self) -> None:
        from dataclasses import FrozenInstanceError
        result = LLMResult(response={"assistant_text": "x", "tool_call": None}, tokens=7)
        with self.assertRaises(FrozenInstanceError):
            result.tokens = 99  # type: ignore[misc]


if __name__ == "__main__":
    unittest.main()
