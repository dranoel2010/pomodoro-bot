import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

_SRC_DIR = Path(__file__).resolve().parents[2] / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from contracts import StartupError

# Import llm.factory without executing src/llm/__init__.py.
_LLM_DIR = Path(__file__).resolve().parents[2] / "src" / "llm"
if "llm" not in sys.modules:
    _pkg = types.ModuleType("llm")
    _pkg.__path__ = [str(_LLM_DIR)]  # type: ignore[attr-defined]
    sys.modules["llm"] = _pkg

from llm.config import ConfigurationError
from llm.factory import create_llm_client

sys.modules["llm"].create_llm_client = create_llm_client


class _ProcessLLMClientStub:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


class _ProcessLLMClientFailingStub:
    def __init__(self, **kwargs):
        del kwargs
        raise RuntimeError("llm worker boom")


def _runtime_worker_modules(llm_client_cls: type[object]) -> dict[str, types.ModuleType]:
    runtime_pkg = types.ModuleType("runtime")
    runtime_pkg.__path__ = []  # type: ignore[attr-defined]
    process_workers = types.ModuleType("runtime.process_workers")
    process_workers.ProcessLLMClient = llm_client_cls
    return {
        "runtime": runtime_pkg,
        "runtime.process_workers": process_workers,
    }


def _llm_settings(**overrides):
    values = {
        "enabled": True,
        "model_path": "models/llm",
        "hf_filename": "model.gguf",
        "hf_repo_id": "",
        "hf_revision": "",
        "system_prompt": "",
        "max_tokens": 128,
        "n_threads": 4,
        "n_ctx": 2048,
        "n_batch": 256,
        "temperature": 0.2,
        "top_p": 0.9,
        "repeat_penalty": 1.1,
        "verbose": False,
        "cpu_cores": (1,),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class LLMFactoryTests(unittest.TestCase):
    def test_create_llm_client_returns_none_when_disabled(self) -> None:
        result = create_llm_client(
            llm=_llm_settings(enabled=False),
            hf_token=None,
            log_queue=object(),
            log_level=20,
            logger=MagicMock(),
        )
        self.assertIsNone(result)

    def test_create_llm_client_happy_path(self) -> None:
        settings = _llm_settings()
        llm_config = SimpleNamespace(model_path="/tmp/model.gguf")
        logger = MagicMock()

        with patch.dict(sys.modules, _runtime_worker_modules(_ProcessLLMClientStub)):
            with patch(
                "llm.factory.LLMConfig.from_sources",
                return_value=llm_config,
            ) as from_sources:
                client = create_llm_client(
                    llm=settings,
                    hf_token="hf-token",
                    log_queue=object(),
                    log_level=20,
                    logger=logger,
                )

        self.assertIsInstance(client, _ProcessLLMClientStub)
        self.assertEqual(llm_config, client.kwargs["config"])
        self.assertEqual((1,), client.kwargs["cpu_cores"])
        self.assertEqual(20, client.kwargs["log_level"])
        self.assertEqual("hf-token", from_sources.call_args.kwargs["hf_token"])
        logger.info.assert_called_once_with("LLM enabled (model: %s)", "/tmp/model.gguf")

    def test_create_llm_client_wraps_configuration_errors(self) -> None:
        with patch.dict(sys.modules, _runtime_worker_modules(_ProcessLLMClientStub)):
            with patch(
                "llm.factory.LLMConfig.from_sources",
                side_effect=ConfigurationError("invalid llm config"),
            ):
                with self.assertRaises(StartupError) as error:
                    create_llm_client(
                        llm=_llm_settings(),
                        hf_token=None,
                        log_queue=object(),
                        log_level=20,
                        logger=MagicMock(),
                    )

        self.assertIn("LLM configuration error: invalid llm config", str(error.exception))

    def test_create_llm_client_wraps_process_initialization_errors(self) -> None:
        with patch.dict(sys.modules, _runtime_worker_modules(_ProcessLLMClientFailingStub)):
            with patch(
                "llm.factory.LLMConfig.from_sources",
                return_value=SimpleNamespace(model_path="/tmp/model.gguf"),
            ):
                with self.assertRaises(StartupError) as error:
                    create_llm_client(
                        llm=_llm_settings(),
                        hf_token=None,
                        log_queue=object(),
                        log_level=20,
                        logger=MagicMock(),
                    )

        self.assertIn(
            "LLM initialization failed: RuntimeError: llm worker boom",
            str(error.exception),
        )


if __name__ == "__main__":
    unittest.main()
