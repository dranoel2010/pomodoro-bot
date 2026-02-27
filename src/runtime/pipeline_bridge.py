"""Pipecat pipeline bridge with pending-utterance flow control."""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from typing import Any, Awaitable, Callable

from stt.events import Utterance


class PipecatPipelineBridge:
    """Runs the Pipecat pipeline thread and queues utterance frames."""

    def __init__(
        self,
        *,
        logger: logging.Logger,
        allow_interruptions: bool,
        metrics_enabled: bool,
        process_utterance: Callable[[Any], Awaitable[None]],
    ) -> None:
        self._logger = logger
        self._allow_interruptions = allow_interruptions
        self._metrics_enabled = metrics_enabled
        self._process_utterance = process_utterance

        self._thread = threading.Thread(
            target=self._run_thread,
            name="pipecat",
            daemon=True,
        )
        self._ready = threading.Event()
        self._failure: Exception | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._task: Any = None
        self._end_frame: Any = None
        self._utterance_frame: Any = None
        self._pending_utterances = 0
        self._pending_lock = threading.Lock()

    def start(self, timeout_seconds: float = 30.0) -> None:
        self._thread.start()
        if not self._ready.wait(timeout=timeout_seconds):
            raise RuntimeError("Pipecat pipeline initialization timed out")
        self.raise_failure()

    def raise_failure(self) -> None:
        if self._failure is not None:
            raise RuntimeError(f"Pipecat pipeline failed: {self._failure}") from self._failure

    def has_pending_utterance(self) -> bool:
        with self._pending_lock:
            return self._pending_utterances > 0

    def submit_utterance(self, utterance: Utterance) -> None:
        self.raise_failure()
        if self._loop is None or self._task is None or self._utterance_frame is None:
            raise RuntimeError("Pipecat pipeline is not ready")

        with self._pending_lock:
            if self._pending_utterances > 0:
                return
            self._pending_utterances += 1

        frame = self._utterance_frame(utterance)
        future = asyncio.run_coroutine_threadsafe(
            self._task.queue_frame(frame),
            self._loop,
        )
        try:
            future.result(timeout=5.0)
        except Exception:
            self._complete_pending_utterance()
            raise

    def stop(self, timeout_seconds: float = 10.0) -> None:
        if (
            self._loop is not None
            and self._task is not None
            and self._end_frame is not None
        ):
            try:
                future = asyncio.run_coroutine_threadsafe(
                    self._task.queue_frame(self._end_frame()),
                    self._loop,
                )
                future.result(timeout=5.0)
            except Exception as error:
                self._logger.warning("Failed to signal Pipecat end frame: %s", error)

        if self._thread.is_alive():
            self._thread.join(timeout=timeout_seconds)

    def _run_thread(self) -> None:
        try:
            asyncio.run(self._run_async())
        except Exception as error:
            self._failure = error
            self._ready.set()

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
                await bridge._process_and_complete(frame)

        pipeline = Pipeline([UtteranceProcessor()])
        params = PipelineParams(
            allow_interruptions=self._allow_interruptions,
            enable_metrics=self._metrics_enabled,
        )
        task = PipelineTask(pipeline, params=params, enable_rtvi=False)
        if not callable(getattr(task, "queue_frame", None)):
            raise RuntimeError("Pipecat task is missing queue_frame().")

        self._loop = asyncio.get_running_loop()
        self._task = task
        self._end_frame = EndFrame
        self._utterance_frame = UtteranceFrame
        self._ready.set()

        runner = PipelineRunner(handle_sigint=False)
        await runner.run(task)

    async def _process_and_complete(self, frame: Any) -> None:
        try:
            await self._process_utterance(frame)
        finally:
            self._complete_pending_utterance()

    def _complete_pending_utterance(self) -> None:
        with self._pending_lock:
            if self._pending_utterances > 0:
                self._pending_utterances -= 1
