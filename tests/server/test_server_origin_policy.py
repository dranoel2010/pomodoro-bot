from __future__ import annotations

import sys
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


class UIServerOriginPolicyTests(unittest.TestCase):
    def test_loopback_host_defaults_to_local_origins(self) -> None:
        settings = UIServerSettings(
            enabled=True,
            host="127.0.0.1",
            port=8765,
            ui="jarvis",
            index_file="",
        )

        config = UIServerConfig.from_settings(settings)
        self.assertEqual(
            (
                "http://127.0.0.1:8765",
                "http://localhost:8765",
                "http://[::1]:8765",
                None,
            ),
            config.websocket_origins,
        )

    def test_non_loopback_host_requires_explicit_allowed_origins(self) -> None:
        settings = UIServerSettings(
            enabled=True,
            host="0.0.0.0",
            port=8765,
            ui="jarvis",
            index_file="",
            allowed_origins=(),
        )

        with self.assertRaises(ServerConfigurationError) as ctx:
            UIServerConfig.from_settings(settings)
        self.assertIn("UI_SERVER_ALLOWED_ORIGINS must be set", str(ctx.exception))

    def test_non_loopback_host_uses_configured_allowed_origins(self) -> None:
        settings = UIServerSettings(
            enabled=True,
            host="0.0.0.0",
            port=8765,
            ui="jarvis",
            index_file="",
            allowed_origins=("http://192.168.1.50:8765",),
        )

        config = UIServerConfig.from_settings(settings)
        self.assertEqual(
            ("http://192.168.1.50:8765", None),
            config.websocket_origins,
        )


if __name__ == "__main__":
    unittest.main()
