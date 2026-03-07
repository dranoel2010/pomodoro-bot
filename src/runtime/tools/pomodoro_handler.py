"""Domain handler for pomodoro tool commands."""

from __future__ import annotations

import logging

from llm.types import JSONObject
from shared.defaults import DEFAULT_FOCUS_TOPIC_DE, DEFAULT_TIMER_SESSION_NAME
from pomodoro import PomodoroCycleState, PomodoroTimer
from pomodoro.constants import (
    ACTION_ABORT,
    ACTION_RESET,
    ACTION_START,
    REASON_POMODORO_ACTIVE,
    REASON_SUPERSEDED_BY_POMODORO,
    REASON_TIMER_ACTIVE,
)
from contracts.tool_contract import POMODORO_TOOL_TO_RUNTIME_ACTION

from .messages import (
    ACTIVE_SESSION_PHASES,
    default_pomodoro_text,
    pomodoro_rejection_text,
    pomodoro_status_message,
)
from .projector import RuntimeToolProjector


class PomodoroToolHandler:
    """Executes pomodoro tool commands and projects resulting UI updates."""

    def __init__(
        self,
        *,
        logger: logging.Logger,
        pomodoro_timer: PomodoroTimer,
        countdown_timer: PomodoroTimer,
        projector: RuntimeToolProjector,
        phase_state_map: dict[str, str],
        idle_cycle_state: str,
        pomodoro_cycle: PomodoroCycleState | None = None,
    ) -> None:
        self._logger = logger
        self._pomodoro_timer = pomodoro_timer
        self._countdown_timer = countdown_timer
        self._projector = projector
        self._phase_state_map = phase_state_map
        self._idle_cycle_state = idle_cycle_state
        self._pomodoro_cycle = pomodoro_cycle

    def status_message(self) -> str:
        return pomodoro_status_message(self._pomodoro_timer.snapshot())

    def handle(self, tool_name: str, arguments: JSONObject, assistant_text: str) -> str:
        action = POMODORO_TOOL_TO_RUNTIME_ACTION[tool_name]
        timer_snapshot = self._countdown_timer.snapshot()
        if timer_snapshot.phase in ACTIVE_SESSION_PHASES:
            if action in {ACTION_START, ACTION_RESET}:
                self._stop_timer_for_pomodoro_switch()
            else:
                response_text = pomodoro_rejection_text(action, REASON_TIMER_ACTIVE)
                self._projector.publish_pomodoro(
                    self._pomodoro_timer.snapshot(),
                    action=action,
                    accepted=False,
                    reason=REASON_TIMER_ACTIVE,
                    tool_name=tool_name,
                    motivation=response_text,
                )
                return response_text

        focus_topic = arguments.get("focus_topic")
        focus_topic = focus_topic.strip() if isinstance(focus_topic, str) else None
        focus_topic = focus_topic or None
        result = self._pomodoro_timer.apply(action, session=focus_topic)
        response_text = (
            assistant_text.strip() or default_pomodoro_text(action, result.snapshot)
            if result.accepted
            else pomodoro_rejection_text(action, result.reason)
        )
        dispatch_cycle_phase: str | None = None
        dispatch_session_count: int | None = None
        if self._pomodoro_cycle is not None and result.accepted:
            if action == ACTION_START:
                self._pomodoro_cycle.begin_cycle(
                    session_name=result.snapshot.session or DEFAULT_FOCUS_TOPIC_DE
                )
            elif action == ACTION_ABORT:
                self._pomodoro_cycle.reset()
            elif action == ACTION_RESET:
                self._pomodoro_cycle.begin_cycle(
                    session_name=result.snapshot.session or DEFAULT_FOCUS_TOPIC_DE
                )
            if self._pomodoro_cycle.active:
                dispatch_cycle_phase = self._phase_state_map.get(
                    self._pomodoro_cycle.phase_type,
                    self._idle_cycle_state,
                )
                dispatch_session_count = self._pomodoro_cycle.session_count
            else:
                dispatch_cycle_phase = self._idle_cycle_state
                dispatch_session_count = 0
        self._projector.publish_pomodoro(
            result.snapshot,
            action=action,
            accepted=result.accepted,
            reason=result.reason,
            tool_name=tool_name,
            motivation=response_text,
            cycle_phase=dispatch_cycle_phase,
            session_count=dispatch_session_count,
        )
        return response_text

    def _stop_timer_for_pomodoro_switch(self) -> None:
        timer_snapshot = self._countdown_timer.snapshot()
        if timer_snapshot.phase not in ACTIVE_SESSION_PHASES:
            return

        result = self._countdown_timer.apply(ACTION_ABORT, session=DEFAULT_TIMER_SESSION_NAME)
        self._projector.publish_timer(
            result.snapshot,
            action=ACTION_ABORT,
            accepted=result.accepted,
            reason=REASON_SUPERSEDED_BY_POMODORO,
            message="Timer beendet, Pomodoro startet jetzt.",
        )
        self._logger.info(
            "Timer aborted due to pomodoro switch (%s).",
            REASON_POMODORO_ACTIVE,
        )
