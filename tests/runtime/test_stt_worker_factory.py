import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import ANY, patch

_SRC_DIR = Path(__file__).resolve().parents[2] / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

# Import runtime.workers.stt without executing src/runtime/__init__.py.
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
from stt.config import ConfigurationError
from runtime.workers.stt import create_stt_worker


class STTWorkerFactoryTests(unittest.TestCase):
    def test_create_stt_worker_builds_worker_from_resources(self) -> None:
        wake_word_config = object()
        stt_config = object()
        stt_worker = object()
        stt_settings = SimpleNamespace(cpu_cores=(1, 2))

        with patch(
            "runtime.workers.stt.create_stt_resources",
            return_value=(wake_word_config, stt_config),
        ) as create_resources, patch(
            "runtime.workers.stt.STTWorker",
            return_value=stt_worker,
        ) as worker_cls:
            returned_wake_word, returned_worker = create_stt_worker(
                wake_word=SimpleNamespace(),
                stt=stt_settings,
                pico_key="secret",
                log_queue=object(),
                log_level=20,
            )

        self.assertIs(returned_wake_word, wake_word_config)
        self.assertIs(returned_worker, stt_worker)
        create_resources.assert_called_once_with(
            wake_word=ANY,
            stt=stt_settings,
            pico_key="secret",
        )
        worker_cls.assert_called_once()
        self.assertEqual(stt_config, worker_cls.call_args.kwargs["config"])
        self.assertEqual((1, 2), worker_cls.call_args.kwargs["cpu_cores"])
        self.assertEqual(20, worker_cls.call_args.kwargs["log_level"])

    def test_create_stt_worker_wraps_configuration_errors(self) -> None:
        with patch(
            "runtime.workers.stt.create_stt_resources",
            side_effect=ConfigurationError("bad stt config"),
        ):
            with self.assertRaises(StartupError) as error:
                create_stt_worker(
                    wake_word=SimpleNamespace(),
                    stt=SimpleNamespace(cpu_cores=()),
                    pico_key="secret",
                    log_queue=object(),
                    log_level=20,
                )

        self.assertTrue(str(error.exception).startswith("STT configuration error:"))

    def test_create_stt_worker_wraps_init_errors(self) -> None:
        with patch(
            "runtime.workers.stt.create_stt_resources",
            return_value=(object(), object()),
        ), patch(
            "runtime.workers.stt.STTWorker",
            side_effect=RuntimeError("boom"),
        ):
            with self.assertRaises(StartupError) as error:
                create_stt_worker(
                    wake_word=SimpleNamespace(),
                    stt=SimpleNamespace(cpu_cores=()),
                    pico_key="secret",
                    log_queue=object(),
                    log_level=20,
                )

        self.assertTrue(str(error.exception).startswith("STT initialization failed:"))


if __name__ == "__main__":
    unittest.main()
