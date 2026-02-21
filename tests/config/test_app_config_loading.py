import os
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest.mock import patch

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
                    [wake_word]
                    ppn_file = "models/wake.ppn"
                    pv_file = "models/params.pv"

                    [tts]
                    model_path = "voices/de_DE.onnx"

                    [llm]
                    system_prompt = "prompts/system.md"

                    [ui_server]
                    index_file = "web/index.html"
                    """
                ).strip(),
            )

            app_config = load_app_config(str(config_path))

            self.assertEqual(str(config_path), app_config.source_file)
            self.assertEqual(
                str((root / "models/wake.ppn").resolve()),
                app_config.wake_word.ppn_file,
            )
            self.assertEqual(
                str((root / "models/params.pv").resolve()),
                app_config.wake_word.pv_file,
            )
            self.assertEqual(
                str((root / "voices/de_DE.onnx").resolve()),
                app_config.tts.model_path,
            )
            self.assertEqual(
                str((root / "prompts/system.md").resolve()),
                app_config.llm.system_prompt,
            )
            self.assertEqual(
                str((root / "web/index.html").resolve()),
                app_config.ui_server.index_file,
            )

    def test_load_app_config_rejects_secret_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.toml"
            _write_text(
                config_path,
                textwrap.dedent(
                    """
                    [wake_word]
                    ppn_file = "wake.ppn"
                    pv_file = "params.pv"

                    [oracle]
                    google_calendar_id = "private-id"
                    """
                ).strip(),
            )

            with self.assertRaises(AppConfigurationError) as context:
                load_app_config(str(config_path))

            self.assertIn("oracle.google_calendar_id", str(context.exception))

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
            _write_text(executable_dir_config, "[wake_word]\nppn_file='a'\npv_file='b'\n")
            executable = Path(exe_dir) / "main"

            with patch.dict(os.environ, {}, clear=True):
                with patch("app_config.Path.cwd", return_value=cwd):
                    with patch.object(sys, "frozen", True, create=True):
                        with patch.object(sys, "executable", str(executable), create=True):
                            resolved = resolve_config_path()

            self.assertEqual(executable_dir_config.resolve(), resolved)


if __name__ == "__main__":
    unittest.main()
