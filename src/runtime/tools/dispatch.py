"""Dispatcher that executes normalized tool calls against runtime services."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from llm.types import JSONObject, ToolCall
from shared.defaults import DEFAULT_FOCUS_TOPIC_DE, DEFAULT_TIMER_DURATION_SECONDS, DEFAULT_TIMER_SESSION_NAME
from pomodoro import PomodoroCycleState, PomodoroTimer, remap_timer_tool_for_active_pomodoro
from pomodoro.constants import (
    ACTION_ABORT,
    ACTION_RESET,
    ACTION_START,
    PHASE_TYPE_LONG_BREAK,
    PHASE_TYPE_SHORT_BREAK,
    PHASE_TYPE_WORK,
    REASON_POMODORO_ACTIVE,
    REASON_SUPERSEDED_BY_POMODORO,
    REASON_TIMER_ACTIVE,
)
from contracts.ui_protocol import (
    STATE_POMODORO_IDLE,
    STATE_POMODORO_LONG_BREAK,
    STATE_POMODORO_SHORT_BREAK,
    STATE_POMODORO_WORK,
)
import contracts.tool_contract as _tc
from contracts.tool_contract import (
    POMODORO_TOOL_TO_RUNTIME_ACTION,
    TIMER_TOOL_TO_RUNTIME_ACTION,
)

from .calendar import handle_calendar_tool_call, parse_duration_seconds
from .messages import (
    ACTIVE_SESSION_PHASES,
    default_pomodoro_text,
    default_timer_text,
    pomodoro_rejection_text,
    pomodoro_status_message,
    timer_rejection_text,
    timer_status_message,
)
from ..ui import RuntimeUIPublisher

if TYPE_CHECKING:
    from config import AppConfig
    from oracle.service import OracleContextService


def _handle_tell_joke(assistant_text: str) -> str:
    del assistant_text  # joke is hardcoded; LLM text is irrelevant
    return (
        "Warum können Geister so schlecht lügen? "
        "Weil man durch sie hindurchsehen kann."
    )


_PHASE_TYPE_TO_POMODORO_STATE: dict[str, str] = {
    PHASE_TYPE_WORK: STATE_POMODORO_WORK,
    PHASE_TYPE_SHORT_BREAK: STATE_POMODORO_SHORT_BREAK,
    PHASE_TYPE_LONG_BREAK: STATE_POMODORO_LONG_BREAK,
}


class RuntimeToolDispatcher:
    """Routes tool calls to timer, pomodoro, and calendar handlers."""
    def __init__(
        self,
        *,
        logger: logging.Logger,
        app_config: "AppConfig",
        oracle_service: "OracleContextService" | None,
        pomodoro_timer: PomodoroTimer,
        countdown_timer: PomodoroTimer,
        ui: RuntimeUIPublisher,
        pomodoro_cycle: PomodoroCycleState | None = None,
    ):
        self._logger = logger
        self._app_config = app_config
        self._oracle_service = oracle_service
        self._pomodoro_timer = pomodoro_timer
        self._countdown_timer = countdown_timer
        self._ui = ui
        self._pomodoro_cycle = pomodoro_cycle

    def active_runtime_message(self) -> str:
        pomodoro_snapshot = self._pomodoro_timer.snapshot()
        if pomodoro_snapshot.phase in ACTIVE_SESSION_PHASES:
            return pomodoro_status_message(pomodoro_snapshot)
        timer_snapshot = self._countdown_timer.snapshot()
        if timer_snapshot.phase in ACTIVE_SESSION_PHASES:
            return timer_status_message(timer_snapshot)
        return "Listening for wake word"

    def handle_tool_call(self, tool_call: ToolCall, assistant_text: str) -> str:
        raw_name = tool_call["name"]
        normalized_arguments: JSONObject = tool_call.get("arguments", {})

        pomodoro_snapshot = self._pomodoro_timer.snapshot()
        if pomodoro_snapshot.phase in ACTIVE_SESSION_PHASES:
            raw_name = remap_timer_tool_for_active_pomodoro(
                raw_name,
                pomodoro_active=True,
            )

        match raw_name:
            case _tc.TOOL_STATUS_POMODORO:
                return self._handle_pomodoro_status_query(assistant_text)
            case (
                _tc.TOOL_START_POMODORO
                | _tc.TOOL_STOP_POMODORO
                | _tc.TOOL_PAUSE_POMODORO
                | _tc.TOOL_CONTINUE_POMODORO
                | _tc.TOOL_RESET_POMODORO
            ):
                return self._handle_pomodoro_tool_call(raw_name, normalized_arguments, assistant_text)
            case (
                _tc.TOOL_START_TIMER
                | _tc.TOOL_STOP_TIMER
                | _tc.TOOL_PAUSE_TIMER
                | _tc.TOOL_CONTINUE_TIMER
                | _tc.TOOL_RESET_TIMER
            ):
                return self._handle_timer_tool_call(raw_name, normalized_arguments, assistant_text)
            case _tc.TOOL_SHOW_UPCOMING_EVENTS | _tc.TOOL_ADD_CALENDAR_EVENT:
                return handle_calendar_tool_call(
                    tool_name=raw_name,
                    arguments=normalized_arguments,
                    oracle_service=self._oracle_service,
                    app_config=self._app_config,
                    logger=self._logger,
                )
            case _tc.TOOL_TELL_JOKE:
                return _handle_tell_joke(assistant_text)
            case _:
                self._logger.warning("Unsupported tool call: %s", raw_name)
                return assistant_text

    def _handle_pomodoro_status_query(self, assistant_text: str) -> str:
        del assistant_text  # status is always live data; LLM text cannot know remaining time
        return pomodoro_status_message(self._pomodoro_timer.snapshot())

    def _handle_pomodoro_tool_call(
        self,
        tool_name: str,
        arguments: JSONObject,
        assistant_text: str,
    ) -> str:
        action = POMODORO_TOOL_TO_RUNTIME_ACTION[tool_name]
        timer_snapshot = self._countdown_timer.snapshot()
        if timer_snapshot.phase in ACTIVE_SESSION_PHASES:
            if action in {ACTION_START, ACTION_RESET}:
                self._stop_timer_for_pomodoro_switch()
            else:
                response_text = pomodoro_rejection_text(action, REASON_TIMER_ACTIVE)
                self._ui.publish_pomodoro_update(
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
                dispatch_cycle_phase = _PHASE_TYPE_TO_POMODORO_STATE.get(
                    self._pomodoro_cycle.phase_type, STATE_POMODORO_IDLE
                )
                dispatch_session_count = self._pomodoro_cycle.session_count
            else:
                dispatch_cycle_phase = STATE_POMODORO_IDLE
                dispatch_session_count = 0
        self._ui.publish_pomodoro_update(
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

    def _handle_timer_tool_call(
        self,
        tool_name: str,
        arguments: JSONObject,
        assistant_text: str,
    ) -> str:
        action = TIMER_TOOL_TO_RUNTIME_ACTION[tool_name]
        pomodoro_snapshot = self._pomodoro_timer.snapshot()
        if pomodoro_snapshot.phase in ACTIVE_SESSION_PHASES:
            response_text = timer_rejection_text(action, REASON_POMODORO_ACTIVE)
            self._ui.publish_timer_update(
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
        self._ui.publish_timer_update(
            result.snapshot,
            action=action,
            accepted=result.accepted,
            reason=result.reason,
            tool_name=tool_name,
            message=response_text,
        )
        return response_text

    def _stop_timer_for_pomodoro_switch(self) -> None:
        timer_snapshot = self._countdown_timer.snapshot()
        if timer_snapshot.phase not in ACTIVE_SESSION_PHASES:
            return

        result = self._countdown_timer.apply(ACTION_ABORT, session=DEFAULT_TIMER_SESSION_NAME)
        self._ui.publish_timer_update(
            result.snapshot,
            action=ACTION_ABORT,
            accepted=result.accepted,
            reason=REASON_SUPERSEDED_BY_POMODORO,
            message="Timer beendet, Pomodoro startet jetzt.",
        )
