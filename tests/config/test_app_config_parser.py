import os
import stat
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest.mock import patch

from config import AppConfigurationError, load_app_config
from config import parse_app_config


def _minimal_toml_bytes() -> bytes:
    return textwrap.dedent(
        """
        [wake_word]
        ppn_file = "wake.ppn"
        pv_file = "params.pv"
        """
    ).strip().encode("utf-8")


class ParseAppConfigBytesTests(unittest.TestCase):
    """Direct unit tests for the parse_app_config(bytes) interface."""

    def _base_dir(self) -> Path:
        return Path(tempfile.gettempdir())

    def test_valid_bytes_returns_app_config(self) -> None:
        config = parse_app_config(
            _minimal_toml_bytes(),
            base_dir=self._base_dir(),
            source_file="test.toml",
        )
        self.assertEqual("test.toml", config.source_file)

    def test_invalid_toml_raises_app_configuration_error(self) -> None:
        bad_toml = b"[this is not valid toml\x00"
        with self.assertRaises(AppConfigurationError) as ctx:
            parse_app_config(bad_toml, base_dir=self._base_dir(), source_file="bad.toml")
        self.assertIn("Failed to parse config TOML", str(ctx.exception))

    def test_non_utf8_bytes_raises_app_configuration_error(self) -> None:
        non_utf8 = b"\xff\xfe not utf-8"
        with self.assertRaises(AppConfigurationError) as ctx:
            parse_app_config(non_utf8, base_dir=self._base_dir(), source_file="bad.toml")
        self.assertIn("Failed to parse config TOML", str(ctx.exception))

    def test_toml_decode_error_message_preserved(self) -> None:
        with self.assertRaises(AppConfigurationError) as ctx:
            parse_app_config(b"key = !!!", base_dir=self._base_dir(), source_file="x.toml")
        self.assertIn("Failed to parse config TOML", str(ctx.exception))

    def test_cpu_cores_parsed_from_bytes(self) -> None:
        toml = textwrap.dedent(
            """
            [wake_word]
            ppn_file = "wake.ppn"
            pv_file = "params.pv"

            [stt]
            cpu_cores = [0, 1]

            [tts]
            cpu_cores = [2]

            [llm]
            cpu_cores = [3, 4, 5]
            """
        ).strip().encode("utf-8")

        config = parse_app_config(toml, base_dir=self._base_dir(), source_file="t.toml")
        self.assertEqual((0, 1), config.stt.cpu_cores)
        self.assertEqual((2,), config.tts.cpu_cores)
        self.assertEqual((3, 4, 5), config.llm.cpu_cores)


class LoadAppConfigOSErrorTests(unittest.TestCase):
    """Tests for the OSError handling path in load_app_config."""

    def test_unreadable_file_raises_app_configuration_error(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".toml", delete=False) as fh:
            fh.write(b"[wake_word]\nppn_file = 'a'\npv_file = 'b'\n")
            tmp_path = fh.name
        try:
            os.chmod(tmp_path, 0o000)
            with self.assertRaises(AppConfigurationError) as ctx:
                load_app_config(tmp_path)
            self.assertIn("Failed to read config file", str(ctx.exception))
        finally:
            os.chmod(tmp_path, stat.S_IRUSR | stat.S_IWUSR)
            os.unlink(tmp_path)


if __name__ == "__main__":
    unittest.main()
