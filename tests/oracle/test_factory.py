import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

_SRC_DIR = Path(__file__).resolve().parents[2] / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

# Import oracle.factory without executing src/oracle/__init__.py.
_ORACLE_DIR = Path(__file__).resolve().parents[2] / "src" / "oracle"
if "oracle" not in sys.modules:
    _pkg = types.ModuleType("oracle")
    _pkg.__path__ = [str(_ORACLE_DIR)]  # type: ignore[attr-defined]
    sys.modules["oracle"] = _pkg

from oracle.factory import create_oracle_service
from contracts import StartupError

sys.modules["oracle"].create_oracle_service = create_oracle_service


class OracleFactoryTests(unittest.TestCase):
    def test_create_oracle_service_happy_path(self) -> None:
        settings = SimpleNamespace()
        logger = MagicMock()
        oracle_config = object()
        oracle_service = object()

        with patch(
            "oracle.factory.OracleConfig.from_settings",
            return_value=oracle_config,
        ) as config_from_settings, patch(
            "oracle.factory.OracleContextService",
            return_value=oracle_service,
        ) as context_service:
            result = create_oracle_service(
                oracle=settings,
                calendar_id="calendar-id",
                service_account_file="/tmp/service.json",
                logger=logger,
            )

        self.assertIs(result, oracle_service)
        config_from_settings.assert_called_once_with(
            settings,
            calendar_id="calendar-id",
            calendar_service_account_file="/tmp/service.json",
        )
        context_service.assert_called_once_with(
            config=oracle_config,
            logger=unittest.mock.ANY,
        )
        logger.warning.assert_not_called()

    def test_create_oracle_service_degrades_gracefully_on_error(self) -> None:
        logger = MagicMock()

        with patch(
            "oracle.factory.OracleConfig.from_settings",
            side_effect=RuntimeError("oracle bootstrap failed"),
        ):
            result = create_oracle_service(
                oracle=SimpleNamespace(),
                calendar_id="calendar-id",
                service_account_file="/tmp/service.json",
                logger=logger,
            )

        self.assertIsNone(result)
        logger.warning.assert_called_once()
        warning_args = logger.warning.call_args.args
        self.assertEqual(
            "Oracle context unavailable (%s: %s); continuing startup without it.",
            warning_args[0],
        )
        self.assertEqual("RuntimeError", warning_args[1])
        self.assertEqual("oracle bootstrap failed", str(warning_args[2]))
        logger.debug.assert_called_once_with(
            "Oracle context initialization traceback",
            exc_info=True,
        )

    def test_create_oracle_service_raises_on_unexpected_exception(self) -> None:
        logger = MagicMock()

        with patch(
            "oracle.factory.OracleConfig.from_settings",
            return_value=object(),
        ), patch(
            "oracle.factory.OracleContextService",
            side_effect=TypeError("unexpected"),
        ):
            with self.assertRaises(StartupError):
                create_oracle_service(
                    oracle=SimpleNamespace(),
                    calendar_id="calendar-id",
                    service_account_file="/tmp/service.json",
                    logger=logger,
                )


if __name__ == "__main__":
    unittest.main()
