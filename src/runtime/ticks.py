"""Tick handlers that publish timer completion updates and optional TTS output."""

from __future__ import annotations

import logging
from typing import Callable, Optional

from pomodoro import PomodoroTick
from pomodoro.constants import (
    ACTION_COMPLETED,
    ACTION_TICK,
    REASON_COMPLETED,
    REASON_TICK,
)
from tts import SpeechService, TTSError
from contracts.ui_protocol import EVENT_ASSISTANT_REPLY, STATE_REPLYING

from .messages import default_pomodoro_text, default_timer_text
from .ui import RuntimeUIPublisher


def handle_pomodoro_tick(
    tick: PomodoroTick,
    *,
    speech_service: Optional[SpeechService],
    logger: logging.Logger,
    ui: RuntimeUIPublisher,
    publish_idle_state: Callable[[], None],
) -> None:
    if tick.completed:
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

    ui.publish_pomodoro_update(
        tick.snapshot,
        action=ACTION_TICK,
        accepted=True,
        reason=REASON_TICK,
    )


def handle_timer_tick(
    tick: PomodoroTick,
    *,
    speech_service: Optional[SpeechService],
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
