"""Tick handlers that publish timer completion updates and optional TTS output."""

from __future__ import annotations

import logging
from dataclasses import dataclass
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


@dataclass(frozen=True)
class TickDependencies:
    """Dependencies required for processing pomodoro and timer tick events."""
    speech_service: Optional[SpeechService]
    logger: logging.Logger
    ui: RuntimeUIPublisher
    publish_idle_state: Callable[[], None]


class TickProcessor:
    """Handles tick side effects such as UI updates and completion speech."""
    def __init__(self, dependencies: TickDependencies):
        self._dependencies = dependencies

    def handle_pomodoro_tick(self, tick: PomodoroTick) -> None:
        deps = self._dependencies
        if tick.completed:
            completion_message = default_pomodoro_text(ACTION_COMPLETED, tick.snapshot)
            deps.ui.publish_pomodoro_update(
                tick.snapshot,
                action=ACTION_COMPLETED,
                accepted=True,
                reason=REASON_COMPLETED,
                motivation=completion_message,
            )
            deps.ui.publish_state(STATE_REPLYING, message="Pomodoro completed")
            deps.ui.publish(EVENT_ASSISTANT_REPLY, text=completion_message)
            if deps.speech_service:
                try:
                    deps.speech_service.speak(completion_message)
                except TTSError as error:
                    deps.logger.error("TTS completion playback failed: %s", error)
            deps.publish_idle_state()
            return

        deps.ui.publish_pomodoro_update(
            tick.snapshot,
            action=ACTION_TICK,
            accepted=True,
            reason=REASON_TICK,
        )

    def handle_timer_tick(self, tick: PomodoroTick) -> None:
        deps = self._dependencies
        if tick.completed:
            completion_message = default_timer_text(ACTION_COMPLETED, tick.snapshot)
            deps.ui.publish_timer_update(
                tick.snapshot,
                action=ACTION_COMPLETED,
                accepted=True,
                reason=REASON_COMPLETED,
                message=completion_message,
            )
            deps.ui.publish_state(STATE_REPLYING, message="Timer completed")
            deps.ui.publish(EVENT_ASSISTANT_REPLY, text=completion_message)
            if deps.speech_service:
                try:
                    deps.speech_service.speak(completion_message)
                except TTSError as error:
                    deps.logger.error("TTS timer completion playback failed: %s", error)
            deps.publish_idle_state()
            return

        deps.ui.publish_timer_update(
            tick.snapshot,
            action=ACTION_TICK,
            accepted=True,
            reason=REASON_TICK,
        )
