"""TEMT6000 light-sensor adapter backed by an ADS1115 ADC."""

from __future__ import annotations

import logging
from typing import Any, Mapping, Optional

from ..errors import OracleDependencyError, OracleReadError


class TEMT6000Sensor:
    """TEMT6000 ambient light sensor via ADS1115 ADC."""

    def __init__(
        self,
        name: str = "temt6000",
        *,
        channel: int = 0,
        gain: int = 1,
        adc_address: int = 0x48,
        busnum: int = 1,
        adc_full_scale_volts: float = 4.096,
        resistor_ohms: float = 10_000.0,
        lux_per_microamp: float = 2.0,
        logger: Optional[logging.Logger] = None,
    ):
        if channel not in (0, 1, 2, 3):
            raise ValueError(f"TEMT6000 channel must be 0..3, got: {channel}")
        if resistor_ohms <= 0:
            raise ValueError("TEMT6000 resistor_ohms must be positive")
        if adc_full_scale_volts <= 0:
            raise ValueError("TEMT6000 adc_full_scale_volts must be positive")

        self._name = name
        self._channel = channel
        self._gain = gain
        self._adc_full_scale_volts = float(adc_full_scale_volts)
        self._resistor_ohms = float(resistor_ohms)
        self._lux_per_microamp = float(lux_per_microamp)
        self._logger = logger or logging.getLogger(f"{__name__}.{name}")
        self._adc = self._create_adc(adc_address=adc_address, busnum=busnum)

    def _create_adc(self, *, adc_address: int, busnum: int):
        try:
            import Adafruit_ADS1x15
        except ImportError as error:  # pragma: no cover - depends on hardware env
            raise OracleDependencyError(
                "TEMT6000 dependencies missing. Install Adafruit_ADS1x15."
            ) from error

        try:
            return Adafruit_ADS1x15.ADS1115(address=adc_address, busnum=busnum)
        except Exception as error:  # pragma: no cover - depends on hardware env
            raise OracleReadError(f"Failed to initialize ADS1115: {error}") from error

    def get_readings(self) -> Mapping[str, Any]:
        """Read current light values from configured ADC channel."""
        try:
            raw = int(self._adc.read_adc(self._channel, gain=self._gain))
        except Exception as error:  # pragma: no cover - depends on hardware env
            raise OracleReadError(f"Failed to read TEMT6000 sensor: {error}") from error

        # ADS1115 in single-ended mode returns a non-negative 15-bit-ish value.
        raw = max(raw, 0)
        max_raw = 32767.0

        volts = (raw / max_raw) * self._adc_full_scale_volts
        microamps = (volts / self._resistor_ohms) * 1_000_000.0
        lux = max(0.0, microamps * self._lux_per_microamp)
        intensity_pct = max(0.0, min(100.0, (raw / max_raw) * 100.0))

        readings = {
            "raw": raw,
            "volts": round(volts, 4),
            "microamps": round(microamps, 2),
            "illuminance_lux": round(lux, 2),
            "light_intensity_pct": round(intensity_pct, 2),
        }
        return readings


# Backward-compatibility alias for previous typoed class name.
TMT6000Sensor = TEMT6000Sensor
