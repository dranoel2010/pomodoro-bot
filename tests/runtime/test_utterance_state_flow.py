import sys
import unittest
from pathlib import Path

_SRC_DIR = Path(__file__).resolve().parents[2] / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from runtime.pipecat_engine import _noop_signal_handlers, _wait_for_service_ready


class _ServiceStub:
    def __init__(self, ready: bool):
        self.ready = ready
        self.calls: list[float] = []

    def wait_until_ready(self, timeout: float) -> bool:
        self.calls.append(timeout)
        return self.ready


class PipecatEngineCallbackTests(unittest.TestCase):
    def test_wait_for_service_ready_delegates_timeout(self) -> None:
        service = _ServiceStub(ready=True)
        self.assertTrue(_wait_for_service_ready(service, 2.5))
        self.assertEqual([2.5], service.calls)

    def test_noop_signal_handlers_accepts_service(self) -> None:
        _noop_signal_handlers(_ServiceStub(ready=False))


if __name__ == "__main__":
    unittest.main()
