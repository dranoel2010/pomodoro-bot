# oracle module

Optional environment-context providers used by `src/main.py` to enrich LLM prompts.

## Providers

- `sensor/ens160_sensor.py`: air-quality readings (`aqi`, `tvoc_ppb`, `eco2_ppm`)
- `sensor/temt6000_sensor.py`: ambient light readings (`illuminance_lux`, etc.) via ADS1115
- `calendar/google_calendar.py`: upcoming Google Calendar events

## Runtime behavior

- Providers are optional and initialized from app config (`config.toml`).
- Calendar credentials stay in environment variables (secrets).
- Missing dependencies or unavailable hardware do not crash the app.
- Failed reads are logged and skipped; cached values are reused when possible.

## Environment variables

- `ORACLE_ENABLED` (`true`/`false`, default `true`)
- `ORACLE_ENS160_ENABLED` (`true`/`false`, default `false`)
- `ORACLE_TEMT6000_ENABLED` (`true`/`false`, default `false`)
- `ORACLE_GOOGLE_CALENDAR_ENABLED` (`true`/`false`, default auto when calendar id + service account are set)
- `ORACLE_GOOGLE_CALENDAR_ID` (secret; env only)
- `ORACLE_GOOGLE_SERVICE_ACCOUNT_FILE` (secret path; env only)
- `ORACLE_GOOGLE_CALENDAR_MAX_RESULTS` (default `5`)
- `ORACLE_SENSOR_CACHE_TTL_SECONDS` (default `15`)
- `ORACLE_CALENDAR_CACHE_TTL_SECONDS` (default `60`)
