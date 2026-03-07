from __future__ import annotations

import builtins
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

from oracle.errors import OracleDependencyError, OracleReadError
from oracle.sensor.temt6000_sensor import TEMT6000Sensor


def _build_import_hook(
    *,
    ads_error: Exception | None = None,
    raw_reading: int = 16383,
    init_error: Exception | None = None,
):
    real_import = builtins.__import__

    class _FakeADS1115:
        def __init__(self, *, address, busnum):
            if init_error is not None:
                raise init_error
            self._raw = raw_reading

        def read_adc(self, channel, *, gain):
            return self._raw

    fake_ads_module = types.ModuleType("Adafruit_ADS1x15")
    fake_ads_module.ADS1115 = _FakeADS1115

    def _hook(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "Adafruit_ADS1x15":
            if ads_error is not None:
                raise ads_error
            return fake_ads_module
        return real_import(name, globals, locals, fromlist, level)

    return _hook


class TEMT6000SensorTests(unittest.TestCase):
    def test_valid_adc_reading_computes_illuminance_and_intensity_correctly(self) -> None:
        """raw=16383 → illuminance_lux and light_intensity_pct computed via ADC formula (AC #2)."""
        with patch("builtins.__import__", side_effect=_build_import_hook(raw_reading=16383)):
            sensor = TEMT6000Sensor()
            readings = sensor.get_readings()

        # raw=16383, max_raw=32767, adc_full_scale=4.096V, resistor=10kΩ, lux_per_µA=2.0
        # volts ≈ 2.0479, microamps ≈ 204.79, lux ≈ 409.59, intensity ≈ 50.0
        self.assertEqual(409.59, readings["illuminance_lux"])
        self.assertEqual(50.0, readings["light_intensity_pct"])

    def test_raw_zero_yields_zero_lux_and_zero_intensity(self) -> None:
        """raw=0 → illuminance_lux=0.0 and light_intensity_pct=0.0 (edge case: non-negative clamp, AC #2)."""
        with patch("builtins.__import__", side_effect=_build_import_hook(raw_reading=0)):
            sensor = TEMT6000Sensor()
            readings = sensor.get_readings()

        self.assertEqual(0.0, readings["illuminance_lux"])
        self.assertEqual(0.0, readings["light_intensity_pct"])

    def test_missing_adafruit_ads1x15_raises_oracle_dependency_error(self) -> None:
        """Missing Adafruit_ADS1x15 package → OracleDependencyError with actionable message (AC #5)."""
        error = ImportError("No module named 'Adafruit_ADS1x15'")
        with patch(
            "builtins.__import__",
            side_effect=_build_import_hook(ads_error=error),
        ):
            with self.assertRaises(OracleDependencyError) as context:
                TEMT6000Sensor()

        self.assertIn("Adafruit_ADS1x15", str(context.exception))

    def test_ads1115_init_failure_raises_oracle_read_error(self) -> None:
        """ADS1115 hardware init failure → OracleReadError (AC #5)."""
        with patch(
            "builtins.__import__",
            side_effect=_build_import_hook(init_error=OSError("I2C init failed")),
        ):
            with self.assertRaises(OracleReadError) as context:
                TEMT6000Sensor()

        self.assertIn("ADS1115", str(context.exception))

    def test_channel_out_of_range_raises_value_error(self) -> None:
        """channel=4 is outside valid range 0..3 → ValueError raised before ADC init (AC #5)."""
        with self.assertRaises(ValueError) as context:
            TEMT6000Sensor(channel=4)

        self.assertIn("channel", str(context.exception).lower())


if __name__ == "__main__":
    unittest.main()
