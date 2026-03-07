"""Runtime orchestration loop for wake-word events, ticks, and utterance jobs."""

from __future__ import annotations

import concurrent.futures
import datetime as dt
import logging
from queue import Empty
from typing import Callable

from config import AppConfig
from contracts.ui_protocol import (
    EVENT_ERROR,
    STATE_ERROR,
    STATE_IDLE,
    STATE_LISTENING,
    STATE_THINKING,
    STATE_TRANSCRIBING,
)
from llm.types import EnvironmentContext
from oracle.service import OracleContextService
from pomodoro.constants import ACTION_SYNC, REASON_STARTUP
from server.service import UIServer
from stt.config import WakeWordConfig
from stt.events import (
    Utterance,
    UtteranceCapturedEvent,
    WakeWordDetectedEvent,
    WakeWordErrorEvent,
)
from stt.service import WakeWordService

from contracts.pipeline import LLMClient, STTClient, TTSClient
from .components import RuntimeComponents, _build_runtime_components
from .ticks import handle_pomodoro_tick, handle_timer_tick
from .utterance import process_utterance


def _noop_signal_handlers(service: WakeWordService) -> None:
    del service


def _wait_for_service_ready(service: WakeWordService, timeout: float) -> bool:
    return service.wait_until_ready(timeout=timeout)


class RuntimeEngine:
    """Main runtime loop that coordinates wake-word events and assistant flow."""

    def __init__(
        self,
        *,
        logger: logging.Logger,
        app_config: AppConfig,
        wake_word_config: WakeWordConfig,
        stt: STTClient,
        assistant_llm: LLMClient | None = None,
        speech_service: TTSClient | None = None,
        oracle_service: OracleContextService | None = None,
        ui_server: UIServer | None = None,
        components: RuntimeComponents | None = None,
        setup_signal_handlers: Callable[
            [WakeWordService], None
        ] = _noop_signal_handlers,
        wait_for_service_ready: Callable[
            [WakeWordService, float], bool
        ] = _wait_for_service_ready,
    ):
        self._logger = logger
        self._wake_word_config = wake_word_config
        self._stt = stt
        self._assistant_llm = assistant_llm
        self._speech_service = speech_service
        self._oracle_service = oracle_service
        self._ui_server = ui_server
        self._setup_signal_handlers = setup_signal_handlers
        self._wait_for_service_ready = wait_for_service_ready
        self._llm_fast_path_enabled = bool(app_config.llm.fast_path_enabled)
        self._logger.info(
            "LLM fast-path routing %s",
            "enabled" if self._llm_fast_path_enabled else "disabled",
        )

        runtime_components = components or _build_runtime_components(
            logger=self._logger,
            app_config=app_config,
            oracle_service=oracle_service,
            ui_server=ui_server,
        )
        self._ui = runtime_components.ui
        self._pomodoro_timer = runtime_components.pomodoro_timer
        self._countdown_timer = runtime_components.countdown_timer
        self._dispatcher = runtime_components.dispatcher
        self._event_queue = runtime_components.event_queue
        self._publisher = runtime_components.publisher
        self._utterance_executor = runtime_components.utterance_executor
        self._pomodoro_cycle = runtime_components.pomodoro_cycle
        self._pending_utterance: concurrent.futures.Future[None] | None = None
        self._wakeword_service: WakeWordService | None = None

    def run(self) -> int:
        try:
            if not self._start_wakeword_service():
                return 1
            self._publish_startup_sync()
            self._publish_idle_state()

            while True:
                if self._finalize_pending_utterance():
                    return 1
                self._emit_timer_ticks()

                event = self._poll_event()
                if event is None:
                    if self._wakeword_is_running():
                        continue
                    self._logger.error("Wake word service stopped unexpectedly")
                    self._publish_runtime_error(
                        "Wake word service stopped unexpectedly"
                    )
                    return 1

                if (event_exit := self._handle_event(event)) is not None:
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
        now_local = dt.datetime.now().astimezone().isoformat(timespec="seconds")
        light_level_lux = None
        air_quality = None
        upcoming_events = None

        if self._oracle_service is not None:
            try:
                payload = self._oracle_service.build_environment_payload()
                now_local = str(payload.get("now_local") or now_local)
                light_level_lux = payload.get("light_level_lux")
                air_quality = payload.get("air_quality")
                upcoming_events = payload.get("upcoming_events")
            except Exception as error:
                self._logger.warning("Failed to collect oracle context: %s", error)

        return EnvironmentContext(
            now_local=now_local,
            light_level_lux=light_level_lux,
            air_quality=air_quality,
            upcoming_events=upcoming_events,
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

    def _start_wakeword_service(self) -> bool:
        self._wakeword_service = WakeWordService(
            config=self._wake_word_config,
            publisher=self._publisher,
            logger=logging.getLogger("wake_word"),
        )
        wakeword_service = self._wakeword_service
        self._setup_signal_handlers(wakeword_service)

        self._logger.info("Starting wake word service...")
        wakeword_service.start()

        self._logger.debug("Initializing wake word detection...")
        if self._wait_for_service_ready(wakeword_service, timeout=10.0):
            self._logger.info("Ready! Listening for wake word ...")
            return True

        if wakeword_service.is_running:
            self._logger.error("Service initialization timed out.")
        else:
            self._logger.error("Service crashed during initialization.")
        return False

    def _wakeword_is_running(self) -> bool:
        wakeword_service = self._wakeword_service
        return wakeword_service is not None and wakeword_service.is_running

    def _publish_runtime_error(self, message: str) -> None:
        self._ui.publish(
            EVENT_ERROR,
            state=STATE_ERROR,
            message=message,
        )

    def _finalize_pending_utterance(self) -> bool:
        pending = self._pending_utterance
        if pending is None or not pending.done():
            return False

        self._pending_utterance = None
        try:
            pending.result()
        except Exception as error:
            self._logger.error("Utterance worker failed: %s", error, exc_info=True)
            self._publish_runtime_error(f"Utterance worker failed: {error}")
            return True
        return False

    def _emit_timer_ticks(self) -> None:
        pomodoro_tick = self._pomodoro_timer.poll()
        if pomodoro_tick is not None:
            handle_pomodoro_tick(
                pomodoro_tick,
                speech_service=self._speech_service,
                logger=self._logger,
                ui=self._ui,
                publish_idle_state=self._publish_idle_state,
                pomodoro_timer=self._pomodoro_timer,
                cycle=self._pomodoro_cycle,
            )

        timer_tick = self._countdown_timer.poll()
        if timer_tick is not None:
            handle_timer_tick(
                timer_tick,
                speech_service=self._speech_service,
                logger=self._logger,
                ui=self._ui,
                publish_idle_state=self._publish_idle_state,
            )

    def _poll_event(self) -> object | None:
        try:
            return self._event_queue.get(timeout=0.25)
        except Empty:
            return None

    def _submit_utterance(self, utterance: Utterance) -> None:
        self._ui.publish_state(
            STATE_TRANSCRIBING,
            message="Transcribing utterance",
            duration_seconds=round(utterance.duration_seconds, 2),
            audio_bytes=len(utterance.audio_bytes),
        )
        try:
            self._pending_utterance = self._utterance_executor.submit(
                process_utterance,
                utterance,
                stt=self._stt,
                assistant_llm=self._assistant_llm,
                speech_service=self._speech_service,
                logger=self._logger,
                ui=self._ui,
                build_llm_environment_context=self._build_llm_environment_context,
                handle_tool_call=self._dispatcher.handle_tool_call,
                publish_idle_state=self._publish_idle_state,
                llm_fast_path_enabled=self._llm_fast_path_enabled,
            )
        except Exception as error:
            self._logger.error("Failed to submit utterance task: %s", error)
            self._publish_runtime_error(f"Failed to submit utterance task: {error}")
            self._publish_idle_state()
            self._pending_utterance = None

    def _handle_event(self, event: object) -> int | None:
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
            pending = self._pending_utterance
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
            self._publish_runtime_error(f"WakeWordErrorEvent: {event.message}")
            return 1

        self._logger.warning("Ignoring unknown event type: %s", type(event).__name__)
        return None

    def _shutdown(self) -> None:
        self._logger.info("Stopping utterance executor...")
        self._utterance_executor.shutdown(wait=False, cancel_futures=True)

        wakeword_service = self._wakeword_service
        if wakeword_service is not None:
            self._logger.info("Stopping service...")
            try:
                wakeword_service.stop(timeout_seconds=5.0)
            except Exception as error:
                self._logger.error("Error stopping service: %s", error, exc_info=True)

        if self._ui_server is not None:
            self._logger.info("Stopping UI server...")
            try:
                self._ui_server.stop(timeout_seconds=5.0)
            except Exception as error:
                self._logger.error("Error stopping UI server: %s", error, exc_info=True)
