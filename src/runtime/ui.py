"""UI publishing adapter used by runtime components."""

from __future__ import annotations

from typing import Optional, Protocol

from pomodoro import PomodoroSnapshot
from contracts.ui_protocol import EVENT_POMODORO, EVENT_TIMER


class UISink(Protocol):
    def publish(self, event_type: str, **payload: object) -> None:
        ...

    def publish_state(
        self,
        state: str,
        *,
        message: Optional[str] = None,
        **payload: object,
    ) -> None:
        ...


class RuntimeUIPublisher:
    """Safe facade that emits runtime updates when a UI server is available."""

    def __init__(self, ui_server: Optional[UISink]):
        self._ui_server = ui_server

    def publish(self, event_type: str, **payload: object) -> None:
        if self._ui_server:
            self._ui_server.publish(event_type, **payload)

    def publish_state(
        self,
        state: str,
        *,
        message: Optional[str] = None,
        **payload: object,
    ) -> None:
        if self._ui_server:
            self._ui_server.publish_state(state, message=message, **payload)

    def publish_pomodoro_update(
        self,
        snapshot: PomodoroSnapshot,
        *,
        action: str,
        accepted: Optional[bool] = None,
        reason: str = "",
        tool_name: Optional[str] = None,
        motivation: Optional[str] = None,
    ) -> None:
        payload: dict[str, object] = {
            "action": action,
            "phase": snapshot.phase,
            "session": snapshot.session,
            "duration_seconds": snapshot.duration_seconds,
            "remaining_seconds": snapshot.remaining_seconds,
        }
        if accepted is not None:
            payload["accepted"] = accepted
        if reason:
            payload["reason"] = reason
        if tool_name:
            payload["tool_name"] = tool_name
        if motivation:
            payload["motivation"] = motivation
        self.publish(EVENT_POMODORO, **payload)

    def publish_timer_update(
        self,
        snapshot: PomodoroSnapshot,
        *,
        action: str,
        accepted: Optional[bool] = None,
        reason: str = "",
        tool_name: Optional[str] = None,
        message: Optional[str] = None,
    ) -> None:
        payload: dict[str, object] = {
            "action": action,
            "phase": snapshot.phase,
            "duration_seconds": snapshot.duration_seconds,
            "remaining_seconds": snapshot.remaining_seconds,
        }
        if accepted is not None:
            payload["accepted"] = accepted
        if reason:
            payload["reason"] = reason
        if tool_name:
            payload["tool_name"] = tool_name
        if message:
            payload["message"] = message
        self.publish(EVENT_TIMER, **payload)
