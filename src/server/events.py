"""Utilities for serializing UI events and preserving sticky state."""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from typing import Any, Callable

from contracts.ui_protocol import STICKY_EVENT_ORDER, STICKY_EVENT_TYPES


def make_event(
    event_type: str,
    *,
    now_fn: Callable[[], datetime] | None = None,
    **payload: Any,
) -> str:
    """Serialize an event payload with type and timestamp for websocket delivery."""
    now = now_fn() if now_fn is not None else datetime.now(timezone.utc)
    return json.dumps(
        {
            "type": event_type,
            "timestamp": now.isoformat(),
            **payload,
        }
    )


class StickyEventStore:
    """Thread-safe cache of sticky events replayed to new websocket clients."""
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
