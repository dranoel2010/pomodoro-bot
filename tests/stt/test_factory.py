import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

_SRC_DIR = Path(__file__).resolve().parents[2] / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from contracts.errors import StartupError

# Import stt.factory without executing src/stt/__init__.py.
_STT_DIR = Path(__file__).resolve().parents[2] / "src" / "stt"
if "stt" not in sys.modules:
    _pkg = types.ModuleType("stt")
    _pkg.__path__ = [str(_STT_DIR)]  # type: ignore[attr-defined]
    sys.modules["stt"] = _pkg

from stt.config import ConfigurationError
from stt.factory import create_stt_client

sys.modules["stt"].create_stt_client = create_stt_client


class _ProcessSTTClientStub:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


class _ProcessSTTClientFailingStub:
    def __init__(self, **kwargs):
        del kwargs
        raise RuntimeError("stt worker boom")


def _runtime_worker_modules(stt_client_cls: type[object]) -> dict[str, types.ModuleType]:
    runtime_pkg = types.ModuleType("runtime")
    runtime_pkg.__path__ = []  # type: ignore[attr-defined]
    process_workers = types.ModuleType("runtime.process_workers")
    process_workers.ProcessSTTClient = stt_client_cls
    return {
        "runtime": runtime_pkg,
        "runtime.process_workers": process_workers,
    }


class STTFactoryTests(unittest.TestCase):
    def test_create_stt_client_happy_path(self) -> None:
        wake_word_settings = SimpleNamespace()
        stt_settings = SimpleNamespace(cpu_cores=(1, 2))
        wake_word_config = object()
        stt_config = object()

        with patch.dict(
            sys.modules,
            _runtime_worker_modules(_ProcessSTTClientStub),
        ):
            with patch(
                "stt.factory.WakeWordConfig.from_settings",
                return_value=wake_word_config,
            ) as wakeword_from_settings, patch(
                "stt.factory.STTConfig.from_settings",
                return_value=stt_config,
            ) as stt_from_settings:
                returned_wakeword, stt_client = create_stt_client(
                    wake_word=wake_word_settings,
                    stt=stt_settings,
                    pico_key="secret",
                    log_queue=object(),
                    log_level=20,
                )

        self.assertIs(returned_wakeword, wake_word_config)
        self.assertIsInstance(stt_client, _ProcessSTTClientStub)
        wakeword_from_settings.assert_called_once_with(
            pico_voice_access_key="secret",
            settings=wake_word_settings,
        )
        stt_from_settings.assert_called_once_with(stt_settings)
        self.assertEqual(stt_config, stt_client.kwargs["config"])
        self.assertEqual((1, 2), stt_client.kwargs["cpu_cores"])
        self.assertEqual(20, stt_client.kwargs["log_level"])

    def test_create_stt_client_wraps_configuration_errors(self) -> None:
        with patch.dict(
            sys.modules,
            _runtime_worker_modules(_ProcessSTTClientStub),
        ):
            with patch(
                "stt.factory.WakeWordConfig.from_settings",
                side_effect=ConfigurationError("invalid wakeword"),
            ):
                with self.assertRaises(StartupError) as error:
                    create_stt_client(
                        wake_word=SimpleNamespace(),
                        stt=SimpleNamespace(cpu_cores=()),
                        pico_key="secret",
                        log_queue=object(),
                        log_level=20,
                    )

        self.assertIn("STT configuration error: invalid wakeword", str(error.exception))

    def test_create_stt_client_wraps_process_initialization_errors(self) -> None:
        with patch.dict(
            sys.modules,
            _runtime_worker_modules(_ProcessSTTClientFailingStub),
        ):
            with patch(
                "stt.factory.WakeWordConfig.from_settings",
                return_value=object(),
            ), patch(
                "stt.factory.STTConfig.from_settings",
                return_value=object(),
            ):
                with self.assertRaises(StartupError) as error:
                    create_stt_client(
                        wake_word=SimpleNamespace(),
                        stt=SimpleNamespace(cpu_cores=()),
                        pico_key="secret",
                        log_queue=object(),
                        log_level=20,
                    )

        self.assertIn(
            "STT initialization failed: RuntimeError: stt worker boom",
            str(error.exception),
        )


if __name__ == "__main__":
    unittest.main()
