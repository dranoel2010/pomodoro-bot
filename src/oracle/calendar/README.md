# oracle.calendar module

## Purpose
Google Calendar adapter used by runtime calendar tool calls.

## Key files
- `google_calendar.py`: read/write wrapper with normalized event payloads and validation.

## Configuration
Runtime inputs come from oracle config and secrets:
- `oracle.google_calendar_enabled`
- `oracle.google_calendar_max_results`
- `ORACLE_GOOGLE_CALENDAR_ID`
- `ORACLE_GOOGLE_SERVICE_ACCOUNT_FILE`

Dependencies:
- `google-auth`
- `google-api-python-client`

## Integration notes
- Supports listing upcoming events and creating events.
- Write operations require non-read-only initialization.
- All failures are surfaced as oracle-specific exceptions.
