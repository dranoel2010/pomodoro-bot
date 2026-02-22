"""Runtime orchestration loop for wake-word events, ticks, and utterance jobs."""

from __future__ import annotations

import concurrent.futures
import datetime as dt
import logging
from dataclasses import dataclass
from queue import Empty, Queue
from typing import Any, Callable, Optional

from shared.defaults import DEFAULT_TIMER_DURATION_SECONDS
from app_config import AppConfig
from llm import EnvironmentContext, PomodoroAssistantLLM
from oracle import OracleContextService
from pomodoro import PomodoroTimer
from pomodoro.constants import ACTION_SYNC, REASON_STARTUP
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
from contracts.ui_protocol import (
    EVENT_ERROR,
    STATE_ERROR,
    STATE_IDLE,
    STATE_LISTENING,
    STATE_THINKING,
    STATE_TRANSCRIBING,
)

from .ticks import TickDependencies, TickProcessor
from .tool_dispatch import RuntimeToolDispatcher
from .ui import RuntimeUIPublisher
from .utterance import UtteranceDependencies, UtteranceProcessor


@dataclass(frozen=True)
class RuntimeHooks:
    """Injectable lifecycle hooks used by runtime startup and shutdown flow."""
    setup_signal_handlers: Callable[[WakeWordService], None]
    wait_for_service_ready: Callable[[WakeWordService, float], bool]


@dataclass(frozen=True)
class RuntimeBootstrap:
    """Dependency bundle required to construct the runtime engine."""
    logger: logging.Logger
    app_config: AppConfig
    wake_word_config: WakeWordConfig
    stt: FasterWhisperSTT
    assistant_llm: Optional[PomodoroAssistantLLM]
    speech_service: Optional[SpeechService]
    oracle_service: Optional[OracleContextService]
    ui_server: Optional[UIServer]
    hooks: RuntimeHooks


@dataclass
class RuntimeResources:
    """Mutable runtime resources created for the event loop lifecycle."""
    event_queue: Queue[Any]
    publisher: QueueEventPublisher
    utterance_executor: concurrent.futures.ThreadPoolExecutor
    pending_utterance: Optional[concurrent.futures.Future[None]] = None
    wakeword_service: Optional[WakeWordService] = None


class RuntimeEngine:
    """Main runtime loop that coordinates wake-word events and assistant flow."""
    def __init__(self, bootstrap: RuntimeBootstrap):
        self._bootstrap = bootstrap
        self._logger = bootstrap.logger

        self._ui = RuntimeUIPublisher(bootstrap.ui_server)
        self._pomodoro_timer = PomodoroTimer(logger=logging.getLogger("pomodoro"))
        self._countdown_timer = PomodoroTimer(
            duration_seconds=DEFAULT_TIMER_DURATION_SECONDS,
            logger=logging.getLogger("timer"),
        )
        self._dispatcher = RuntimeToolDispatcher(
            logger=self._logger,
            app_config=bootstrap.app_config,
            oracle_service=bootstrap.oracle_service,
            pomodoro_timer=self._pomodoro_timer,
            countdown_timer=self._countdown_timer,
            ui=self._ui,
        )

        self._tick_processor = TickProcessor(
            TickDependencies(
                speech_service=bootstrap.speech_service,
                logger=self._logger,
                ui=self._ui,
                publish_idle_state=self._publish_idle_state,
            )
        )
        self._utterance_processor = UtteranceProcessor(
            UtteranceDependencies(
                stt=bootstrap.stt,
                assistant_llm=bootstrap.assistant_llm,
                speech_service=bootstrap.speech_service,
                logger=self._logger,
                ui=self._ui,
                build_llm_environment_context=self._build_llm_environment_context,
                handle_tool_call=self._dispatcher.handle_tool_call,
                publish_idle_state=self._publish_idle_state,
            )
        )

        event_queue: Queue[Any] = Queue()
        self._resources = RuntimeResources(
            event_queue=event_queue,
            publisher=QueueEventPublisher(event_queue),
            utterance_executor=concurrent.futures.ThreadPoolExecutor(
                max_workers=1,
                thread_name_prefix="utterance",
            ),
        )

    def run(self) -> int:
        self._publish_startup_sync()

        try:
            self._resources.wakeword_service = WakeWordService(
                config=self._bootstrap.wake_word_config,
                publisher=self._resources.publisher,
                logger=logging.getLogger("wake_word"),
            )
            wakeword_service = self._resources.wakeword_service

            self._bootstrap.hooks.setup_signal_handlers(wakeword_service)

            self._logger.info("Starting wake word service...")
            wakeword_service.start()

            self._logger.debug("Initializing wake word detection...")
            if not self._bootstrap.hooks.wait_for_service_ready(
                wakeword_service, timeout=10.0
            ):
                if not wakeword_service.is_running:
                    self._logger.error("Service crashed during initialization.")
                else:
                    self._logger.error("Service initialization timed out.")
                return 1

            self._logger.info("Ready! Listening for wake word ...")
            self._publish_idle_state()

            while True:
                self._finalize_pending_utterance()
                self._emit_timer_ticks()

                event, loop_exit = self._poll_event()
                if loop_exit is not None:
                    return loop_exit
                if event is None:
                    continue

                event_exit = self._handle_event(event)
                if event_exit is not None:
                    return event_exit

        except KeyboardInterrupt:
            self._logger.info("Shutdown requested by keyboard interrupt.")
            return 0
        except Exception as error:
            self._logger.error("Unexpected error: %s", error, exc_info=True)
            return 1
        finally:
            self._shutdown()

    def _publish_idle_state(self) -> None:
        self._ui.publish_state(
            STATE_IDLE,
            message=self._dispatcher.active_runtime_message(),
        )

    def _build_llm_environment_context(self) -> EnvironmentContext:
        payload = {
            "now_local": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
            "light_level_lux": None,
            "air_quality": None,
            "upcoming_events": None,
        }
        oracle_service = self._bootstrap.oracle_service
        if oracle_service is not None:
            try:
                payload.update(oracle_service.build_environment_payload())
            except Exception as error:
                self._logger.warning("Failed to collect oracle context: %s", error)

        return EnvironmentContext(
            now_local=payload["now_local"],
            light_level_lux=payload.get("light_level_lux"),
            air_quality=payload.get("air_quality"),
            upcoming_events=payload.get("upcoming_events"),
        )

    def _publish_startup_sync(self) -> None:
        self._ui.publish_pomodoro_update(
            self._pomodoro_timer.snapshot(),
            action=ACTION_SYNC,
            accepted=True,
            reason=REASON_STARTUP,
        )
        self._ui.publish_timer_update(
            self._countdown_timer.snapshot(),
            action=ACTION_SYNC,
            accepted=True,
            reason=REASON_STARTUP,
        )

    def _finalize_pending_utterance(self) -> None:
        pending = self._resources.pending_utterance
        if pending is None or not pending.done():
            return

        try:
            pending.result()
        except Exception as error:
            self._logger.error("Utterance worker failed: %s", error, exc_info=True)
            self._ui.publish(
                EVENT_ERROR,
                state=STATE_ERROR,
                message=f"Utterance worker failed: {error}",
            )
            self._publish_idle_state()
        finally:
            self._resources.pending_utterance = None

    def _emit_timer_ticks(self) -> None:
        pomodoro_tick = self._pomodoro_timer.poll()
        if pomodoro_tick is not None:
            self._tick_processor.handle_pomodoro_tick(pomodoro_tick)

        timer_tick = self._countdown_timer.poll()
        if timer_tick is not None:
            self._tick_processor.handle_timer_tick(timer_tick)

    def _poll_event(self) -> tuple[Optional[Any], Optional[int]]:
        try:
            return self._resources.event_queue.get(timeout=0.25), None
        except Empty:
            wakeword_service = self._resources.wakeword_service
            if wakeword_service is None:
                return None, 1
            if not wakeword_service.is_running:
                self._logger.error("Service stopped unexpectedly")
                self._ui.publish(
                    EVENT_ERROR,
                    state=STATE_ERROR,
                    message="Wake word service stopped unexpectedly",
                )
                return None, 1
            return None, None

    def _submit_utterance(self, utterance: Any) -> None:
        self._ui.publish_state(
            STATE_TRANSCRIBING,
            message="Transcribing utterance",
            duration_seconds=round(utterance.duration_seconds, 2),
            audio_bytes=len(utterance.audio_bytes),
        )
        try:
            self._resources.pending_utterance = self._resources.utterance_executor.submit(
                self._utterance_processor.process,
                utterance,
            )
        except Exception as error:
            self._logger.error("Failed to submit utterance task: %s", error)
            self._ui.publish(
                EVENT_ERROR,
                state=STATE_ERROR,
                message=f"Failed to submit utterance task: {error}",
            )
            self._publish_idle_state()
            self._resources.pending_utterance = None

    def _handle_event(self, event: Any) -> Optional[int]:
        if isinstance(event, WakeWordDetectedEvent):
            self._logger.info("Wake word detected at %s", event.occurred_at.isoformat())
            self._ui.publish_state(STATE_LISTENING, message="Wake word detected")
            return None

        if isinstance(event, UtteranceCapturedEvent):
            utterance = event.utterance
            self._logger.info(
                "Captured utterance at %s (duration=%0.2fs, bytes=%d)",
                utterance.created_at.isoformat(),
                utterance.duration_seconds,
                len(utterance.audio_bytes),
            )
            pending = self._resources.pending_utterance
            if pending is not None and not pending.done():
                self._logger.warning(
                    "Skipping utterance while previous request is still processing."
                )
                self._ui.publish_state(
                    STATE_THINKING,
                    message="Previous request still processing",
                )
                return None

            self._submit_utterance(utterance)
            return None

        if isinstance(event, WakeWordErrorEvent):
            self._logger.error(
                "WakeWordErrorEvent: %s",
                event.message,
                exc_info=event.exception,
            )
            self._ui.publish(
                EVENT_ERROR,
                state=STATE_ERROR,
                message=f"WakeWordErrorEvent: {event.message}",
            )
            return 1

        self._logger.warning("Ignoring unknown event type: %s", type(event).__name__)
        return None

    def _shutdown(self) -> None:
        self._logger.info("Stopping utterance executor...")
        self._resources.utterance_executor.shutdown(wait=False, cancel_futures=True)

        wakeword_service = self._resources.wakeword_service
        if wakeword_service is not None:
            self._logger.info("Stopping service...")
            try:
                wakeword_service.stop(timeout_seconds=5.0)
            except Exception as error:
                self._logger.error("Error stopping service: %s", error, exc_info=True)

        ui_server = self._bootstrap.ui_server
        if ui_server is not None:
            self._logger.info("Stopping UI server...")
            try:
                ui_server.stop(timeout_seconds=5.0)
            except Exception as error:
                self._logger.error("Error stopping UI server: %s", error, exc_info=True)
