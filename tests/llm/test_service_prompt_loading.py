import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

# Import llm modules without executing src/llm/__init__.py.
_LLM_DIR = Path(__file__).resolve().parents[2] / "src" / "llm"
if "llm" not in sys.modules:
    _pkg = types.ModuleType("llm")
    _pkg.__path__ = [str(_LLM_DIR)]  # type: ignore[attr-defined]
    sys.modules["llm"] = _pkg

from llm.config import LLMConfig
from llm.service import PomodoroAssistantLLM


class _BackendStub:
    def __init__(self, config):
        self._config = config

    def complete(self, messages, max_tokens):  # pragma: no cover - unused in these tests
        return '{"assistant_text":"", "tool_call": null}'


def _build_config(tmp_root: Path, *, system_prompt_path: str) -> LLMConfig:
    model_path = tmp_root / "dummy.gguf"
    model_path.write_bytes(b"dummy")
    return LLMConfig(
        model_path=str(model_path),
        system_prompt_path=system_prompt_path,
    )


class ServicePromptLoadingTests(unittest.TestCase):
    def test_loads_prompt_from_resolved_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prompt_path = root / "prompts" / "system_prompt_qwen3.md"
            prompt_path.parent.mkdir(parents=True, exist_ok=True)
            prompt_path.write_text("PROMPT_FROM_CONFIG_PATH", encoding="utf-8")
            config = _build_config(root, system_prompt_path=str(prompt_path))

            with patch("llm.service.LlamaBackend", _BackendStub):
                service = PomodoroAssistantLLM(config)

            self.assertEqual("PROMPT_FROM_CONFIG_PATH", service._system_prompt_template)

    def test_frozen_mode_falls_back_to_bundled_prompts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            missing_config_resolved_path = (
                root / "deploy" / "prompts" / "system_prompt_qwen3.md"
            )
            bundled_prompt = root / "bundle" / "prompts" / "system_prompt_qwen3.md"
            bundled_prompt.parent.mkdir(parents=True, exist_ok=True)
            bundled_prompt.write_text("PROMPT_FROM_BUNDLE", encoding="utf-8")
            config = _build_config(
                root,
                system_prompt_path=str(missing_config_resolved_path),
            )

            with patch("llm.service.LlamaBackend", _BackendStub), patch.object(
                sys,
                "_MEIPASS",
                str(root / "bundle"),
                create=True,
            ):
                service = PomodoroAssistantLLM(config)

            self.assertEqual("PROMPT_FROM_BUNDLE", service._system_prompt_template)


if __name__ == "__main__":
    unittest.main()
