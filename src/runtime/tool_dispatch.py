from __future__ import annotations

import logging
from typing import Any, Optional

from pomodoro import PomodoroSnapshot, PomodoroTimer, remap_timer_tool_for_active_pomodoro
from tool_contract import (
    CALENDAR_TOOL_NAMES,
    POMODORO_TOOL_TO_RUNTIME_ACTION,
    TIMER_TOOL_TO_RUNTIME_ACTION,
)

from .calendar_tools import handle_calendar_tool_call, parse_duration_seconds
from .contracts import AppConfigLike, CalendarOracleLike
from .messages import (
    ACTIVE_SESSION_PHASES,
    default_pomodoro_text,
    default_timer_text,
    pomodoro_rejection_text,
    pomodoro_status_message,
    timer_rejection_text,
    timer_status_message,
)
from .ui import RuntimeUIPublisher


class RuntimeToolDispatcher:
    def __init__(
        self,
        *,
        logger: logging.Logger,
        app_config: AppConfigLike,
        oracle_service: Optional[CalendarOracleLike],
        pomodoro_timer: PomodoroTimer,
        countdown_timer: PomodoroTimer,
        ui: RuntimeUIPublisher,
    ):
        self._logger = logger
        self._app_config = app_config
        self._oracle_service = oracle_service
        self._pomodoro_timer = pomodoro_timer
        self._countdown_timer = countdown_timer
        self._ui = ui

    def active_runtime_message(self) -> str:
        pomodoro_snapshot = self._pomodoro_timer.snapshot()
        if pomodoro_snapshot.phase in ACTIVE_SESSION_PHASES:
            return pomodoro_status_message(pomodoro_snapshot)
        timer_snapshot = self._countdown_timer.snapshot()
        if timer_snapshot.phase in ACTIVE_SESSION_PHASES:
            return timer_status_message(timer_snapshot)
        return "Listening for wake word"

    def handle_tool_call(self, tool_call: dict[str, Any], assistant_text: str) -> str:
        raw_name = tool_call.get("name")
        if not isinstance(raw_name, str):
            return assistant_text
        raw_arguments = tool_call.get("arguments")
        arguments = raw_arguments if isinstance(raw_arguments, dict) else {}

        pomodoro_snapshot = self._pomodoro_timer.snapshot()
        if self._is_session_active(pomodoro_snapshot):
            raw_name = remap_timer_tool_for_active_pomodoro(
                raw_name,
                pomodoro_active=True,
            )

        if raw_name in POMODORO_TOOL_TO_RUNTIME_ACTION:
            return self._handle_pomodoro_tool_call(raw_name, arguments, assistant_text)
        if raw_name in TIMER_TOOL_TO_RUNTIME_ACTION:
            return self._handle_timer_tool_call(raw_name, arguments, assistant_text)
        if raw_name in CALENDAR_TOOL_NAMES:
            return handle_calendar_tool_call(
                tool_name=raw_name,
                arguments=arguments,
                oracle_service=self._oracle_service,
                app_config=self._app_config,
                logger=self._logger,
            )

        self._logger.warning("Unsupported tool call: %s", raw_name)
        return assistant_text

    def _handle_pomodoro_tool_call(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        assistant_text: str,
    ) -> str:
        action = POMODORO_TOOL_TO_RUNTIME_ACTION[tool_name]
        timer_snapshot = self._countdown_timer.snapshot()
        if self._is_session_active(timer_snapshot):
            if action in {"start", "reset"}:
                self._stop_timer_for_pomodoro_switch()
            else:
                response_text = pomodoro_rejection_text(action, "timer_active")
                self._ui.publish_pomodoro_update(
                    self._pomodoro_timer.snapshot(),
                    action=action,
                    accepted=False,
                    reason="timer_active",
                    tool_name=tool_name,
                    motivation=response_text,
                )
                return response_text

        focus_topic_raw = arguments.get("focus_topic")
        focus_topic = (
            str(focus_topic_raw).strip()
            if isinstance(focus_topic_raw, str) and focus_topic_raw.strip()
            else None
        )
        result = self._pomodoro_timer.apply(action, session=focus_topic)
        if result.accepted:
            response_text = assistant_text.strip() or default_pomodoro_text(
                action,
                result.snapshot,
            )
        else:
            response_text = pomodoro_rejection_text(action, result.reason)
        self._ui.publish_pomodoro_update(
            result.snapshot,
            action=action,
            accepted=result.accepted,
            reason=result.reason,
            tool_name=tool_name,
            motivation=response_text,
        )
        return response_text

    def _handle_timer_tool_call(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        assistant_text: str,
    ) -> str:
        action = TIMER_TOOL_TO_RUNTIME_ACTION[tool_name]
        pomodoro_snapshot = self._pomodoro_timer.snapshot()
        if self._is_session_active(pomodoro_snapshot):
            response_text = timer_rejection_text(action, "pomodoro_active")
            self._ui.publish_timer_update(
                self._countdown_timer.snapshot(),
                action=action,
                accepted=False,
                reason="pomodoro_active",
                tool_name=tool_name,
                message=response_text,
            )
            return response_text

        if action == "start":
            duration_seconds = parse_duration_seconds(
                arguments.get("duration"),
                default_seconds=10 * 60,
            )
            result = self._countdown_timer.apply(
                action,
                session="Timer",
                duration_seconds=duration_seconds,
            )
        else:
            result = self._countdown_timer.apply(action, session="Timer")

        if result.accepted:
            response_text = assistant_text.strip() or default_timer_text(
                action,
                result.snapshot,
            )
        else:
            response_text = timer_rejection_text(action, result.reason)
        self._ui.publish_timer_update(
            result.snapshot,
            action=action,
            accepted=result.accepted,
            reason=result.reason,
            tool_name=tool_name,
            message=response_text,
        )
        return response_text

    def _is_session_active(self, snapshot: PomodoroSnapshot) -> bool:
        return snapshot.phase in ACTIVE_SESSION_PHASES

    def _stop_timer_for_pomodoro_switch(self) -> None:
        timer_snapshot = self._countdown_timer.snapshot()
        if not self._is_session_active(timer_snapshot):
            return

        result = self._countdown_timer.apply("abort", session="Timer")
        self._ui.publish_timer_update(
            result.snapshot,
            action="abort",
            accepted=result.accepted,
            reason="superseded_by_pomodoro",
            message="Timer beendet, Pomodoro startet jetzt.",
        )
