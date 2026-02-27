import sys
import unittest
from pathlib import Path
from unittest.mock import patch

_SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

import main as app_main


class _CrashDuringStartupService:
    def __init__(self):
        self.is_running = True
        self.is_ready = False
        self.wait_calls: list[float] = []

    def wait_until_ready(self, timeout: float | None = None) -> bool:
        self.wait_calls.append(timeout or 0.0)
        self.is_running = False
        return False


class _NeverReadyService:
    def __init__(self):
        self.is_running = True
        self.is_ready = False
        self.wait_calls: list[float] = []

    def wait_until_ready(self, timeout: float | None = None) -> bool:
        self.wait_calls.append(timeout or 0.0)
        return False


class MainStartupTests(unittest.TestCase):
    def test_wait_for_service_ready_returns_false_when_service_crashes(self) -> None:
        service = _CrashDuringStartupService()
        result = app_main._wait_for_service_ready_callback(service, timeout=1.0)
        self.assertFalse(result)
        self.assertEqual([0.25], service.wait_calls)

    def test_wait_for_service_ready_uses_bounded_wait_intervals(self) -> None:
        service = _NeverReadyService()

        with patch.object(
            app_main.time,
            "monotonic",
            side_effect=[0.0, 0.0, 0.0, 0.2, 0.2, 0.6],
        ):
            result = app_main._wait_for_service_ready_callback(service, timeout=0.5)

        self.assertFalse(result)
        self.assertEqual([0.25, 0.25], service.wait_calls)


if __name__ == "__main__":
    unittest.main()

