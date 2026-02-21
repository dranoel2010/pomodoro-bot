import datetime as dt
import json
import sys
import types
import unittest
from pathlib import Path

# Import server.events without executing src/server/__init__.py.
_SERVER_DIR = Path(__file__).resolve().parents[2] / "src" / "server"
if "server" not in sys.modules:
    _pkg = types.ModuleType("server")
    _pkg.__path__ = [str(_SERVER_DIR)]  # type: ignore[attr-defined]
    sys.modules["server"] = _pkg

from server.events import StickyEventStore, make_event


class ServerEventsTests(unittest.TestCase):
    def test_make_event_serializes_timestamp_and_payload(self) -> None:
        now = dt.datetime(2026, 2, 21, 10, 0, tzinfo=dt.timezone.utc)
        raw = make_event("state_update", now_fn=lambda: now, state="idle", message="Ready")
        payload = json.loads(raw)

        self.assertEqual("state_update", payload["type"])
        self.assertEqual(now.isoformat(), payload["timestamp"])
        self.assertEqual("idle", payload["state"])
        self.assertEqual("Ready", payload["message"])

    def test_sticky_store_ignores_non_sticky_events(self) -> None:
        store = StickyEventStore()
        store.remember("hello", '{"type":"hello"}')
        self.assertEqual([], store.snapshot())

    def test_sticky_store_snapshot_follows_stable_order(self) -> None:
        store = StickyEventStore()
        store.remember("assistant_reply", '{"type":"assistant_reply","n":1}')
        store.remember("state_update", '{"type":"state_update","n":2}')
        store.remember("error", '{"type":"error","n":3}')
        store.remember("transcript", '{"type":"transcript","n":4}')

        snapshot = store.snapshot()
        decoded_types = [json.loads(item)["type"] for item in snapshot]
        self.assertEqual(
            ["transcript", "assistant_reply", "error", "state_update"],
            decoded_types,
        )

    def test_sticky_store_overwrites_latest_event_by_type(self) -> None:
        store = StickyEventStore()
        store.remember("timer", '{"type":"timer","remaining":10}')
        store.remember("timer", '{"type":"timer","remaining":9}')
        snapshot = store.snapshot()

        self.assertEqual(1, len(snapshot))
        self.assertEqual(9, json.loads(snapshot[0])["remaining"])


if __name__ == "__main__":
    unittest.main()
