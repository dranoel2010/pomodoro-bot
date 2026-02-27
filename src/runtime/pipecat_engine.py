"""Pipecat runtime loop for local wake->stt->llm->tool->tts execution."""

from __future__ import annotations

import logging
from queue import Empty, Queue
from typing import Callable

from app_config import AppConfig
from contracts.ui_protocol import (
    EVENT_ERROR,
    STATE_ERROR,
    STATE_IDLE,
    STATE_LISTENING,
    STATE_THINKING,
    STATE_TRANSCRIBING,
)
from pomodoro import PomodoroTimer
from pomodoro.constants import ACTION_SYNC, REASON_STARTUP
from shared.defaults import DEFAULT_TIMER_DURATION_SECONDS
from stt.config import WakeWordConfig
from stt.events import (
    EventPublisher,
    QueueEventPublisher,
    UtteranceCapturedEvent,
    WakeWordDetectedEvent,
    WakeWordErrorEvent,
)

from .pipeline_bridge import PipecatPipelineBridge
from .ports import (
    LLMClient,
    OracleContextClient,
    SpeechClient,
    STTClient,
    UIServerPort,
    WakeWordServiceFactory,
    WakeWordServicePort,
)
from .ticks import handle_pomodoro_tick, handle_timer_tick
from .tool_dispatch import RuntimeToolDispatcher
from .ui import RuntimeUIPublisher
from .utterance_handler import RuntimeUtteranceHandler


def _create_default_wakeword_service(
    config: WakeWordConfig,
    publisher: EventPublisher,
    logger: logging.Logger,
) -> WakeWordServicePort:
    from stt.service import WakeWordService

    return WakeWordService(
        config=config,
        publisher=publisher,
        logger=logger,
    )


def _noop_signal_handlers(service: WakeWordServicePort) -> None:
    del service


def _wait_for_service_ready(service: WakeWordServicePort, timeout: float) -> bool:
    return service.wait_until_ready(timeout=timeout)


class PipecatRuntimeEngine:
    """Main runtime loop coordinating wake-word events and Pipecat utterance jobs."""

    def __init__(
        self,
        *,
        logger: logging.Logger,
        app_config: AppConfig,
        wake_word_config: WakeWordConfig,
        stt: STTClient,
        assistant_llm: LLMClient | None = None,
        speech_service: SpeechClient | None = None,
        oracle_service: OracleContextClient | None = None,
        ui_server: UIServerPort | None = None,
        setup_signal_handlers: Callable[[WakeWordServicePort], None] = _noop_signal_handlers,
        wait_for_service_ready: Callable[[WakeWordServicePort, float], bool] = _wait_for_service_ready,
        create_wakeword_service: WakeWordServiceFactory = _create_default_wakeword_service,
    ):
        self._logger = logger
        self._wake_word_config = wake_word_config
        self._speech_service = speech_service
        self._ui_server = ui_server
        self._setup_signal_handlers = setup_signal_handlers
        self._wait_for_service_ready = wait_for_service_ready
        self._create_wakeword_service = create_wakeword_service

        self._ui = RuntimeUIPublisher(ui_server)
        self._pomodoro_timer = PomodoroTimer(logger=logging.getLogger("pomodoro"))
        self._countdown_timer = PomodoroTimer(
            duration_seconds=DEFAULT_TIMER_DURATION_SECONDS,
            logger=logging.getLogger("timer"),
        )
        self._dispatcher = RuntimeToolDispatcher(
            logger=self._logger,
            app_config=app_config,
            oracle_service=oracle_service,
            pomodoro_timer=self._pomodoro_timer,
            countdown_timer=self._countdown_timer,
            ui=self._ui,
        )

        self._event_queue: Queue[object] = Queue()
        self._publisher = QueueEventPublisher(self._event_queue)
        self._wakeword_service: WakeWordServicePort | None = None

        self._utterance_handler = RuntimeUtteranceHandler(
            logger=self._logger,
            stt=stt,
            assistant_llm=assistant_llm,
            speech_service=speech_service,
            oracle_service=oracle_service,
            dispatcher=self._dispatcher,
            ui=self._ui,
            llm_fast_path_enabled=bool(app_config.pipecat.llm.local_llama.fast_path_enabled),
            publish_idle_state=self._publish_idle_state,
        )
        self._pipeline = PipecatPipelineBridge(
            logger=self._logger,
            allow_interruptions=bool(app_config.pipecat.runtime.allow_interruptions),
            metrics_enabled=bool(app_config.pipecat.runtime.metrics_enabled),
            process_utterance=self._utterance_handler.process_utterance,
        )

    def run(self) -> int:
        try:
            if not self._start_wakeword_service():
                return 1
            self._pipeline.start(timeout_seconds=30.0)
            self._publish_startup_sync()
            self._publish_idle_state()

            while True:
                self._pipeline.raise_failure()
                self._emit_timer_ticks()
                try:
                    event = self._event_queue.get(timeout=0.25)
                except Empty:
                    event = None

                if event is None:
                    if self._wakeword_is_running():
                        continue
                    self._ui.publish(
                        EVENT_ERROR,
                        state=STATE_ERROR,
                        message="Wake word service stopped unexpectedly",
                    )
                    return 1

                if (event_exit := self._handle_event(event)) is not None:
                    return event_exit
        except KeyboardInterrupt:
            self._logger.info("Shutdown requested by keyboard interrupt")
            return 0
        except Exception as error:
            self._logger.error("Unexpected runtime error: %s", error, exc_info=True)
            return 1
        finally:
            self._shutdown()

    def _publish_idle_state(self) -> None:
        self._ui.publish_state(STATE_IDLE, message=self._dispatcher.active_runtime_message())

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
        self._wakeword_service = self._create_wakeword_service(
            config=self._wake_word_config,
            publisher=self._publisher,
            logger=logging.getLogger("wake_word"),
        )
        service = self._wakeword_service
        self._setup_signal_handlers(service)
        service.start()
        if self._wait_for_service_ready(service, timeout=10.0):
            self._logger.info("Ready! Listening for wake word ...")
            return True
        self._logger.error("Wake word service failed to initialize")
        return False

    def _wakeword_is_running(self) -> bool:
        service = self._wakeword_service
        return service is not None and service.is_running

    def _emit_timer_ticks(self) -> None:
        pomodoro_tick = self._pomodoro_timer.poll()
        if pomodoro_tick is not None:
            handle_pomodoro_tick(
                pomodoro_tick,
                speech_service=self._speech_service,
                logger=self._logger,
                ui=self._ui,
                publish_idle_state=self._publish_idle_state,
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

    def _handle_event(self, event: object) -> int | None:
        if isinstance(event, WakeWordDetectedEvent):
            self._ui.publish_state(STATE_LISTENING, message="Wake word detected")
            return None

        if isinstance(event, UtteranceCapturedEvent):
            utterance = event.utterance
            if self._pipeline.has_pending_utterance():
                self._ui.publish_state(STATE_THINKING, message="Previous request still processing")
                return None
            self._ui.publish_state(
                STATE_TRANSCRIBING,
                message="Transcribing utterance",
                duration_seconds=round(utterance.duration_seconds, 2),
                audio_bytes=len(utterance.audio_bytes),
            )
            self._pipeline.submit_utterance(utterance)
            return None

        if isinstance(event, WakeWordErrorEvent):
            self._ui.publish(
                EVENT_ERROR,
                state=STATE_ERROR,
                message=f"WakeWordErrorEvent: {event.message}",
            )
            return 1

        self._logger.warning("Ignoring unknown event type: %s", type(event).__name__)
        return None

    def _shutdown(self) -> None:
        try:
            self._pipeline.stop(timeout_seconds=10.0)
        except Exception as error:
            self._logger.warning("Error while stopping Pipecat pipeline: %s", error)

        if self._wakeword_service is not None:
            try:
                self._wakeword_service.stop(timeout_seconds=5.0)
            except Exception as error:
                self._logger.error("Error stopping wake-word service: %s", error)

        if self._ui_server is not None:
            try:
                self._ui_server.stop(timeout_seconds=5.0)
            except Exception as error:
                self._logger.error("Error stopping UI server: %s", error)
