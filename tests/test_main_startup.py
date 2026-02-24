import sys
import unittest
import types
import importlib
from pathlib import Path
from unittest.mock import patch

_SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))


def _import_main_with_startup_stubs():
    stt_module = types.ModuleType("stt")
    stt_module.create_stt_client = lambda *args, **kwargs: None

    class _WakeWordService:  # pragma: no cover - type placeholder for import path
        pass

    stt_module.WakeWordService = _WakeWordService

    tts_module = types.ModuleType("tts")
    tts_module.create_tts_client = lambda *args, **kwargs: None

    llm_module = types.ModuleType("llm")
    llm_module.create_llm_client = lambda *args, **kwargs: None

    oracle_module = types.ModuleType("oracle")
    oracle_module.create_oracle_service = lambda *args, **kwargs: None

    server_module = types.ModuleType("server")
    server_module.create_ui_server = lambda *args, **kwargs: None

    with patch.dict(
        sys.modules,
        {
            "stt": stt_module,
            "tts": tts_module,
            "llm": llm_module,
            "oracle": oracle_module,
            "server": server_module,
        },
    ):
        sys.modules.pop("main", None)
        return importlib.import_module("main")


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
        app_main = _import_main_with_startup_stubs()
        service = _CrashDuringStartupService()

        result = app_main._wait_for_service_ready_callback(service, timeout=1.0)

        self.assertFalse(result)
        self.assertEqual([0.25], service.wait_calls)

    def test_wait_for_service_ready_uses_bounded_wait_intervals(self) -> None:
        app_main = _import_main_with_startup_stubs()
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
