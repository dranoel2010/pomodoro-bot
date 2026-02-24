# oracle module

## Purpose
Optional environment-context providers used to enrich LLM context and support calendar tools.

## Key files
- `config.py`: typed oracle configuration model.
- `providers.py`: provider factory with graceful degradation.
- `service.py`: cached context aggregation for sensors and calendar.
- `sensor/`: hardware sensor adapters.
- `calendar/`: Google Calendar client wrapper.

## Configuration
From `config.toml` (`[oracle]`):
- `enabled`
- `ens160_enabled`
- `temt6000_enabled`
- `google_calendar_enabled`
- `google_calendar_max_results`
- `sensor_cache_ttl_seconds`
- `calendar_cache_ttl_seconds`
- `ens160_temperature_compensation_c`
- `ens160_humidity_compensation_pct`
- `temt6000_channel`
- `temt6000_gain`
- `temt6000_adc_address`
- `temt6000_busnum`

Secrets from environment:
- `ORACLE_GOOGLE_CALENDAR_ID`
- `ORACLE_GOOGLE_SERVICE_ACCOUNT_FILE`

## Integration notes
- `OracleContextService` is created only when LLM is enabled in `src/main.py`.
- Missing dependencies or unavailable hardware are logged and skipped.
- Calendar and sensor reads are cached by TTL to reduce repeated I/O.
