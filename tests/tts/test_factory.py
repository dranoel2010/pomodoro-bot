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

# Import tts.factory without executing src/tts/__init__.py.
_TTS_DIR = Path(__file__).resolve().parents[2] / "src" / "tts"
if "tts" not in sys.modules:
    _pkg = types.ModuleType("tts")
    _pkg.__path__ = [str(_TTS_DIR)]  # type: ignore[attr-defined]
    sys.modules["tts"] = _pkg

from tts.config import TTSConfigurationError
from tts.factory import create_tts_client

sys.modules["tts"].create_tts_client = create_tts_client


class _ProcessTTSClientStub:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


class _ProcessTTSClientFailingStub:
    def __init__(self, **kwargs):
        del kwargs
        raise RuntimeError("tts worker boom")


def _runtime_worker_modules(tts_client_cls: type[object]) -> dict[str, types.ModuleType]:
    runtime_pkg = types.ModuleType("runtime")
    runtime_pkg.__path__ = []  # type: ignore[attr-defined]
    process_workers = types.ModuleType("runtime.process_workers")
    process_workers.ProcessTTSClient = tts_client_cls
    return {
        "runtime": runtime_pkg,
        "runtime.process_workers": process_workers,
    }


class TTSFactoryTests(unittest.TestCase):
    def test_create_tts_client_returns_none_when_disabled(self) -> None:
        result = create_tts_client(
            tts=SimpleNamespace(enabled=False),
            log_queue=object(),
            log_level=20,
        )
        self.assertIsNone(result)

    def test_create_tts_client_happy_path(self) -> None:
        settings = SimpleNamespace(enabled=True, cpu_cores=(2, 3))
        tts_config = object()

        with patch.dict(sys.modules, _runtime_worker_modules(_ProcessTTSClientStub)):
            with patch(
                "tts.factory.TTSConfig.from_settings",
                return_value=tts_config,
            ) as config_from_settings:
                client = create_tts_client(
                    tts=settings,
                    log_queue=object(),
                    log_level=20,
                )

        self.assertIsInstance(client, _ProcessTTSClientStub)
        config_from_settings.assert_called_once_with(settings)
        self.assertEqual(tts_config, client.kwargs["config"])
        self.assertEqual((2, 3), client.kwargs["cpu_cores"])
        self.assertEqual(20, client.kwargs["log_level"])

    def test_create_tts_client_wraps_configuration_errors(self) -> None:
        with patch.dict(sys.modules, _runtime_worker_modules(_ProcessTTSClientStub)):
            with patch(
                "tts.factory.TTSConfig.from_settings",
                side_effect=TTSConfigurationError("invalid tts config"),
            ):
                with self.assertRaises(StartupError) as error:
                    create_tts_client(
                        tts=SimpleNamespace(enabled=True, cpu_cores=()),
                        log_queue=object(),
                        log_level=20,
                    )

        self.assertIn("TTS configuration error: invalid tts config", str(error.exception))

    def test_create_tts_client_wraps_process_initialization_errors(self) -> None:
        with patch.dict(sys.modules, _runtime_worker_modules(_ProcessTTSClientFailingStub)):
            with patch(
                "tts.factory.TTSConfig.from_settings",
                return_value=object(),
            ):
                with self.assertRaises(StartupError) as error:
                    create_tts_client(
                        tts=SimpleNamespace(enabled=True, cpu_cores=()),
                        log_queue=object(),
                        log_level=20,
                    )

        self.assertIn(
            "TTS initialization failed: RuntimeError: tts worker boom",
            str(error.exception),
        )


if __name__ == "__main__":
    unittest.main()
