"""Runtime startup composition helpers."""

from __future__ import annotations

import concurrent.futures
import logging
from dataclasses import dataclass
from queue import Queue

from config import AppConfig
from oracle.service import OracleContextService
from pomodoro import PomodoroCycleState, PomodoroTimer
from server.service import UIServer
from shared.defaults import DEFAULT_TIMER_DURATION_SECONDS
from stt.events import QueueEventPublisher

from .tools.dispatch import RuntimeToolDispatcher
from .ui import RuntimeUIPublisher


@dataclass(slots=True)
class RuntimeComponents:
    """Container for runtime collaborators built at startup composition time."""

    ui: RuntimeUIPublisher
    pomodoro_timer: PomodoroTimer
    countdown_timer: PomodoroTimer
    dispatcher: RuntimeToolDispatcher
    event_queue: Queue[object]
    publisher: QueueEventPublisher
    utterance_executor: concurrent.futures.ThreadPoolExecutor
    pomodoro_cycle: PomodoroCycleState | None = None


def _build_runtime_components(
    *,
    logger: logging.Logger,
    app_config: AppConfig,
    oracle_service: OracleContextService | None,
    ui_server: UIServer | None,
) -> RuntimeComponents:
    ui = RuntimeUIPublisher(ui_server)
    pomodoro_timer = PomodoroTimer(logger=logging.getLogger("pomodoro"))
    countdown_timer = PomodoroTimer(
        duration_seconds=DEFAULT_TIMER_DURATION_SECONDS,
        logger=logging.getLogger("timer"),
    )
    pomodoro_cycle = PomodoroCycleState()
    dispatcher = RuntimeToolDispatcher(
        logger=logger,
        app_config=app_config,
        oracle_service=oracle_service,
        pomodoro_timer=pomodoro_timer,
        countdown_timer=countdown_timer,
        ui=ui,
        pomodoro_cycle=pomodoro_cycle,
    )
    event_queue: Queue[object] = Queue()
    publisher = QueueEventPublisher(event_queue)
    utterance_executor = concurrent.futures.ThreadPoolExecutor(
        max_workers=1,
        thread_name_prefix="utterance",
    )
    return RuntimeComponents(
        ui=ui,
        pomodoro_timer=pomodoro_timer,
        countdown_timer=countdown_timer,
        dispatcher=dispatcher,
        event_queue=event_queue,
        publisher=publisher,
        utterance_executor=utterance_executor,
        pomodoro_cycle=pomodoro_cycle,
    )
