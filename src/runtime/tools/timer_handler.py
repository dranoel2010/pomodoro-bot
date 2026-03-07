"""Domain handler for timer tool commands."""

from __future__ import annotations

from llm.types import JSONObject
from shared.defaults import DEFAULT_TIMER_DURATION_SECONDS, DEFAULT_TIMER_SESSION_NAME
from pomodoro import PomodoroTimer
from pomodoro.constants import ACTION_START, REASON_POMODORO_ACTIVE
from contracts.tool_contract import TIMER_TOOL_TO_RUNTIME_ACTION

from .calendar import parse_duration_seconds
from .messages import ACTIVE_SESSION_PHASES, default_timer_text, timer_rejection_text
from .projector import RuntimeToolProjector


class TimerToolHandler:
    """Executes timer tool commands and projects resulting UI updates."""

    def __init__(
        self,
        *,
        pomodoro_timer: PomodoroTimer,
        countdown_timer: PomodoroTimer,
        projector: RuntimeToolProjector,
    ) -> None:
        self._pomodoro_timer = pomodoro_timer
        self._countdown_timer = countdown_timer
        self._projector = projector

    def handle(self, tool_name: str, arguments: JSONObject, assistant_text: str) -> str:
        action = TIMER_TOOL_TO_RUNTIME_ACTION[tool_name]
        pomodoro_snapshot = self._pomodoro_timer.snapshot()
        if pomodoro_snapshot.phase in ACTIVE_SESSION_PHASES:
            response_text = timer_rejection_text(action, REASON_POMODORO_ACTIVE)
            self._projector.publish_timer(
                self._countdown_timer.snapshot(),
                action=action,
                accepted=False,
                reason=REASON_POMODORO_ACTIVE,
                tool_name=tool_name,
                message=response_text,
            )
            return response_text

        if action == ACTION_START:
            duration_seconds = parse_duration_seconds(
                arguments.get("duration"),
                default_seconds=DEFAULT_TIMER_DURATION_SECONDS,
            )
            result = self._countdown_timer.apply(
                action,
                session=DEFAULT_TIMER_SESSION_NAME,
                duration_seconds=duration_seconds,
            )
        else:
            result = self._countdown_timer.apply(action, session=DEFAULT_TIMER_SESSION_NAME)

        response_text = (
            assistant_text.strip() or default_timer_text(action, result.snapshot)
            if result.accepted
            else timer_rejection_text(action, result.reason)
        )
        self._projector.publish_timer(
            result.snapshot,
            action=action,
            accepted=result.accepted,
            reason=result.reason,
            tool_name=tool_name,
            message=response_text,
        )
        return response_text
