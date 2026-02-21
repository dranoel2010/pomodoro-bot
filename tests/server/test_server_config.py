import sys
import tempfile
import types
import unittest
from pathlib import Path

from app_config_schema import UIServerSettings

# Import server.config without executing src/server/__init__.py.
_SERVER_DIR = Path(__file__).resolve().parents[2] / "src" / "server"
if "server" not in sys.modules:
    _pkg = types.ModuleType("server")
    _pkg.__path__ = [str(_SERVER_DIR)]  # type: ignore[attr-defined]
    sys.modules["server"] = _pkg

from server.config import ServerConfigurationError, UIServerConfig


class UIServerConfigTests(unittest.TestCase):
    def test_from_settings_uses_selected_builtin_ui(self) -> None:
        settings = UIServerSettings(
            enabled=True,
            host="127.0.0.1",
            port=8765,
            ui="miro",
            index_file="",
        )

        config = UIServerConfig.from_settings(settings)

        self.assertEqual("miro", config.ui)
        self.assertEqual(
            ("web_ui", "miro", "index.html"),
            Path(config.index_file).parts[-3:],
        )
        self.assertTrue(Path(config.index_file).is_file())

    def test_from_settings_rejects_unknown_ui(self) -> None:
        settings = UIServerSettings(
            enabled=True,
            host="127.0.0.1",
            port=8765,
            ui="retro",
            index_file="",
        )

        with self.assertRaises(ServerConfigurationError):
            UIServerConfig.from_settings(settings)

    def test_from_settings_prefers_explicit_index_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            custom = Path(temp_dir) / "index.html"
            custom.write_text("<html></html>", encoding="utf-8")

            settings = UIServerSettings(
                enabled=True,
                host="127.0.0.1",
                port=8765,
                ui="miro",
                index_file=str(custom),
            )

            config = UIServerConfig.from_settings(settings)
            self.assertEqual(str(custom), config.index_file)


if __name__ == "__main__":
    unittest.main()
