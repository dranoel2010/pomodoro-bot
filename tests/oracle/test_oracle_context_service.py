import datetime as dt
import logging
import sys
import types
import unittest
from pathlib import Path

# Import oracle modules without executing src/oracle/__init__.py.
_ORACLE_DIR = Path(__file__).resolve().parents[2] / "src" / "oracle"
if "oracle" not in sys.modules:
    _pkg = types.ModuleType("oracle")
    _pkg.__path__ = [str(_ORACLE_DIR)]  # type: ignore[attr-defined]
    sys.modules["oracle"] = _pkg

from oracle.config import OracleConfig
from oracle.contracts import OracleProviders
from oracle.service import OracleContextService


class _Clock:
    def __init__(self, values: list[float]):
        self._values = list(values)
        self._index = 0

    def __call__(self) -> float:
        if self._index >= len(self._values):
            raise RuntimeError("Clock exhausted")
        value = self._values[self._index]
        self._index += 1
        return value


class _AirQualityStub:
    def __init__(self):
        self.calls = 0

    def get_readings(self):
        self.calls += 1
        return {"aqi": 42}


class _LightStub:
    def __init__(self):
        self.calls = 0

    def get_readings(self):
        self.calls += 1
        return {"illuminance_lux": 123.4}


class _CalendarStub:
    def __init__(self, responses: list[object], event_id: str = "evt-1"):
        self._responses = list(responses)
        self._event_id = event_id
        self.get_calls: list[dict[str, object]] = []
        self.add_calls: list[dict[str, object]] = []

    def get_events(self, *, max_results: int = 10, time_min=None):
        self.get_calls.append({"max_results": max_results, "time_min": time_min})
        if not self._responses:
            return []
        value = self._responses.pop(0)
        if isinstance(value, Exception):
            raise value
        return value

    def add_event(self, *, summary: str, start: dt.datetime, end: dt.datetime) -> str:
        self.add_calls.append({"summary": summary, "start": start, "end": end})
        return self._event_id


def _config(*, enabled: bool = True, sensor_ttl: float = 10.0, calendar_ttl: float = 10.0):
    return OracleConfig(
        enabled=enabled,
        ens160_enabled=False,
        temt6000_enabled=False,
        calendar_enabled=False,
        ens160_temperature_compensation_c=25.0,
        ens160_humidity_compensation_pct=50.0,
        temt6000_channel=0,
        temt6000_gain=1,
        temt6000_adc_address=0x48,
        temt6000_busnum=1,
        calendar_id="calendar-id",
        calendar_service_account_file="/tmp/service.json",
        calendar_max_results=5,
        sensor_cache_ttl_seconds=sensor_ttl,
        calendar_cache_ttl_seconds=calendar_ttl,
    )


class OracleContextServiceTests(unittest.TestCase):
    def test_disabled_service_only_returns_now_local(self) -> None:
        now = dt.datetime(2026, 2, 21, 10, 0, tzinfo=dt.timezone.utc)
        air = _AirQualityStub()
        light = _LightStub()
        service = OracleContextService(
            _config(enabled=False),
            logger=logging.getLogger("test"),
            providers=OracleProviders(ens160=air, temt6000=light, calendar=None),
            now_fn=lambda: now,
        )

        payload = service.build_environment_payload()
        self.assertEqual({"now_local": "2026-02-21T10:00:00+00:00"}, payload)
        self.assertEqual(0, air.calls)
        self.assertEqual(0, light.calls)

    def test_sensor_payload_uses_ttl_cache(self) -> None:
        now = dt.datetime(2026, 2, 21, 10, 0, tzinfo=dt.timezone.utc)
        air = _AirQualityStub()
        light = _LightStub()
        clock = _Clock([100.0, 101.0, 112.0])
        service = OracleContextService(
            _config(enabled=True, sensor_ttl=10.0),
            logger=logging.getLogger("test"),
            providers=OracleProviders(ens160=air, temt6000=light, calendar=None),
            monotonic_fn=clock,
            now_fn=lambda: now,
        )

        payload1 = service.build_environment_payload()
        payload2 = service.build_environment_payload()
        payload3 = service.build_environment_payload()

        self.assertEqual(2, air.calls)
        self.assertEqual(2, light.calls)
        self.assertEqual(123.4, payload1["light_level_lux"])
        self.assertEqual({"aqi": 42}, payload2["air_quality"])
        self.assertEqual({"aqi": 42}, payload3["air_quality"])

    def test_calendar_cache_returns_previous_on_refresh_error(self) -> None:
        now = dt.datetime(2026, 2, 21, 10, 0, tzinfo=dt.timezone.utc)
        events = [{"summary": "Standup", "start": "2026-02-21T10:30:00+00:00"}]
        calendar = _CalendarStub([events, RuntimeError("boom")])
        clock = _Clock([0.0, 0.0, 10.0, 10.0])
        service = OracleContextService(
            _config(enabled=True, sensor_ttl=30.0, calendar_ttl=5.0),
            logger=logging.getLogger("test"),
            providers=OracleProviders(calendar=calendar),
            monotonic_fn=clock,
            now_fn=lambda: now,
        )

        payload1 = service.build_environment_payload()
        payload2 = service.build_environment_payload()

        self.assertEqual(events, payload1["upcoming_events"])
        self.assertEqual(events, payload2["upcoming_events"])
        self.assertEqual(2, len(calendar.get_calls))

    def test_list_upcoming_events_uses_override_and_default_limits(self) -> None:
        calendar = _CalendarStub([[], []])
        service = OracleContextService(
            _config(enabled=True),
            logger=logging.getLogger("test"),
            providers=OracleProviders(calendar=calendar),
        )

        when = dt.datetime(2026, 2, 21, 12, 0, tzinfo=dt.timezone.utc)
        service.list_upcoming_events(max_results=2, time_min=when)
        service.list_upcoming_events(max_results=0, time_min=when)

        self.assertEqual(2, calendar.get_calls[0]["max_results"])
        self.assertEqual(when, calendar.get_calls[0]["time_min"])
        self.assertEqual(5, calendar.get_calls[1]["max_results"])

    def test_add_event_delegates_to_calendar_and_raises_without_calendar(self) -> None:
        calendar = _CalendarStub([], event_id="evt-42")
        service = OracleContextService(
            _config(enabled=True),
            logger=logging.getLogger("test"),
            providers=OracleProviders(calendar=calendar),
        )

        start = dt.datetime(2026, 2, 21, 12, 0, tzinfo=dt.timezone.utc)
        end = dt.datetime(2026, 2, 21, 12, 30, tzinfo=dt.timezone.utc)
        event_id = service.add_event(title="Review", start=start, end=end)
        self.assertEqual("evt-42", event_id)
        self.assertEqual("Review", calendar.add_calls[0]["summary"])

        missing_calendar = OracleContextService(
            _config(enabled=True),
            logger=logging.getLogger("test"),
            providers=OracleProviders(),
        )
        with self.assertRaises(RuntimeError):
            missing_calendar.add_event(title="X", start=start, end=end)


if __name__ == "__main__":
    unittest.main()
