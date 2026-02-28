import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

_SRC_DIR = Path(__file__).resolve().parents[2] / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

# Import runtime.workers.tts without executing src/runtime/__init__.py.
_RUNTIME_DIR = Path(__file__).resolve().parents[2] / "src" / "runtime"
if "runtime" not in sys.modules:
    _pkg = types.ModuleType("runtime")
    _pkg.__path__ = [str(_RUNTIME_DIR)]  # type: ignore[attr-defined]
    sys.modules["runtime"] = _pkg
if "runtime.workers" not in sys.modules:
    _workers_pkg = types.ModuleType("runtime.workers")
    _workers_pkg.__path__ = [str(_RUNTIME_DIR / "workers")]  # type: ignore[attr-defined]
    sys.modules["runtime.workers"] = _workers_pkg

from contracts import StartupError
from tts.config import TTSConfigurationError
from runtime.workers.tts import create_tts_worker


class TTSWorkerFactoryTests(unittest.TestCase):
    def test_create_tts_worker_returns_none_when_disabled(self) -> None:
        with patch("runtime.workers.tts.create_tts_config") as create_config, patch(
            "runtime.workers.tts.TTSWorker"
        ) as worker_cls:
            result = create_tts_worker(
                tts=SimpleNamespace(enabled=False),
                log_queue=object(),
                log_level=20,
            )

        self.assertIsNone(result)
        create_config.assert_not_called()
        worker_cls.assert_not_called()

    def test_create_tts_worker_builds_worker_from_config(self) -> None:
        tts_config = object()
        worker = object()
        settings = SimpleNamespace(enabled=True, cpu_cores=(4, 5))
        logger = MagicMock()

        with patch(
            "runtime.workers.tts.create_tts_config",
            return_value=tts_config,
        ) as create_config, patch(
            "runtime.workers.tts.TTSWorker",
            return_value=worker,
        ) as worker_cls:
            result = create_tts_worker(
                tts=settings,
                log_queue=object(),
                log_level=20,
                logger=logger,
            )

        self.assertIs(result, worker)
        create_config.assert_called_once_with(tts=settings)
        worker_cls.assert_called_once()
        self.assertEqual(tts_config, worker_cls.call_args.kwargs["config"])
        self.assertEqual((4, 5), worker_cls.call_args.kwargs["cpu_cores"])
        self.assertEqual(20, worker_cls.call_args.kwargs["log_level"])
        self.assertIs(logger, worker_cls.call_args.kwargs["logger"])

    def test_create_tts_worker_wraps_configuration_errors(self) -> None:
        with patch(
            "runtime.workers.tts.create_tts_config",
            side_effect=TTSConfigurationError("bad tts config"),
        ):
            with self.assertRaises(StartupError) as error:
                create_tts_worker(
                    tts=SimpleNamespace(enabled=True, cpu_cores=()),
                    log_queue=object(),
                    log_level=20,
                )

        self.assertTrue(str(error.exception).startswith("TTS configuration error:"))

    def test_create_tts_worker_wraps_init_errors(self) -> None:
        with patch(
            "runtime.workers.tts.create_tts_config",
            return_value=object(),
        ), patch(
            "runtime.workers.tts.TTSWorker",
            side_effect=RuntimeError("boom"),
        ):
            with self.assertRaises(StartupError) as error:
                create_tts_worker(
                    tts=SimpleNamespace(enabled=True, cpu_cores=()),
                    log_queue=object(),
                    log_level=20,
                )

        self.assertTrue(str(error.exception).startswith("TTS initialization failed:"))


if __name__ == "__main__":
    unittest.main()
