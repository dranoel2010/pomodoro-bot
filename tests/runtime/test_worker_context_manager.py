from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

_SRC_DIR = Path(__file__).resolve().parents[2] / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

# Import runtime.workers modules without executing src/runtime/__init__.py.
_RUNTIME_DIR = Path(__file__).resolve().parents[2] / "src" / "runtime"
if "runtime" not in sys.modules:
    _pkg = types.ModuleType("runtime")
    _pkg.__path__ = [str(_RUNTIME_DIR)]  # type: ignore[attr-defined]
    sys.modules["runtime"] = _pkg
if "runtime.workers" not in sys.modules:
    _workers_pkg = types.ModuleType("runtime.workers")
    _workers_pkg.__path__ = [str(_RUNTIME_DIR / "workers")]  # type: ignore[attr-defined]
    sys.modules["runtime.workers"] = _workers_pkg
if "huggingface_hub" not in sys.modules:
    _hf_module = types.ModuleType("huggingface_hub")
    _hf_module.__path__ = []  # type: ignore[attr-defined]
    _hf_module.hf_hub_download = lambda *args, **kwargs: "/tmp/model.gguf"
    sys.modules["huggingface_hub"] = _hf_module
if "huggingface_hub.utils" not in sys.modules:
    _hf_utils_module = types.ModuleType("huggingface_hub.utils")
    _hf_utils_module.HfHubHTTPError = RuntimeError
    _hf_utils_module.RepositoryNotFoundError = RuntimeError
    sys.modules["huggingface_hub.utils"] = _hf_utils_module

import runtime.workers.llm as llm_workers
import runtime.workers.stt as stt_workers
import runtime.workers.tts as tts_workers


class WorkerContextManagerTests(unittest.TestCase):
    def test_stt_worker_context_manager_closes_process_worker(self) -> None:
        with patch("runtime.workers.stt._ProcessWorker") as process_cls:
            process = process_cls.return_value
            with stt_workers.STTWorker(config=object()):
                pass

        process.close.assert_called_once()

    def test_tts_worker_context_manager_closes_process_worker(self) -> None:
        with patch("runtime.workers.tts._ProcessWorker") as process_cls:
            process = process_cls.return_value
            with tts_workers.TTSWorker(config=object()):
                pass

        process.close.assert_called_once()

    def test_llm_worker_context_manager_closes_process_worker(self) -> None:
        worker_config = llm_workers._WorkerConfig(llm_config=object(), cpu_cores=())
        with patch(
            "runtime.workers.llm._resolve_worker_config",
            return_value=worker_config,
        ), patch("runtime.workers.llm._ProcessWorker") as process_cls:
            process = process_cls.return_value
            with llm_workers.LLMWorker(config=object()):
                pass

        process.close.assert_called_once()

    def test_llm_worker_run_uses_typed_payload(self) -> None:
        from llm.types import LLMResult
        worker_config = llm_workers._WorkerConfig(llm_config=object(), cpu_cores=())
        response = {"assistant_text": "ok", "tool_call": None}
        with patch(
            "runtime.workers.llm._resolve_worker_config",
            return_value=worker_config,
        ), patch("runtime.workers.llm._ProcessWorker") as process_cls:
            process = process_cls.return_value
            process.call.return_value = LLMResult(response=response, tokens=42)
            worker = llm_workers.LLMWorker(config=object())
            result = worker.run("hello")

        payload = process.call.call_args.args[0]
        self.assertIsInstance(payload, llm_workers.LLMPayload)
        self.assertEqual("hello", payload.user_prompt)
        self.assertEqual(response, result)
        self.assertEqual(42, worker.last_tokens)

    def test_tts_worker_speak_uses_typed_payload(self) -> None:
        tts_engine_module = types.ModuleType("tts.engine")

        class TTSError(Exception):
            pass

        tts_engine_module.TTSError = TTSError

        with patch.dict(sys.modules, {"tts.engine": tts_engine_module}):
            with patch("runtime.workers.tts._ProcessWorker") as process_cls:
                process = process_cls.return_value
                worker = tts_workers.TTSWorker(config=object())
                worker.speak("test")

        payload = process.call.call_args.args[0]
        self.assertIsInstance(payload, tts_workers.TTSPayload)
        self.assertEqual("test", payload.text)


if __name__ == "__main__":
    unittest.main()
