import logging
import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

_SRC_DIR = Path(__file__).resolve().parents[2] / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

# Import runtime.workers.llm without executing src/runtime/__init__.py.
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

from contracts import StartupError
from llm.config import ConfigurationError
from runtime.workers.llm import AffinityConfigError, create_llm_worker


def _llm_settings(**overrides):
    values = {
        "enabled": True,
        "cpu_cores": (3,),
        "cpu_affinity_mode": "pinned",
        "shared_cpu_reserve_cores": 1,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class LLMWorkerFactoryTests(unittest.TestCase):
    def test_create_llm_worker_returns_none_when_disabled(self) -> None:
        with patch("runtime.workers.llm.create_llm_config") as create_config, patch(
            "runtime.workers.llm.LLMWorker"
        ) as worker_cls:
            result = create_llm_worker(
                llm=_llm_settings(enabled=False),
                hf_token=None,
                log_queue=object(),
                log_level=20,
                logger=MagicMock(),
            )

        self.assertIsNone(result)
        create_config.assert_not_called()
        worker_cls.assert_not_called()

    def test_create_llm_worker_builds_worker_from_config(self) -> None:
        llm_config = SimpleNamespace(model_path="/tmp/model.gguf")
        llm_worker = object()
        logger = MagicMock()
        llm_settings = _llm_settings()

        with patch(
            "runtime.workers.llm.create_llm_config",
            return_value=llm_config,
        ) as create_config, patch(
            "runtime.workers.llm.LLMWorker",
            return_value=llm_worker,
        ) as worker_cls:
            result = create_llm_worker(
                llm=llm_settings,
                hf_token="hf-token",
                log_queue=object(),
                log_level=20,
                logger=logger,
            )

        self.assertIs(result, llm_worker)
        create_config.assert_called_once()
        self.assertEqual("hf-token", create_config.call_args.kwargs["hf_token"])
        self.assertIsInstance(create_config.call_args.kwargs["logger"], logging.Logger)
        worker_cls.assert_called_once()
        self.assertEqual(llm_config, worker_cls.call_args.kwargs["config"])
        self.assertEqual((3,), worker_cls.call_args.kwargs["cpu_cores"])
        self.assertEqual(20, worker_cls.call_args.kwargs["log_level"])
        logger.info.assert_called_once_with("LLM enabled (model: %s)", "/tmp/model.gguf")

    def test_create_llm_worker_wraps_configuration_errors(self) -> None:
        with patch(
            "runtime.workers.llm.create_llm_config",
            side_effect=ConfigurationError("bad llm config"),
        ):
            with self.assertRaises(StartupError) as error:
                create_llm_worker(
                    llm=_llm_settings(),
                    hf_token=None,
                    log_queue=object(),
                    log_level=20,
                    logger=MagicMock(),
                )

        self.assertTrue(str(error.exception).startswith("LLM configuration error:"))

    def test_create_llm_worker_wraps_init_errors(self) -> None:
        with patch(
            "runtime.workers.llm.create_llm_config",
            return_value=SimpleNamespace(model_path="/tmp/model.gguf"),
        ), patch(
            "runtime.workers.llm.LLMWorker",
            side_effect=RuntimeError("boom"),
        ):
            with self.assertRaises(StartupError) as error:
                create_llm_worker(
                    llm=_llm_settings(),
                    hf_token=None,
                    log_queue=object(),
                    log_level=20,
                    logger=MagicMock(),
                )

        self.assertTrue(str(error.exception).startswith("LLM initialization failed:"))

    def test_create_llm_worker_wraps_affinity_config_errors(self) -> None:
        with patch(
            "runtime.workers.llm.create_llm_config",
            return_value=SimpleNamespace(model_path="/tmp/model.gguf"),
        ), patch(
            "runtime.workers.llm.LLMWorker",
            side_effect=AffinityConfigError("invalid affinity mode"),
        ):
            with self.assertRaises(StartupError) as error:
                create_llm_worker(
                    llm=_llm_settings(),
                    hf_token=None,
                    log_queue=object(),
                    log_level=20,
                    logger=MagicMock(),
                )

        self.assertTrue(str(error.exception).startswith("LLM configuration error:"))


if __name__ == "__main__":
    unittest.main()
