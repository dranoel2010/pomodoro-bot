import os
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest.mock import patch

_SRC_DIR = Path(__file__).resolve().parents[2] / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from app_config import (
    AppConfigurationError,
    load_app_config,
    load_secret_config,
    resolve_config_path,
)


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


class AppConfigLoadingTests(unittest.TestCase):
    def test_load_app_config_resolves_relative_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = root / "config.toml"
            _write_text(
                config_path,
                textwrap.dedent(
                    """
                    [pipecat.runtime]
                    language = "de"
                    allow_interruptions = false
                    metrics_enabled = true

                    [pipecat.wake.porcupine]
                    ppn_file = "models/wake.ppn"
                    pv_file = "models/params.pv"

                    [pipecat.stt.faster_whisper]

                    [pipecat.llm.local_llama]
                    enabled = false
                    system_prompt = "prompts/system.md"

                    [pipecat.tts.piper]
                    enabled = true
                    model_path = "voices/de_DE.onnx"
                    hf_filename = "de_DE.onnx"

                    [pipecat.ui]
                    enabled = true
                    host = "127.0.0.1"
                    port = 8765
                    ui = "miro"
                    index_file = "web/index.html"

                    [pipecat.tools.calendar]
                    enabled = true
                    google_calendar_enabled = false
                    """
                ).strip(),
            )

            app_config = load_app_config(str(config_path))
            porcupine = app_config.pipecat.wake.porcupine
            piper = app_config.pipecat.tts.piper
            llama = app_config.pipecat.llm.local_llama
            ui = app_config.pipecat.ui

            self.assertEqual(str(config_path), app_config.source_file)
            self.assertEqual(str((root / "models/wake.ppn").resolve()), porcupine.ppn_file)
            self.assertEqual(str((root / "models/params.pv").resolve()), porcupine.pv_file)
            self.assertEqual(str((root / "voices/de_DE.onnx").resolve()), piper.model_path)
            self.assertEqual(str((root / "prompts/system.md").resolve()), llama.system_prompt)
            self.assertEqual(str((root / "web/index.html").resolve()), ui.index_file)
            self.assertEqual("miro", ui.ui)

    def test_load_app_config_parses_cpu_core_affinity_lists(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.toml"
            _write_text(
                config_path,
                textwrap.dedent(
                    """
                    [pipecat.runtime]
                    language = "de"
                    allow_interruptions = false
                    metrics_enabled = true

                    [pipecat.wake.porcupine]
                    ppn_file = "wake.ppn"
                    pv_file = "params.pv"

                    [pipecat.stt.faster_whisper]
                    cpu_cores = [0, 1]

                    [pipecat.llm.local_llama]
                    enabled = false
                    cpu_cores = [3, 4, 5]

                    [pipecat.tts.piper]
                    enabled = true
                    hf_filename = "de.onnx"
                    cpu_cores = [2]

                    [pipecat.ui]
                    enabled = true
                    host = "127.0.0.1"
                    port = 8765
                    ui = "jarvis"

                    [pipecat.tools.calendar]
                    enabled = true
                    google_calendar_enabled = false
                    """
                ).strip(),
            )

            app_config = load_app_config(str(config_path))
            self.assertEqual((0, 1), app_config.pipecat.stt.faster_whisper.cpu_cores)
            self.assertEqual((2,), app_config.pipecat.tts.piper.cpu_cores)
            self.assertEqual((3, 4, 5), app_config.pipecat.llm.local_llama.cpu_cores)

    def test_load_app_config_rejects_duplicate_cpu_cores(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.toml"
            _write_text(
                config_path,
                textwrap.dedent(
                    """
                    [pipecat.runtime]
                    language = "de"
                    allow_interruptions = false
                    metrics_enabled = true

                    [pipecat.wake.porcupine]
                    ppn_file = "wake.ppn"
                    pv_file = "params.pv"

                    [pipecat.stt.faster_whisper]
                    cpu_cores = [0, 0]

                    [pipecat.llm.local_llama]
                    enabled = false

                    [pipecat.tts.piper]
                    enabled = false
                    hf_filename = "de.onnx"

                    [pipecat.ui]
                    enabled = true
                    host = "127.0.0.1"
                    port = 8765
                    ui = "jarvis"

                    [pipecat.tools.calendar]
                    enabled = true
                    google_calendar_enabled = false
                    """
                ).strip(),
            )

            with self.assertRaises(AppConfigurationError) as context:
                load_app_config(str(config_path))
            self.assertIn("pipecat.stt.faster_whisper.cpu_cores", str(context.exception))

    def test_load_app_config_rejects_unknown_ui_variant(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.toml"
            _write_text(
                config_path,
                textwrap.dedent(
                    """
                    [pipecat.runtime]
                    language = "de"
                    allow_interruptions = false
                    metrics_enabled = true

                    [pipecat.wake.porcupine]
                    ppn_file = "wake.ppn"
                    pv_file = "params.pv"

                    [pipecat.stt.faster_whisper]

                    [pipecat.llm.local_llama]
                    enabled = false

                    [pipecat.tts.piper]
                    enabled = false
                    hf_filename = "de.onnx"

                    [pipecat.ui]
                    enabled = true
                    host = "127.0.0.1"
                    port = 8765
                    ui = "retro"

                    [pipecat.tools.calendar]
                    enabled = true
                    google_calendar_enabled = false
                    """
                ).strip(),
            )

            with self.assertRaises(AppConfigurationError) as context:
                load_app_config(str(config_path))
            self.assertIn("pipecat.ui.ui", str(context.exception))

    def test_load_app_config_rejects_unknown_llm_affinity_mode(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.toml"
            _write_text(
                config_path,
                textwrap.dedent(
                    """
                    [pipecat.runtime]
                    language = "de"
                    allow_interruptions = false
                    metrics_enabled = true

                    [pipecat.wake.porcupine]
                    ppn_file = "wake.ppn"
                    pv_file = "params.pv"

                    [pipecat.stt.faster_whisper]

                    [pipecat.llm.local_llama]
                    enabled = false
                    cpu_affinity_mode = "auto"

                    [pipecat.tts.piper]
                    enabled = false
                    hf_filename = "de.onnx"

                    [pipecat.ui]
                    enabled = true
                    host = "127.0.0.1"
                    port = 8765
                    ui = "jarvis"

                    [pipecat.tools.calendar]
                    enabled = true
                    google_calendar_enabled = false
                    """
                ).strip(),
            )

            with self.assertRaises(AppConfigurationError) as context:
                load_app_config(str(config_path))
            self.assertIn("pipecat.llm.local_llama.cpu_affinity_mode", str(context.exception))

    def test_load_secret_config_requires_pico_key(self) -> None:
        with self.assertRaises(AppConfigurationError):
            load_secret_config(environ={})

    def test_load_secret_config_normalizes_optional_values(self) -> None:
        secret_config = load_secret_config(
            environ={
                "PICO_VOICE_ACCESS_KEY": "  abc  ",
                "HF_TOKEN": "  ",
                "ORACLE_GOOGLE_CALENDAR_ID": " cal-1 ",
                "ORACLE_GOOGLE_SERVICE_ACCOUNT_FILE": " /tmp/sa.json ",
            }
        )

        self.assertEqual("abc", secret_config.pico_voice_access_key)
        self.assertIsNone(secret_config.hf_token)
        self.assertEqual("cal-1", secret_config.oracle_google_calendar_id)
        self.assertEqual("/tmp/sa.json", secret_config.oracle_google_service_account_file)

    def test_resolve_config_path_uses_executable_dir_fallback_in_frozen_mode(self) -> None:
        with tempfile.TemporaryDirectory() as cwd_dir, tempfile.TemporaryDirectory() as exe_dir:
            cwd = Path(cwd_dir)
            executable_dir_config = Path(exe_dir) / "config.toml"
            _write_text(
                executable_dir_config,
                textwrap.dedent(
                    """
                    [pipecat.runtime]
                    language = "de"
                    allow_interruptions = false
                    metrics_enabled = true

                    [pipecat.wake.porcupine]
                    ppn_file = "wake.ppn"
                    pv_file = "params.pv"

                    [pipecat.stt.faster_whisper]
                    [pipecat.llm.local_llama]
                    enabled = false
                    [pipecat.tts.piper]
                    enabled = false
                    hf_filename = "de.onnx"
                    [pipecat.ui]
                    enabled = true
                    host = "127.0.0.1"
                    port = 8765
                    ui = "jarvis"
                    [pipecat.tools.calendar]
                    enabled = true
                    google_calendar_enabled = false
                    """
                ).strip(),
            )
            executable = Path(exe_dir) / "main"

            with patch.dict(os.environ, {}, clear=True):
                with patch("app_config.Path.cwd", return_value=cwd):
                    with patch.object(sys, "frozen", True, create=True):
                        with patch.object(sys, "executable", str(executable), create=True):
                            resolved = resolve_config_path()

            self.assertEqual(executable_dir_config.resolve(), resolved)


if __name__ == "__main__":
    unittest.main()
