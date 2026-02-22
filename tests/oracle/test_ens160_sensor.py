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
from oracle.sensor.ens160_sensor import ENS160Sensor


def _build_import_hook(*, adafruit_error: Exception | None = None, board_error: Exception | None = None):
    real_import = builtins.__import__

    class _FakeENS160:
        def __init__(self, _i2c):
            self.temperature_compensation = None
            self.humidity_compensation = None
            self.AQI = 2
            self.TVOC = 321
            self.eCO2 = 700

    fake_ens160_module = types.ModuleType("adafruit_ens160")
    fake_ens160_module.ENS160 = _FakeENS160

    fake_board_module = types.ModuleType("board")
    fake_board_module.I2C = lambda: object()

    def _hook(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "adafruit_ens160":
            if adafruit_error is not None:
                raise adafruit_error
            return fake_ens160_module
        if name == "board":
            if board_error is not None:
                raise board_error
            return fake_board_module
        return real_import(name, globals, locals, fromlist, level)

    return _hook


class ENS160SensorTests(unittest.TestCase):
    def test_reads_values_and_applies_compensation(self) -> None:
        with patch("builtins.__import__", side_effect=_build_import_hook()):
            sensor = ENS160Sensor(
                temperature_compensation_c=23.5,
                humidity_compensation_pct=55.0,
            )

        self.assertEqual(
            {"aqi": 2, "tvoc_ppb": 321, "eco2_ppm": 700},
            sensor.get_readings(),
        )
        self.assertEqual(23.5, sensor._sensor.temperature_compensation)
        self.assertEqual(55.0, sensor._sensor.humidity_compensation)

    def test_missing_pkg_resources_reports_actionable_dependency_error(self) -> None:
        error = ModuleNotFoundError(
            "No module named 'pkg_resources'",
            name="pkg_resources",
        )
        with patch(
            "builtins.__import__",
            side_effect=_build_import_hook(board_error=error),
        ):
            with self.assertRaises(OracleDependencyError) as context:
                ENS160Sensor()

        message = str(context.exception)
        self.assertIn("pkg_resources", message)
        self.assertIn("setuptools<81", message)

    def test_unsupported_board_is_reported_as_runtime_error(self) -> None:
        with patch(
            "builtins.__import__",
            side_effect=_build_import_hook(board_error=NotImplementedError("unsupported board")),
        ):
            with self.assertRaises(OracleReadError) as context:
                ENS160Sensor()

        self.assertIn("unsupported on this host", str(context.exception))

    def test_missing_ens160_module_reports_dependency_error(self) -> None:
        error = ModuleNotFoundError(
            "No module named 'adafruit_ens160'",
            name="adafruit_ens160",
        )
        with patch(
            "builtins.__import__",
            side_effect=_build_import_hook(adafruit_error=error),
        ):
            with self.assertRaises(OracleDependencyError) as context:
                ENS160Sensor()

        self.assertIn("adafruit_ens160", str(context.exception))


if __name__ == "__main__":
    unittest.main()
