import logging
import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

_SRC_DIR = Path(__file__).resolve().parents[2] / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

# Import llm.factory without executing src/llm/__init__.py.
_LLM_DIR = Path(__file__).resolve().parents[2] / "src" / "llm"
if "llm" not in sys.modules:
    _pkg = types.ModuleType("llm")
    _pkg.__path__ = [str(_LLM_DIR)]  # type: ignore[attr-defined]
    sys.modules["llm"] = _pkg

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

from llm.config import ConfigurationError
from llm.factory import create_llm_config


def _llm_settings(**overrides):
    values = {
        "model_path": "models/llm",
        "hf_filename": "model.gguf",
        "hf_repo_id": "",
        "hf_revision": "",
        "system_prompt": "",
        "max_tokens": 128,
        "n_threads": 4,
        "n_threads_batch": None,
        "n_ctx": 2048,
        "n_batch": 256,
        "n_ubatch": None,
        "temperature": 0.2,
        "top_p": 0.9,
        "top_k": 40,
        "min_p": 0.05,
        "repeat_penalty": 1.1,
        "use_mmap": True,
        "use_mlock": False,
        "verbose": False,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class LLMFactoryTests(unittest.TestCase):
    def test_create_llm_config_happy_path(self) -> None:
        settings = _llm_settings()
        llm_config = object()
        logger = logging.getLogger("test.llm.factory")

        with patch(
            "llm.factory.LLMConfig.from_sources",
            return_value=llm_config,
        ) as from_sources:
            result = create_llm_config(
                llm=settings,
                hf_token="hf-token",
                logger=logger,
            )

        self.assertIs(result, llm_config)
        self.assertEqual("hf-token", from_sources.call_args.kwargs["hf_token"])
        self.assertIs(logger, from_sources.call_args.kwargs["logger"])

    def test_create_llm_config_propagates_configuration_errors(self) -> None:
        with patch(
            "llm.factory.LLMConfig.from_sources",
            side_effect=ConfigurationError("invalid llm config"),
        ):
            with self.assertRaises(ConfigurationError) as error:
                create_llm_config(
                    llm=_llm_settings(),
                    hf_token=None,
                    logger=logging.getLogger("test.llm.factory"),
                )

        self.assertIn("invalid llm config", str(error.exception))


if __name__ == "__main__":
    unittest.main()
