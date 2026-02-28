import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

_SRC_DIR = Path(__file__).resolve().parents[2] / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

# Import stt.factory without executing src/stt/__init__.py.
_STT_DIR = Path(__file__).resolve().parents[2] / "src" / "stt"
if "stt" not in sys.modules:
    _pkg = types.ModuleType("stt")
    _pkg.__path__ = [str(_STT_DIR)]  # type: ignore[attr-defined]
    sys.modules["stt"] = _pkg

from stt.config import ConfigurationError
from stt.factory import create_stt_resources


class STTFactoryTests(unittest.TestCase):
    def test_create_stt_resources_happy_path(self) -> None:
        wake_word_settings = SimpleNamespace()
        stt_settings = SimpleNamespace()
        wake_word_config = object()
        stt_config = object()

        with patch(
            "stt.factory.WakeWordConfig.from_settings",
            return_value=wake_word_config,
        ) as wakeword_from_settings, patch(
            "stt.factory.STTConfig.from_settings",
            return_value=stt_config,
        ) as stt_from_settings:
            returned_wakeword, returned_stt = create_stt_resources(
                wake_word=wake_word_settings,
                stt=stt_settings,
                pico_key="secret",
            )

        self.assertIs(returned_wakeword, wake_word_config)
        self.assertIs(returned_stt, stt_config)
        wakeword_from_settings.assert_called_once_with(
            pico_voice_access_key="secret",
            settings=wake_word_settings,
        )
        stt_from_settings.assert_called_once_with(stt_settings)

    def test_create_stt_resources_propagates_configuration_errors(self) -> None:
        with patch(
            "stt.factory.WakeWordConfig.from_settings",
            side_effect=ConfigurationError("invalid wakeword"),
        ):
            with self.assertRaises(ConfigurationError) as error:
                create_stt_resources(
                    wake_word=SimpleNamespace(),
                    stt=SimpleNamespace(),
                    pico_key="secret",
                )

        self.assertIn("invalid wakeword", str(error.exception))


if __name__ == "__main__":
    unittest.main()
