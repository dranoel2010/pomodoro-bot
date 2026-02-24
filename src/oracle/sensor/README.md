# oracle.sensor module

## Purpose
Hardware sensor adapters for air quality and ambient light context.

## Key files
- `ens160_sensor.py`: ENS160 air-quality readings (`aqi`, `tvoc_ppb`, `eco2_ppm`).
- `temt6000_sensor.py`: TEMT6000 luminance readings via ADS1115.

## Configuration
From `config.toml` (`[oracle]`):
- `ens160_enabled`
- `temt6000_enabled`
- `ens160_temperature_compensation_c`
- `ens160_humidity_compensation_pct`
- `temt6000_channel`
- `temt6000_gain`
- `temt6000_adc_address`
- `temt6000_busnum`

## Integration notes
- Provider initialization is best-effort; unavailable hardware is logged and skipped.
- Sensor data is consumed through `OracleContextService` with TTL caching.
