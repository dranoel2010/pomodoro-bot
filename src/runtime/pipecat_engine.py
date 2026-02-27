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

class _PipecatBridge:

    def __init__(
        self,
        *,
        logger: logging.Logger,
        stt: FasterWhisperSTT,
        assistant_llm: PomodoroAssistantLLM | None,
        speech_service: SpeechService | None,
        ui: RuntimeUIPublisher,
        dispatcher: RuntimeToolDispatcher,
        publish_idle_state: Callable[[], None],
        build_llm_environment_context: Callable[[], EnvironmentContext],
        llm_fast_path_enabled: bool,
        allow_interruptions: bool,
        metrics_enabled: bool,
    ):
        self._logger = logger
        self._stt = stt
        self._assistant_llm = assistant_llm
        self._speech_service = speech_service
        self._ui = ui
        self._dispatcher = dispatcher
        self._publish_idle_state = publish_idle_state
        self._build_llm_environment_context = build_llm_environment_context
        self._llm_fast_path_enabled = llm_fast_path_enabled
        self._allow_interruptions = allow_interruptions
        self._metrics_enabled = metrics_enabled
        self._thread = threading.Thread(target=self._run_thread, name="pipecat", daemon=True)
        self._ready = threading.Event()
        self._failure: Exception | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._task: Any = None
        self._end_frame: Any = None
        self._utterance_frame: Any = None
        self._pending = 0
        self._pending_lock = threading.Lock()

    def start(self) -> None:
        self._thread.start()
        if not self._ready.wait(timeout=30.0):
            raise RuntimeError("Pipecat pipeline initialization timed out")
        self.raise_if_failed()

    def stop(self) -> None:
        if self._loop is not None and self._task is not None and self._end_frame is not None:
            try:
                fut = asyncio.run_coroutine_threadsafe(
                    self._task.queue_frame(self._end_frame()),
                    self._loop,
                )
                fut.result(timeout=5.0)
            except Exception as error:
                self._logger.warning("Failed to signal Pipecat end frame: %s", error)
        if self._thread.is_alive():
            self._thread.join(timeout=10.0)

    def raise_if_failed(self) -> None:
        if self._failure is not None:
            raise RuntimeError(f"Pipecat pipeline failed: {self._failure}") from self._failure
    @property
    def has_pending_utterance(self) -> bool:
        with self._pending_lock:
            return self._pending > 0

    def submit_utterance(self, utterance: Utterance) -> bool:
        self.raise_if_failed()
        if self._loop is None or self._task is None or self._utterance_frame is None:
            raise RuntimeError("Pipecat pipeline is not ready")
        with self._pending_lock:
            if self._pending > 0:
                return False
            self._pending += 1
        frame = self._utterance_frame(utterance)
        fut = asyncio.run_coroutine_threadsafe(self._task.queue_frame(frame), self._loop)
        try:
            fut.result(timeout=5.0)
            return True
        except Exception:
            self._complete()
            raise

    def _run_thread(self) -> None:
        try:
            asyncio.run(self._run_async())
        except Exception as error:
            self._failure = error
            self._ready.set()

    def _complete(self) -> None:
        with self._pending_lock:
            if self._pending > 0:
                self._pending -= 1

    def _emit_error(self, prefix: str, error: Exception) -> None:
        self._logger.error("%s: %s", prefix, error)
        self._ui.publish(EVENT_ERROR, state=STATE_ERROR, message=f"{prefix}: {error}")
        self._publish_idle_state()

    def _log_metrics(self, frame: Any) -> None:
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

    async def _run_async(self) -> None:
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
        bridge = self
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
                stage = "Transcription"
                try:
                    started_at = time.perf_counter()
                    result = bridge._stt.transcribe(frame.utterance)
                    frame.stt_duration_seconds = time.perf_counter() - started_at
                    frame.transcript_text = result.text.strip()
                    frame.language = result.language
                    frame.confidence = result.confidence
                    if not frame.transcript_text:
                        bridge._ui.publish_state(STATE_IDLE, message="No speech detected")
                        return
                    bridge._ui.publish(
                        EVENT_TRANSCRIPT,
                        state=STATE_TRANSCRIBING,
                        text=frame.transcript_text,
                        language=frame.language,
                        confidence=frame.confidence,
                    )
                    if bridge._assistant_llm is not None:
                        stage = "LLM processing"
                        bridge._ui.publish_state(STATE_THINKING, message="Generating reply")
                        llm_response: dict[str, object] | None = None
                        if bridge._llm_fast_path_enabled and callable(maybe_fast_path_response):
                            started_at = time.perf_counter()
                            llm_response = maybe_fast_path_response(frame.transcript_text)
                            frame.fast_path_duration_seconds = time.perf_counter() - started_at
                            frame.fast_path_used = llm_response is not None
                        if llm_response is None:
                            env = bridge._build_llm_environment_context()
                            started_at = time.perf_counter()
                            llm_response = bridge._assistant_llm.run(frame.transcript_text, env=env)
                            frame.llm_duration_seconds = time.perf_counter() - started_at
                        frame.assistant_text = str(llm_response.get("assistant_text", "")).strip()
                        raw_tool = llm_response.get("tool_call")
                        frame.tool_call = raw_tool if isinstance(raw_tool, dict) else None
                    stage = "Tool dispatch"
                    if frame.tool_call is not None:
                        frame.assistant_text = bridge._dispatcher.handle_tool_call(
                            frame.tool_call,
                            frame.assistant_text,
                        ).strip()
                    if frame.assistant_text:
                        stage = "TTS playback"
                        bridge._ui.publish_state(STATE_REPLYING, message="Delivering reply")
                        bridge._ui.publish(EVENT_ASSISTANT_REPLY, text=frame.assistant_text)
                        if bridge._speech_service is not None:
                            started_at = time.perf_counter()
                            bridge._speech_service.speak(frame.assistant_text)
                            frame.tts_duration_seconds = time.perf_counter() - started_at
                except Exception as error:
                    bridge._emit_error(f"{stage} failed", error)
                finally:
                    bridge._publish_idle_state()
                    bridge._log_metrics(frame)
                    bridge._complete()
        pipeline = Pipeline([UtteranceProcessor()])
        params = PipelineParams(
            allow_interruptions=self._allow_interruptions,
            enable_metrics=self._metrics_enabled,
        )
        task = PipelineTask(pipeline, params=params, enable_rtvi=False)
        runner = PipelineRunner(handle_sigint=False)
        if not callable(getattr(task, "queue_frame", None)):
            raise RuntimeError("Pipecat task is missing queue_frame().")
        self._loop = asyncio.get_running_loop()
        self._task = task
        self._end_frame = EndFrame
        self._utterance_frame = UtteranceFrame
        self._ready.set()
        await runner.run(task)

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
        self._oracle_service = oracle_service
        self._ui_server = ui_server
        self._setup_signal_handlers = setup_signal_handlers
        self._wait_for_service_ready = wait_for_service_ready
        self._speech_service = speech_service
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
        self._pipeline = _PipecatBridge(
            logger=logger,
            stt=stt,
            assistant_llm=assistant_llm,
            speech_service=speech_service,
            ui=self._ui,
            dispatcher=self._dispatcher,
            publish_idle_state=self._publish_idle_state,
            build_llm_environment_context=self._build_llm_environment_context,
            llm_fast_path_enabled=bool(app_config.pipecat.llm.local_llama.fast_path_enabled),
            allow_interruptions=bool(app_config.pipecat.runtime.allow_interruptions),
            metrics_enabled=bool(app_config.pipecat.runtime.metrics_enabled),
        )
        self._event_queue: Queue[object] = Queue()
        self._publisher = QueueEventPublisher(self._event_queue)
        self._wakeword_service: WakeWordService | None = None

    def run(self) -> int:
        try:
            if not self._start_wakeword_service():
                return 1
            self._pipeline.start()
            self._publish_startup_sync()
            self._publish_idle_state()
            while True:
                self._pipeline.raise_if_failed()
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

    def _handle_event(self, event: object) -> int | None:
        if isinstance(event, WakeWordDetectedEvent):
            self._ui.publish_state(STATE_LISTENING, message="Wake word detected")
            return None
        if isinstance(event, UtteranceCapturedEvent):
            utterance = event.utterance
            if self._pipeline.has_pending_utterance:
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
        self._pipeline.stop()
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
