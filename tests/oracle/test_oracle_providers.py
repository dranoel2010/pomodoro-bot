import logging
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

# Import oracle modules without executing src/oracle/__init__.py.
_ORACLE_DIR = Path(__file__).resolve().parents[2] / "src" / "oracle"
if "oracle" not in sys.modules:
    _pkg = types.ModuleType("oracle")
    _pkg.__path__ = [str(_ORACLE_DIR)]  # type: ignore[attr-defined]
    sys.modules["oracle"] = _pkg

from oracle.config import OracleConfig
from oracle.providers import build_oracle_providers


def _config(*, enabled: bool = True, calendar_enabled: bool = False):
    return OracleConfig(
        enabled=enabled,
        ens160_enabled=True,
        temt6000_enabled=True,
        calendar_enabled=calendar_enabled,
        ens160_temperature_compensation_c=25.0,
        ens160_humidity_compensation_pct=50.0,
        temt6000_channel=0,
        temt6000_gain=1,
        temt6000_adc_address=0x48,
        temt6000_busnum=1,
        calendar_id="calendar-id",
        calendar_service_account_file="/tmp/service.json",
        calendar_max_results=5,
        sensor_cache_ttl_seconds=10.0,
        calendar_cache_ttl_seconds=10.0,
    )


class OracleProvidersTests(unittest.TestCase):
    def test_disabled_config_skips_provider_initialization(self) -> None:
        with patch("oracle.providers.ENS160Sensor") as ens160_cls:
            with patch("oracle.providers.TEMT6000Sensor") as temt6000_cls:
                with patch("oracle.providers.GoogleCalendar") as calendar_cls:
                    providers = build_oracle_providers(
                        _config(enabled=False),
                        logger=logging.getLogger("test"),
                    )

        self.assertIsNone(providers.ens160)
        self.assertIsNone(providers.temt6000)
        self.assertIsNone(providers.calendar)
        ens160_cls.assert_not_called()
        temt6000_cls.assert_not_called()
        calendar_cls.assert_not_called()

    def test_enabled_config_initializes_available_providers(self) -> None:
        with patch("oracle.providers.ENS160Sensor", return_value=object()) as ens160_cls:
            with patch(
                "oracle.providers.TEMT6000Sensor",
                return_value=object(),
            ) as temt6000_cls:
                with patch(
                    "oracle.providers.GoogleCalendar",
                    return_value=object(),
                ) as calendar_cls:
                    providers = build_oracle_providers(
                        _config(enabled=True, calendar_enabled=True),
                        logger=logging.getLogger("test"),
                    )

        self.assertIsNotNone(providers.ens160)
        self.assertIsNotNone(providers.temt6000)
        self.assertIsNotNone(providers.calendar)
        ens160_cls.assert_called_once()
        temt6000_cls.assert_called_once()
        calendar_cls.assert_called_once()


if __name__ == "__main__":
    unittest.main()
