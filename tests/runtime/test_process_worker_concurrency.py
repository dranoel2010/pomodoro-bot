from __future__ import annotations

import logging
import sys
import threading
import time
import types
import unittest
from pathlib import Path
from unittest.mock import patch

# Import runtime.workers.core without executing src/runtime/__init__.py.
_RUNTIME_DIR = Path(__file__).resolve().parents[2] / "src" / "runtime"
if "runtime" not in sys.modules:
    _pkg = types.ModuleType("runtime")
    _pkg.__path__ = [str(_RUNTIME_DIR)]  # type: ignore[attr-defined]
    sys.modules["runtime"] = _pkg
if "runtime.workers" not in sys.modules:
    _workers_pkg = types.ModuleType("runtime.workers")
    _workers_pkg.__path__ = [str(_RUNTIME_DIR / "workers")]  # type: ignore[attr-defined]
    sys.modules["runtime.workers"] = _workers_pkg

from runtime.workers.core import _ProcessWorker, _ResponseEnvelope


def _dummy_runtime_factory() -> object:
    return object()


def _build_worker() -> _ProcessWorker:
    with patch.object(_ProcessWorker, "_start_worker", return_value=None):
        return _ProcessWorker(
            name="test-worker",
            runtime_factory=_dummy_runtime_factory,
            runtime_args=(),
            cpu_cores=(),
            log_queue=None,
            log_level=logging.INFO,
            logger=logging.getLogger("test"),
            startup_timeout_seconds=5.0,
        )


class ProcessWorkerConcurrencyTests(unittest.TestCase):
    def test_call_serializes_concurrent_requests(self) -> None:
        worker = _build_worker()
        send_call_ids: list[int] = []
        first_wait_entered = threading.Event()
        release_first_response = threading.Event()
        lock = threading.Lock()
        responses = [
            _ResponseEnvelope(kind="result", call_id=1, payload="first-ok"),
            _ResponseEnvelope(kind="result", call_id=2, payload="second-ok"),
        ]

        def _send_request(message: object) -> None:
            call_id = getattr(message, "call_id", None)
            with lock:
                send_call_ids.append(int(call_id))

        wait_index = {"value": 0}

        def _wait_for_response(*, timeout_seconds: float):
            del timeout_seconds
            wait_index["value"] += 1
            if wait_index["value"] == 1:
                first_wait_entered.set()
                self.assertTrue(
                    release_first_response.wait(timeout=1.0),
                    "First call should be released by the test thread.",
                )
            return responses[wait_index["value"] - 1]

        with patch.object(worker, "_send_request", side_effect=_send_request), patch.object(
            worker,
            "_wait_for_response",
            side_effect=_wait_for_response,
        ):
            first_result: list[object] = []
            second_result: list[object] = []

            first_thread = threading.Thread(
                target=lambda: first_result.append(worker.call("first")),
                daemon=True,
            )
            second_thread = threading.Thread(
                target=lambda: second_result.append(worker.call("second")),
                daemon=True,
            )

            first_thread.start()
            self.assertTrue(
                first_wait_entered.wait(timeout=1.0),
                "First worker call did not start waiting for a response.",
            )

            second_thread.start()
            time.sleep(0.05)
            self.assertEqual(
                [1],
                send_call_ids,
                "Second worker call should wait until the first call completes.",
            )

            release_first_response.set()
            first_thread.join(timeout=1.0)
            second_thread.join(timeout=1.0)
            self.assertFalse(first_thread.is_alive(), "First call did not complete.")
            self.assertFalse(second_thread.is_alive(), "Second call did not complete.")

        self.assertEqual(["first-ok"], first_result)
        self.assertEqual(["second-ok"], second_result)
        self.assertEqual([1, 2], send_call_ids)


if __name__ == "__main__":
    unittest.main()
