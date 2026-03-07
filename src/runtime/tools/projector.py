"""UI projection helpers for runtime tool outcomes."""

from __future__ import annotations

from pomodoro import PomodoroSnapshot

from ..ui import RuntimeUIPublisher


class RuntimeToolProjector:
    """Publishes timer and pomodoro tool outcomes to the UI layer."""

    def __init__(self, ui: RuntimeUIPublisher):
        self._ui = ui

    def publish_pomodoro(
        self,
        snapshot: PomodoroSnapshot,
        *,
        action: str,
        accepted: bool | None = None,
        reason: str = "",
        tool_name: str | None = None,
        motivation: str | None = None,
        cycle_phase: str | None = None,
        session_count: int | None = None,
    ) -> None:
        self._ui.publish_pomodoro_update(
            snapshot,
            action=action,
            accepted=accepted,
            reason=reason,
            tool_name=tool_name,
            motivation=motivation,
            cycle_phase=cycle_phase,
            session_count=session_count,
        )

    def publish_timer(
        self,
        snapshot: PomodoroSnapshot,
        *,
        action: str,
        accepted: bool | None = None,
        reason: str = "",
        tool_name: str | None = None,
        message: str | None = None,
    ) -> None:
        self._ui.publish_timer_update(
            snapshot,
            action=action,
            accepted=accepted,
            reason=reason,
            tool_name=tool_name,
            message=message,
        )
