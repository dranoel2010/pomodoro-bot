"""ENS160 air-quality sensor adapter."""

from __future__ import annotations

import logging
from typing import Any, Mapping, Optional

from ..errors import OracleDependencyError, OracleReadError


class ENS160Sensor:
    """ENS160 air quality sensor wrapper."""

    def __init__(
        self,
        name: str = "ens160",
        *,
        temperature_compensation_c: float = 25.0,
        humidity_compensation_pct: float = 50.0,
        logger: Optional[logging.Logger] = None,
    ):
        self._name = name
        self._temperature_compensation_c = float(temperature_compensation_c)
        self._humidity_compensation_pct = float(humidity_compensation_pct)
        self._logger = logger or logging.getLogger(f"{__name__}.{name}")
        self._sensor = self._create_sensor()

    def _create_sensor(self):
        try:
            import board
            import adafruit_ens160
        except ImportError as error:  # pragma: no cover - depends on hardware env
            raise OracleDependencyError(
                "ENS160 dependencies missing. Install adafruit-blinka and "
                "adafruit-circuitpython-ens160."
            ) from error

        try:
            i2c = board.I2C()
            sensor = adafruit_ens160.ENS160(i2c)
            sensor.temperature_compensation = self._temperature_compensation_c
            sensor.humidity_compensation = self._humidity_compensation_pct
            return sensor
        except Exception as error:  # pragma: no cover - depends on hardware env
            raise OracleReadError(f"Failed to initialize ENS160 sensor: {error}") from error

    def get_readings(self) -> Mapping[str, Any]:
        """Read current air-quality values."""
        try:
            readings = {
                "aqi": int(self._sensor.AQI),
                "tvoc_ppb": int(self._sensor.TVOC),
                "eco2_ppm": int(self._sensor.eCO2),
            }
            return readings
        except Exception as error:  # pragma: no cover - depends on hardware env
            raise OracleReadError(f"Failed to read ENS160 sensor: {error}") from error
