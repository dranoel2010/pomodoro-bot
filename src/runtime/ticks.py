from __future__ import annotations

import logging
from typing import Callable, Optional

from pomodoro import PomodoroTick
from tts import SpeechService, TTSError

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
        completion_message = default_pomodoro_text("completed", tick.snapshot)
        ui.publish_pomodoro_update(
            tick.snapshot,
            action="completed",
            accepted=True,
            reason="completed",
            motivation=completion_message,
        )
        ui.publish_state("replying", message="Pomodoro completed")
        ui.publish("assistant_reply", text=completion_message)
        if speech_service:
            try:
                speech_service.speak(completion_message)
            except TTSError as error:
                logger.error("TTS completion playback failed: %s", error)
        publish_idle_state()
        return

    ui.publish_pomodoro_update(
        tick.snapshot,
        action="tick",
        accepted=True,
        reason="tick",
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
        completion_message = default_timer_text("completed", tick.snapshot)
        ui.publish_timer_update(
            tick.snapshot,
            action="completed",
            accepted=True,
            reason="completed",
            message=completion_message,
        )
        ui.publish_state("replying", message="Timer completed")
        ui.publish("assistant_reply", text=completion_message)
        if speech_service:
            try:
                speech_service.speak(completion_message)
            except TTSError as error:
                logger.error("TTS timer completion playback failed: %s", error)
        publish_idle_state()
        return

    ui.publish_timer_update(
        tick.snapshot,
        action="tick",
        accepted=True,
        reason="tick",
    )
