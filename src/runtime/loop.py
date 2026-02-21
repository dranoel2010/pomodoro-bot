from __future__ import annotations

import concurrent.futures
import datetime as dt
import logging
from queue import Empty, Queue
from typing import Callable, Optional

from app_config import AppConfig
from llm import EnvironmentContext, PomodoroAssistantLLM
from oracle import OracleContextService
from pomodoro import PomodoroTimer
from server import UIServer
from stt import (
    FasterWhisperSTT,
    QueueEventPublisher,
    UtteranceCapturedEvent,
    WakeWordConfig,
    WakeWordDetectedEvent,
    WakeWordErrorEvent,
    WakeWordService,
)
from tts import SpeechService

from .ticks import handle_pomodoro_tick, handle_timer_tick
from .tool_dispatch import RuntimeToolDispatcher
from .ui import RuntimeUIPublisher
from .utterance import process_utterance


def run_runtime_loop(
    *,
    logger: logging.Logger,
    app_config: AppConfig,
    wake_word_config: WakeWordConfig,
    stt: FasterWhisperSTT,
    assistant_llm: Optional[PomodoroAssistantLLM],
    speech_service: Optional[SpeechService],
    oracle_service: Optional[OracleContextService],
    ui_server: Optional[UIServer],
    setup_signal_handlers_fn: Callable[[WakeWordService], None],
    wait_for_service_ready_fn: Callable[[WakeWordService, float], bool],
) -> int:
    def build_llm_environment_context() -> EnvironmentContext:
        payload = {
            "now_local": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
            "light_level_lux": None,
            "air_quality": None,
            "upcoming_events": None,
        }
        if oracle_service is not None:
            try:
                payload.update(oracle_service.build_environment_payload())
            except Exception as error:
                logger.warning("Failed to collect oracle context: %s", error)

        return EnvironmentContext(
            now_local=payload["now_local"],
            light_level_lux=payload.get("light_level_lux"),
            air_quality=payload.get("air_quality"),
            upcoming_events=payload.get("upcoming_events"),
        )

    ui = RuntimeUIPublisher(ui_server)
    pomodoro_timer = PomodoroTimer(logger=logging.getLogger("pomodoro"))
    countdown_timer = PomodoroTimer(
        duration_seconds=10 * 60,
        logger=logging.getLogger("timer"),
    )
    dispatcher = RuntimeToolDispatcher(
        logger=logger,
        app_config=app_config,
        oracle_service=oracle_service,
        pomodoro_timer=pomodoro_timer,
        countdown_timer=countdown_timer,
        ui=ui,
    )

    def publish_idle_state() -> None:
        ui.publish_state("idle", message=dispatcher.active_runtime_message())

    ui.publish_pomodoro_update(
        pomodoro_timer.snapshot(),
        action="sync",
        accepted=True,
        reason="startup",
    )
    ui.publish_timer_update(
        countdown_timer.snapshot(),
        action="sync",
        accepted=True,
        reason="startup",
    )

    event_queue: Queue = Queue()
    publisher = QueueEventPublisher(event_queue)
    service: Optional[WakeWordService] = None
    wake_word_logger = logging.getLogger("wake_word")
    utterance_executor = concurrent.futures.ThreadPoolExecutor(
        max_workers=1,
        thread_name_prefix="utterance",
    )
    pending_utterance: Optional[concurrent.futures.Future[None]] = None

    try:
        service = WakeWordService(
            config=wake_word_config,
            publisher=publisher,
            logger=wake_word_logger,
        )

        setup_signal_handlers_fn(service)

        logger.info("Starting wake word service...")
        service.start()

        logger.debug("Initializing wake word detection...")
        if not wait_for_service_ready_fn(service, timeout=10.0):
            if not service.is_running:
                logger.error("Service crashed during initialization.")
            else:
                logger.error("Service initialization timed out.")

            return 1

        logger.info("Ready! Listening for wake word ...")
        publish_idle_state()

        while True:
            if pending_utterance is not None and pending_utterance.done():
                try:
                    pending_utterance.result()
                except Exception as error:
                    logger.error("Utterance worker failed: %s", error, exc_info=True)
                    ui.publish(
                        "error",
                        state="error",
                        message=f"Utterance worker failed: {error}",
                    )
                    publish_idle_state()
                finally:
                    pending_utterance = None

            pomodoro_tick = pomodoro_timer.poll()
            if pomodoro_tick is not None:
                handle_pomodoro_tick(
                    pomodoro_tick,
                    speech_service=speech_service,
                    logger=logger,
                    ui=ui,
                    publish_idle_state=publish_idle_state,
                )

            timer_tick = countdown_timer.poll()
            if timer_tick is not None:
                handle_timer_tick(
                    timer_tick,
                    speech_service=speech_service,
                    logger=logger,
                    ui=ui,
                    publish_idle_state=publish_idle_state,
                )

            try:
                event = event_queue.get(timeout=0.25)
            except Empty:
                if not service.is_running:
                    logger.error("Service stopped unexpectedly")
                    ui.publish(
                        "error",
                        state="error",
                        message="Wake word service stopped unexpectedly",
                    )
                    return 1
                continue

            if isinstance(event, WakeWordDetectedEvent):
                print(f"[{event.occurred_at.isoformat()}] 🎤 WakeWordDetectedEvent\n")
                ui.publish_state("listening", message="Wake word detected")

            elif isinstance(event, UtteranceCapturedEvent):
                utterance = event.utterance
                print(
                    f"[{utterance.created_at.isoformat()}] ✓ UtteranceCapturedEvent: "
                    f"{utterance.duration_seconds:.2f}s, {len(utterance.audio_bytes):,} bytes\n"
                )
                if pending_utterance is not None and not pending_utterance.done():
                    logger.warning(
                        "Skipping utterance while previous request is still processing."
                    )
                    ui.publish_state(
                        "thinking", message="Previous request still processing"
                    )
                    continue

                ui.publish_state(
                    "transcribing",
                    message="Transcribing utterance",
                    duration_seconds=round(utterance.duration_seconds, 2),
                    audio_bytes=len(utterance.audio_bytes),
                )
                try:
                    pending_utterance = utterance_executor.submit(
                        process_utterance,
                        utterance=utterance,
                        stt=stt,
                        assistant_llm=assistant_llm,
                        speech_service=speech_service,
                        logger=logger,
                        ui=ui,
                        build_llm_environment_context=build_llm_environment_context,
                        handle_tool_call=dispatcher.handle_tool_call,
                        publish_idle_state=publish_idle_state,
                    )
                except Exception as error:
                    logger.error("Failed to submit utterance task: %s", error)
                    ui.publish(
                        "error",
                        state="error",
                        message=f"Failed to submit utterance task: {error}",
                    )
                    publish_idle_state()

            elif isinstance(event, WakeWordErrorEvent):
                logger.error(
                    f"WakeWordErrorEvent: {event.message}",
                    exc_info=event.exception,
                )
                ui.publish(
                    "error",
                    state="error",
                    message=f"WakeWordErrorEvent: {event.message}",
                )
                return 1

    except KeyboardInterrupt:
        print("\n👋 Shutting down...\n")
        return 0

    except Exception as error:
        logger.error(f"Unexpected error: {error}", exc_info=True)
        return 1

    finally:
        logger.info("Stopping utterance executor...")
        utterance_executor.shutdown(wait=False, cancel_futures=True)
        if service:
            logger.info("Stopping service...")
            try:
                service.stop(timeout_seconds=5.0)
            except Exception as error:
                logger.error(f"Error stopping service: {error}", exc_info=True)
        if ui_server:
            logger.info("Stopping UI server...")
            try:
                ui_server.stop(timeout_seconds=5.0)
            except Exception as error:
                logger.error(f"Error stopping UI server: {error}", exc_info=True)
