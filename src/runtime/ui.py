from __future__ import annotations

from typing import Any, Optional, Protocol

from pomodoro import PomodoroSnapshot


class UIServerLike(Protocol):
    def publish(self, event_type: str, **payload: Any) -> None:
        ...

    def publish_state(
        self,
        state: str,
        *,
        message: Optional[str] = None,
        **payload: Any,
    ) -> None:
        ...


class RuntimeUIPublisher:
    def __init__(self, ui_server: Optional[UIServerLike]):
        self._ui_server = ui_server

    def publish(self, event_type: str, **payload: Any) -> None:
        if self._ui_server:
            self._ui_server.publish(event_type, **payload)

    def publish_state(
        self,
        state: str,
        *,
        message: Optional[str] = None,
        **payload: Any,
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
        payload: dict[str, Any] = {
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
        self.publish("pomodoro", **payload)

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
        payload: dict[str, Any] = {
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
        self.publish("timer", **payload)
