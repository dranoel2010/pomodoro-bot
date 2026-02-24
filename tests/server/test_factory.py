import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

_SRC_DIR = Path(__file__).resolve().parents[2] / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

# Import server.factory without executing src/server/__init__.py.
_SERVER_DIR = Path(__file__).resolve().parents[2] / "src" / "server"
if "server" not in sys.modules:
    _pkg = types.ModuleType("server")
    _pkg.__path__ = [str(_SERVER_DIR)]  # type: ignore[attr-defined]
    sys.modules["server"] = _pkg

from contracts.ui_protocol import STATE_IDLE
from server.factory import create_ui_server

sys.modules["server"].create_ui_server = create_ui_server


class _UIServerStub:
    def __init__(self, *, config, logger):
        del logger
        self.host = config.host
        self.port = config.port
        self.start_calls: list[float] = []
        self.state_calls: list[tuple[str, str | None, dict[str, object]]] = []

    def start(self, timeout_seconds: float = 5.0) -> None:
        self.start_calls.append(timeout_seconds)

    def publish_state(self, state: str, *, message=None, **payload) -> None:
        self.state_calls.append((state, message, payload))


class ServerFactoryTests(unittest.TestCase):
    def test_create_ui_server_happy_path(self) -> None:
        logger = MagicMock()
        config = SimpleNamespace(enabled=True, host="127.0.0.1", port=8765)

        with patch(
            "server.factory.UIServerConfig.from_settings",
            return_value=config,
        ), patch("server.factory.UIServer", _UIServerStub):
            result = create_ui_server(
                ui=SimpleNamespace(),
                logger=logger,
            )

        self.assertIsInstance(result, _UIServerStub)
        self.assertEqual([5.0], result.start_calls)
        self.assertEqual(
            [(STATE_IDLE, "UI server connected", {})],
            result.state_calls,
        )
        logger.warning.assert_not_called()

    def test_create_ui_server_returns_none_when_disabled(self) -> None:
        logger = MagicMock()
        config = SimpleNamespace(enabled=False)

        with patch(
            "server.factory.UIServerConfig.from_settings",
            return_value=config,
        ):
            result = create_ui_server(
                ui=SimpleNamespace(),
                logger=logger,
            )

        self.assertIsNone(result)
        logger.warning.assert_not_called()

    def test_create_ui_server_degrades_gracefully_on_error(self) -> None:
        logger = MagicMock()

        with patch(
            "server.factory.UIServerConfig.from_settings",
            side_effect=RuntimeError("invalid ui config"),
        ):
            result = create_ui_server(
                ui=SimpleNamespace(),
                logger=logger,
            )

        self.assertIsNone(result)
        logger.warning.assert_called_once()
        warning_args = logger.warning.call_args.args
        self.assertEqual(
            "UI server unavailable (%s: %s); continuing startup without it.",
            warning_args[0],
        )
        self.assertEqual("RuntimeError", warning_args[1])
        self.assertEqual("invalid ui config", str(warning_args[2]))
        logger.debug.assert_called_once_with(
            "UI server initialization traceback",
            exc_info=True,
        )


if __name__ == "__main__":
    unittest.main()
