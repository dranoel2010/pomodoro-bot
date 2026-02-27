"""Pipecat runtime loop for local wake->stt->llm->tool->tts execution."""

from __future__ import annotations

import asyncio
import datetime as dt
import logging
import threading
import time
from queue import Empty, Queue
from typing import Any, Callable

from app_config import AppConfig
from contracts.ui_protocol import (
    EVENT_ASSISTANT_REPLY,
    EVENT_ERROR,
    EVENT_TRANSCRIPT,
    STATE_ERROR,
    STATE_IDLE,
    STATE_LISTENING,
    STATE_REPLYING,
    STATE_THINKING,
    STATE_TRANSCRIBING,
)
from llm.service import PomodoroAssistantLLM
from llm.types import EnvironmentContext
from oracle.service import OracleContextService
from pomodoro import PomodoroTimer
from pomodoro.constants import ACTION_SYNC, REASON_STARTUP
from server.service import UIServer
from shared.defaults import DEFAULT_TIMER_DURATION_SECONDS
from stt.config import WakeWordConfig
from stt.events import (
    QueueEventPublisher,
    Utterance,
    UtteranceCapturedEvent,
    WakeWordDetectedEvent,
    WakeWordErrorEvent,
)
from stt.service import WakeWordService
from stt.stt import FasterWhisperSTT
from tts.service import SpeechService

from .ticks import handle_pomodoro_tick, handle_timer_tick
from .tool_dispatch import RuntimeToolDispatcher
from .ui import RuntimeUIPublisher

try:
    from llm.fast_path import maybe_fast_path_response
except Exception:  # pragma: no cover - optional import in isolated tests
    maybe_fast_path_response = None


def _noop_signal_handlers(service: WakeWordService) -> None:
    del service


def _wait_for_service_ready(service: WakeWordService, timeout: float) -> bool:
    return service.wait_until_ready(timeout=timeout)


class PipecatRuntimeEngine:
    """Main runtime loop coordinating wake-word events and Pipecat utterance jobs."""

    def __init__(
        self,
        *,
        logger: logging.Logger,
        app_config: AppConfig,
        wake_word_config: WakeWordConfig,
        stt: FasterWhisperSTT,
        assistant_llm: PomodoroAssistantLLM | None = None,
        speech_service: SpeechService | None = None,
        oracle_service: OracleContextService | None = None,
        ui_server: UIServer | None = None,
        setup_signal_handlers: Callable[[WakeWordService], None] = _noop_signal_handlers,
        wait_for_service_ready: Callable[[WakeWordService, float], bool] = _wait_for_service_ready,
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
        self._llm_fast_path_enabled = bool(app_config.pipecat.llm.local_llama.fast_path_enabled)
        self._allow_interruptions = bool(app_config.pipecat.runtime.allow_interruptions)
        self._metrics_enabled = bool(app_config.pipecat.runtime.metrics_enabled)

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
        self._wakeword_service: WakeWordService | None = None

        self._pipeline_thread = threading.Thread(
            target=self._run_pipeline_thread,
            name="pipecat",
            daemon=True,
        )
        self._pipeline_ready = threading.Event()
        self._pipeline_failure: Exception | None = None
        self._pipeline_loop: asyncio.AbstractEventLoop | None = None
        self._pipeline_task: Any = None
        self._pipeline_end_frame: Any = None
        self._pipeline_utterance_frame: Any = None
        self._pending_utterances = 0
        self._pending_lock = threading.Lock()

    def run(self) -> int:
        try:
            if not self._start_wakeword_service():
                return 1
            self._start_pipeline()
            self._publish_startup_sync()
            self._publish_idle_state()

            while True:
                self._raise_pipeline_failure()
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

    def _start_pipeline(self) -> None:
        self._pipeline_thread.start()
        if not self._pipeline_ready.wait(timeout=30.0):
            raise RuntimeError("Pipecat pipeline initialization timed out")
        self._raise_pipeline_failure()

    def _raise_pipeline_failure(self) -> None:
        if self._pipeline_failure is not None:
            raise RuntimeError(f"Pipecat pipeline failed: {self._pipeline_failure}") from self._pipeline_failure

    def _submit_utterance(self, utterance: Utterance) -> None:
        self._raise_pipeline_failure()
        if self._pipeline_loop is None or self._pipeline_task is None or self._pipeline_utterance_frame is None:
            raise RuntimeError("Pipecat pipeline is not ready")

        with self._pending_lock:
            if self._pending_utterances > 0:
                return
            self._pending_utterances += 1

        frame = self._pipeline_utterance_frame(utterance)
        future = asyncio.run_coroutine_threadsafe(
            self._pipeline_task.queue_frame(frame),
            self._pipeline_loop,
        )
        try:
            future.result(timeout=5.0)
        except Exception:
            self._complete_utterance()
            raise

    def _complete_utterance(self) -> None:
        with self._pending_lock:
            if self._pending_utterances > 0:
                self._pending_utterances -= 1

    def _run_pipeline_thread(self) -> None:
        try:
            asyncio.run(self._run_pipeline_async())
        except Exception as error:
            self._pipeline_failure = error
            self._pipeline_ready.set()

    async def _run_pipeline_async(self) -> None:
        try:
            from pipecat.frames.frames import DataFrame, EndFrame
            from pipecat.pipeline.pipeline import Pipeline
            from pipecat.pipeline.runner import PipelineRunner
            from pipecat.pipeline.task import PipelineParams, PipelineTask
            from pipecat.processors.frame_processor import FrameProcessor
        except Exception as error:
            raise RuntimeError(
                "Pipecat dependency missing. Install the `pipecat-ai` package."
            ) from error

        engine = self

        class UtteranceFrame(DataFrame):
            def __init__(self, utterance: Utterance):
                super().__init__()
                self.utterance = utterance
                self.started_at = time.perf_counter()
                self.transcript_text = ""
                self.language: str | None = None
                self.confidence: float | None = None
                self.assistant_text = ""
                self.tool_call: dict[str, object] | None = None
                self.stt_duration_seconds: float | None = None
                self.llm_duration_seconds: float | None = None
                self.tts_duration_seconds: float | None = None
                self.fast_path_duration_seconds: float | None = None
                self.fast_path_used = False

        class UtteranceProcessor(FrameProcessor):
            async def process_frame(self, frame: Any, direction: Any) -> None:
                await super().process_frame(frame, direction)
                if not isinstance(frame, UtteranceFrame):
                    await self.push_frame(frame, direction)
                    return
                await engine._process_utterance(frame)

        pipeline = Pipeline([UtteranceProcessor()])
        params = PipelineParams(
            allow_interruptions=self._allow_interruptions,
            enable_metrics=self._metrics_enabled,
        )
        task = PipelineTask(pipeline, params=params, enable_rtvi=False)
        if not callable(getattr(task, "queue_frame", None)):
            raise RuntimeError("Pipecat task is missing queue_frame().")

        self._pipeline_loop = asyncio.get_running_loop()
        self._pipeline_task = task
        self._pipeline_end_frame = EndFrame
        self._pipeline_utterance_frame = UtteranceFrame
        self._pipeline_ready.set()

        runner = PipelineRunner(handle_sigint=False)
        await runner.run(task)

    async def _process_utterance(self, frame: Any) -> None:
        stage = "Transcription"
        try:
            started_at = time.perf_counter()
            result = self._stt.transcribe(frame.utterance)
            frame.stt_duration_seconds = time.perf_counter() - started_at
            frame.transcript_text = result.text.strip()
            frame.language = result.language
            frame.confidence = result.confidence
            if not frame.transcript_text:
                self._ui.publish_state(STATE_IDLE, message="No speech detected")
                return

            self._ui.publish(
                EVENT_TRANSCRIPT,
                state=STATE_TRANSCRIBING,
                text=frame.transcript_text,
                language=frame.language,
                confidence=frame.confidence,
            )

            if self._assistant_llm is not None:
                stage = "LLM processing"
                self._ui.publish_state(STATE_THINKING, message="Generating reply")
                llm_response: dict[str, object] | None = None

                if self._llm_fast_path_enabled and callable(maybe_fast_path_response):
                    started_at = time.perf_counter()
                    llm_response = maybe_fast_path_response(frame.transcript_text)
                    frame.fast_path_duration_seconds = time.perf_counter() - started_at
                    frame.fast_path_used = llm_response is not None

                if llm_response is None:
                    env = self._build_llm_environment_context()
                    started_at = time.perf_counter()
                    llm_response = self._assistant_llm.run(frame.transcript_text, env=env)
                    frame.llm_duration_seconds = time.perf_counter() - started_at

                frame.assistant_text = str(llm_response.get("assistant_text", "")).strip()
                raw_tool = llm_response.get("tool_call")
                frame.tool_call = raw_tool if isinstance(raw_tool, dict) else None

            stage = "Tool dispatch"
            if frame.tool_call is not None:
                frame.assistant_text = self._dispatcher.handle_tool_call(
                    frame.tool_call,
                    frame.assistant_text,
                ).strip()

            if frame.assistant_text:
                stage = "TTS playback"
                self._ui.publish_state(STATE_REPLYING, message="Delivering reply")
                self._ui.publish(EVENT_ASSISTANT_REPLY, text=frame.assistant_text)
                if self._speech_service is not None:
                    started_at = time.perf_counter()
                    self._speech_service.speak(frame.assistant_text)
                    frame.tts_duration_seconds = time.perf_counter() - started_at
        except Exception as error:
            self._logger.error("%s failed: %s", stage, error)
            self._ui.publish(
                EVENT_ERROR,
                state=STATE_ERROR,
                message=f"{stage} failed: {error}",
            )
        finally:
            total = time.perf_counter() - frame.started_at
            fmt = lambda value: "n/a" if value is None else str(round(value * 1000))
            self._logger.info(
                "Pipecat utterance metrics: total_ms=%d stt_ms=%s llm_ms=%s tts_ms=%s fast_path=%s fast_path_ms=%s transcript_chars=%d",
                round(total * 1000),
                fmt(frame.stt_duration_seconds),
                fmt(frame.llm_duration_seconds),
                fmt(frame.tts_duration_seconds),
                frame.fast_path_used,
                fmt(frame.fast_path_duration_seconds),
                len(frame.transcript_text),
            )
            self._publish_idle_state()
            self._complete_utterance()

    def _publish_idle_state(self) -> None:
        self._ui.publish_state(STATE_IDLE, message=self._dispatcher.active_runtime_message())

    def _build_llm_environment_context(self) -> EnvironmentContext:
        now_local = dt.datetime.now().astimezone().isoformat(timespec="seconds")
        payload: dict[str, object] = {}
        if self._oracle_service is not None:
            try:
                payload = self._oracle_service.build_environment_payload()
            except Exception as error:
                self._logger.warning("Failed to collect oracle context: %s", error)
        return EnvironmentContext(
            now_local=str(payload.get("now_local") or now_local),
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

    def _start_wakeword_service(self) -> bool:
        self._wakeword_service = WakeWordService(
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

    def _has_pending_utterance(self) -> bool:
        with self._pending_lock:
            return self._pending_utterances > 0

    def _handle_event(self, event: object) -> int | None:
        if isinstance(event, WakeWordDetectedEvent):
            self._ui.publish_state(STATE_LISTENING, message="Wake word detected")
            return None

        if isinstance(event, UtteranceCapturedEvent):
            utterance = event.utterance
            if self._has_pending_utterance():
                self._ui.publish_state(STATE_THINKING, message="Previous request still processing")
                return None
            self._ui.publish_state(
                STATE_TRANSCRIBING,
                message="Transcribing utterance",
                duration_seconds=round(utterance.duration_seconds, 2),
                audio_bytes=len(utterance.audio_bytes),
            )
            self._submit_utterance(utterance)
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
        if (
            self._pipeline_loop is not None
            and self._pipeline_task is not None
            and self._pipeline_end_frame is not None
        ):
            try:
                future = asyncio.run_coroutine_threadsafe(
                    self._pipeline_task.queue_frame(self._pipeline_end_frame()),
                    self._pipeline_loop,
                )
                future.result(timeout=5.0)
            except Exception as error:
                self._logger.warning("Failed to signal Pipecat end frame: %s", error)

        if self._pipeline_thread.is_alive():
            self._pipeline_thread.join(timeout=10.0)

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
