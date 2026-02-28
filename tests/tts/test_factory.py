import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

_SRC_DIR = Path(__file__).resolve().parents[2] / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

# Import tts.factory without executing src/tts/__init__.py.
_TTS_DIR = Path(__file__).resolve().parents[2] / "src" / "tts"
if "tts" not in sys.modules:
    _pkg = types.ModuleType("tts")
    _pkg.__path__ = [str(_TTS_DIR)]  # type: ignore[attr-defined]
    sys.modules["tts"] = _pkg

from tts.config import TTSConfigurationError
from tts.factory import create_tts_config


class TTSFactoryTests(unittest.TestCase):
    def test_create_tts_config_happy_path(self) -> None:
        settings = SimpleNamespace()
        expected_config = object()

        with patch(
            "tts.factory.TTSConfig.from_settings",
            return_value=expected_config,
        ) as config_from_settings:
            result = create_tts_config(tts=settings)

        self.assertIs(result, expected_config)
        config_from_settings.assert_called_once_with(settings)

    def test_create_tts_config_propagates_validation_errors(self) -> None:
        with patch(
            "tts.factory.TTSConfig.from_settings",
            side_effect=TTSConfigurationError("invalid tts config"),
        ):
            with self.assertRaises(TTSConfigurationError) as error:
                create_tts_config(tts=SimpleNamespace())

        self.assertIn("invalid tts config", str(error.exception))


if __name__ == "__main__":
    unittest.main()
