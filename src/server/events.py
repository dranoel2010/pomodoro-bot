from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from typing import Any, Callable

STICKY_EVENT_TYPES: frozenset[str] = frozenset(
    {
        "state_update",
        "pomodoro",
        "timer",
        "transcript",
        "assistant_reply",
        "error",
    }
)

STICKY_EVENT_ORDER: tuple[str, ...] = (
    "pomodoro",
    "timer",
    "transcript",
    "assistant_reply",
    "error",
    "state_update",
)


def make_event(
    event_type: str,
    *,
    now_fn: Callable[[], datetime] | None = None,
    **payload: Any,
) -> str:
    now = now_fn() if now_fn is not None else datetime.now(timezone.utc)
    return json.dumps(
        {
            "type": event_type,
            "timestamp": now.isoformat(),
            **payload,
        }
    )


class StickyEventStore:
    def __init__(self):
        self._events: dict[str, str] = {}
        self._lock = threading.Lock()

    def remember(self, event_type: str, message: str) -> None:
        if event_type not in STICKY_EVENT_TYPES:
            return
        with self._lock:
            self._events[event_type] = message

    def snapshot(self) -> list[str]:
        with self._lock:
            return [self._events[key] for key in STICKY_EVENT_ORDER if key in self._events]
