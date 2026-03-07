"""Tick handlers that publish timer completion updates and optional TTS output."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Callable

from pomodoro import PomodoroTick, PomodoroCycleState
from pomodoro.constants import (
    ACTION_COMPLETED,
    ACTION_TICK,
    PHASE_TYPE_LONG_BREAK,
    PHASE_TYPE_SHORT_BREAK,
    PHASE_TYPE_WORK,
    REASON_COMPLETED,
    REASON_TICK,
)
from contracts.pipeline import TTSClient
from contracts.ui_protocol import (
    EVENT_ASSISTANT_REPLY,
    STATE_POMODORO_IDLE,
    STATE_POMODORO_LONG_BREAK,
    STATE_POMODORO_SHORT_BREAK,
    STATE_POMODORO_WORK,
    STATE_REPLYING,
)
from tts.engine import TTSError
from .tools.messages import (
    default_pomodoro_text,
    default_timer_text,
    pomodoro_break_to_work_text,
    pomodoro_long_break_to_work_text,
    pomodoro_work_to_break_text,
    pomodoro_work_to_long_break_text,
)
from .ui import RuntimeUIPublisher

if TYPE_CHECKING:
    from pomodoro import PomodoroTimer

_PHASE_TYPE_TO_POMODORO_STATE: dict[str, str] = {
    PHASE_TYPE_WORK: STATE_POMODORO_WORK,
    PHASE_TYPE_SHORT_BREAK: STATE_POMODORO_SHORT_BREAK,
    PHASE_TYPE_LONG_BREAK: STATE_POMODORO_LONG_BREAK,
}


def handle_pomodoro_tick(
    tick: PomodoroTick,
    *,
    speech_service: TTSClient | None,
    logger: logging.Logger,
    ui: RuntimeUIPublisher,
    publish_idle_state: Callable[[], None],
    pomodoro_timer: PomodoroTimer | None = None,
    cycle: PomodoroCycleState | None = None,
) -> None:
    if tick.completed:
        if cycle is not None and cycle.active and pomodoro_timer is not None:
            # Autonomous transition: advance cycle and restart timer
            transition = cycle.advance(pomodoro_timer)
            if transition.new_phase_type == PHASE_TYPE_SHORT_BREAK:
                announcement = pomodoro_work_to_break_text(
                    transition.session_count, transition.duration_seconds
                )
            elif transition.new_phase_type == PHASE_TYPE_LONG_BREAK:
                announcement = pomodoro_work_to_long_break_text(
                    transition.session_count, transition.duration_seconds
                )
            elif transition.previous_phase_type == PHASE_TYPE_SHORT_BREAK:
                announcement = pomodoro_break_to_work_text()
            else:  # PHASE_TYPE_LONG_BREAK → PHASE_TYPE_WORK
                announcement = pomodoro_long_break_to_work_text()
            cycle_phase = _PHASE_TYPE_TO_POMODORO_STATE.get(transition.new_phase_type, STATE_POMODORO_IDLE)
            new_snapshot = pomodoro_timer.snapshot()
            ui.publish_pomodoro_update(
                new_snapshot,
                action=ACTION_COMPLETED,
                accepted=True,
                reason=REASON_COMPLETED,
                motivation=announcement,
                cycle_phase=cycle_phase,
                session_count=transition.session_count,
            )
            ui.publish_state(STATE_REPLYING, message=announcement)
            ui.publish(EVENT_ASSISTANT_REPLY, text=announcement)
            if speech_service is not None:
                try:
                    speech_service.speak(announcement)
                except TTSError as error:
                    logger.error("TTS phase transition announcement failed: %s", error)
            # Publish cycle-aware idle state — the timer is already running for the
            # new phase, so active_runtime_message() returns the new pomodoro status
            # (e.g. "Pomodoro 'Fokus' laeuft (25:00 verbleibend)"), not "idle".
            publish_idle_state()
            return

        # Original completion behavior (manual mode or cycle inactive)
        completion_message = default_pomodoro_text(ACTION_COMPLETED, tick.snapshot)
        ui.publish_pomodoro_update(
            tick.snapshot,
            action=ACTION_COMPLETED,
            accepted=True,
            reason=REASON_COMPLETED,
            motivation=completion_message,
        )
        ui.publish_state(STATE_REPLYING, message="Pomodoro completed")
        ui.publish(EVENT_ASSISTANT_REPLY, text=completion_message)
        if speech_service is not None:
            try:
                speech_service.speak(completion_message)
            except TTSError as error:
                logger.error("TTS completion playback failed: %s", error)
        publish_idle_state()
        return

    tick_cycle_phase: str | None = None
    tick_session_count: int | None = None
    if cycle is not None and cycle.active:
        tick_cycle_phase = _PHASE_TYPE_TO_POMODORO_STATE.get(cycle.phase_type, STATE_POMODORO_IDLE)
        tick_session_count = cycle.session_count
    ui.publish_pomodoro_update(
        tick.snapshot,
        action=ACTION_TICK,
        accepted=True,
        reason=REASON_TICK,
        cycle_phase=tick_cycle_phase,
        session_count=tick_session_count,
    )


def handle_timer_tick(
    tick: PomodoroTick,
    *,
    speech_service: TTSClient | None,
    logger: logging.Logger,
    ui: RuntimeUIPublisher,
    publish_idle_state: Callable[[], None],
) -> None:
    if tick.completed:
        completion_message = default_timer_text(ACTION_COMPLETED, tick.snapshot)
        ui.publish_timer_update(
            tick.snapshot,
            action=ACTION_COMPLETED,
            accepted=True,
            reason=REASON_COMPLETED,
            message=completion_message,
        )
        ui.publish_state(STATE_REPLYING, message="Timer completed")
        ui.publish(EVENT_ASSISTANT_REPLY, text=completion_message)
        if speech_service is not None:
            try:
                speech_service.speak(completion_message)
            except TTSError as error:
                logger.error("TTS timer completion playback failed: %s", error)
        publish_idle_state()
        return

    ui.publish_timer_update(
        tick.snapshot,
        action=ACTION_TICK,
        accepted=True,
        reason=REASON_TICK,
    )
