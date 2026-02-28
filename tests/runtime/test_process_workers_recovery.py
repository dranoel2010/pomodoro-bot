import logging
import sys
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

from runtime.workers.core import (
    _ProcessWorker,
    _ResponseEnvelope,
    WorkerCallTimeoutError,
    WorkerClosedError,
    WorkerCrashError,
    WorkerInitError,
    WorkerTaskError,
)


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


class ProcessWorkerRecoveryTests(unittest.TestCase):
    def test_await_ready_accepts_ready_response(self) -> None:
        worker = _build_worker()
        with patch.object(
            worker,
            "_wait_for_response",
            return_value=_ResponseEnvelope(kind="ready"),
        ):
            worker._await_ready(timeout_seconds=1.0)

    def test_await_ready_wraps_timeout_as_worker_init_error(self) -> None:
        worker = _build_worker()
        with patch.object(
            worker,
            "_wait_for_response",
            side_effect=WorkerCallTimeoutError("timeout"),
        ):
            with self.assertRaises(WorkerInitError) as error:
                worker._await_ready(timeout_seconds=1.0)

        self.assertIn("startup timed out", str(error.exception))

    def test_timeout_restarts_worker_and_allows_subsequent_call(self) -> None:
        worker = _build_worker()
        with patch.object(worker, "_send_request"), patch.object(
            worker,
            "_wait_for_response",
            side_effect=[
                WorkerCallTimeoutError("timeout"),
                _ResponseEnvelope(kind="result", call_id=2, payload="ok"),
            ],
        ), patch.object(worker, "_restart_worker") as restart_worker:
            with self.assertRaises(WorkerCallTimeoutError):
                worker.call("first", timeout_seconds=0.01)
            self.assertEqual("ok", worker.call("second", timeout_seconds=0.5))

        restart_worker.assert_called_once()

    def test_crash_restarts_worker_and_allows_subsequent_call(self) -> None:
        worker = _build_worker()
        with patch.object(worker, "_send_request"), patch.object(
            worker,
            "_wait_for_response",
            side_effect=[
                WorkerCrashError("crash"),
                _ResponseEnvelope(kind="result", call_id=2, payload="ok"),
            ],
        ), patch.object(worker, "_restart_worker") as restart_worker:
            with self.assertRaises(WorkerCrashError):
                worker.call("first", timeout_seconds=0.01)
            self.assertEqual("ok", worker.call("second", timeout_seconds=0.5))

        restart_worker.assert_called_once()

    def test_task_error_propagates_without_restart(self) -> None:
        worker = _build_worker()
        with patch.object(worker, "_send_request"), patch.object(
            worker,
            "_wait_for_response",
            return_value=_ResponseEnvelope(
                kind="task_error",
                call_id=1,
                error_type="ValueError",
                error_message="bad payload",
            ),
        ), patch.object(worker, "_restart_worker") as restart_worker:
            with self.assertRaises(WorkerTaskError) as error:
                worker.call("bad")

        self.assertIn("ValueError: bad payload", str(error.exception))
        restart_worker.assert_not_called()

    def test_close_is_idempotent_and_call_on_closed_worker_fails(self) -> None:
        worker = _build_worker()
        with patch.object(worker, "_shutdown_worker") as shutdown_worker:
            worker.close()
            worker.close()

        shutdown_worker.assert_called_once_with(wait_timeout=5.0)
        with self.assertRaises(WorkerClosedError):
            worker.call("payload")


if __name__ == "__main__":
    unittest.main()
