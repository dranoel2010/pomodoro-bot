"""Thread-safe in-memory pomodoro/timer state machine."""

from __future__ import annotations

import logging
import math
import threading
import time
from dataclasses import dataclass
from typing import Literal, Optional

from .constants import (
    ACTION_ABORT,
    ACTION_CONTINUE,
    ACTION_PAUSE,
    ACTION_RESET,
    ACTION_START,
    ACTIVE_PHASES,
    DEFAULT_POMODORO_SECONDS,
    DEFAULT_POMODORO_SESSION_NAME,
    PHASE_ABORTED,
    PHASE_COMPLETED,
    PHASE_IDLE,
    PHASE_PAUSED,
    PHASE_RUNNING,
    REASON_ABORTED,
    REASON_CONTINUED,
    REASON_INVALID_STATE,
    REASON_NOT_ACTIVE,
    REASON_NOT_PAUSED,
    REASON_NOT_RUNNING,
    REASON_PAUSED,
    REASON_RESET,
    REASON_STARTED,
    REASON_UNSUPPORTED_ACTION,
)

PomodoroPhase = Literal["idle", "running", "paused", "completed", "aborted"]
PomodoroAction = Literal["start", "pause", "continue", "abort", "reset"]


@dataclass(frozen=True)
class PomodoroSnapshot:
    """Immutable timer snapshot exposed to runtime and UI publishers."""
    phase: PomodoroPhase
    session: Optional[str]
    duration_seconds: int
    remaining_seconds: int

    @property
    def is_active(self) -> bool:
        return self.phase in ACTIVE_PHASES


@dataclass(frozen=True)
class PomodoroActionResult:
    """Result envelope returned after applying a timer or pomodoro action."""
    action: PomodoroAction
    accepted: bool
    reason: str
    snapshot: PomodoroSnapshot


@dataclass(frozen=True)
class PomodoroTick:
    """Tick payload emitted while countdown timers are running."""
    snapshot: PomodoroSnapshot
    completed: bool = False


class PomodoroTimer:
    """In-memory pomodoro state machine with monotonic timing."""

    def __init__(
        self,
        *,
        duration_seconds: int = DEFAULT_POMODORO_SECONDS,
        logger: Optional[logging.Logger] = None,
    ):
        if duration_seconds <= 0:
            raise ValueError("duration_seconds must be greater than zero")

        self._default_duration_seconds = int(duration_seconds)
        self._duration_seconds = self._default_duration_seconds
        self._logger = logger or logging.getLogger("pomodoro")
        self._lock = threading.Lock()

        self._phase: PomodoroPhase = PHASE_IDLE
        self._session: Optional[str] = None
        self._started_at_monotonic: Optional[float] = None
        self._paused_at_monotonic: Optional[float] = None
        self._paused_total_seconds: float = 0.0
        self._terminal_remaining_seconds: int = self._duration_seconds
        self._last_emitted_remaining: Optional[int] = None

    def snapshot(self) -> PomodoroSnapshot:
        with self._lock:
            return self._snapshot_locked(time.monotonic())

    def apply(
        self,
        action: PomodoroAction,
        *,
        session: Optional[str] = None,
        duration_seconds: Optional[int] = None,
    ) -> PomodoroActionResult:
        with self._lock:
            now = time.monotonic()
            if action == ACTION_START:
                self._start_locked(
                    now,
                    session=session,
                    duration_seconds=duration_seconds,
                )
                return self._result_locked(action, True, REASON_STARTED, now)

            if action == ACTION_RESET:
                reset_session = session or self._session or DEFAULT_POMODORO_SESSION_NAME
                self._start_locked(
                    now,
                    session=reset_session,
                    duration_seconds=duration_seconds,
                )
                return self._result_locked(action, True, REASON_RESET, now)

            if action == ACTION_PAUSE:
                if self._phase != PHASE_RUNNING:
                    return self._result_locked(action, False, REASON_NOT_RUNNING, now)

                self._terminal_remaining_seconds = self._running_remaining_locked(now)
                self._paused_at_monotonic = now
                self._phase = PHASE_PAUSED
                self._last_emitted_remaining = self._terminal_remaining_seconds
                self._logger.info(
                    "Pomodoro paused: session=%s remaining=%ss",
                    self._session,
                    self._terminal_remaining_seconds,
                )
                return self._result_locked(action, True, REASON_PAUSED, now)

            if action == ACTION_CONTINUE:
                if self._phase != PHASE_PAUSED:
                    return self._result_locked(action, False, REASON_NOT_PAUSED, now)

                paused_at = self._paused_at_monotonic
                if paused_at is None:
                    return self._result_locked(action, False, REASON_INVALID_STATE, now)

                self._paused_total_seconds += max(0.0, now - paused_at)
                self._paused_at_monotonic = None
                self._phase = PHASE_RUNNING
                self._last_emitted_remaining = None
                self._logger.info("Pomodoro continued: session=%s", self._session)
                return self._result_locked(action, True, REASON_CONTINUED, now)

            if action == ACTION_ABORT:
                if self._phase not in ACTIVE_PHASES:
                    return self._result_locked(action, False, REASON_NOT_ACTIVE, now)

                self._terminal_remaining_seconds = self._current_remaining_locked(now)
                self._paused_at_monotonic = None
                self._phase = PHASE_ABORTED
                self._last_emitted_remaining = self._terminal_remaining_seconds
                self._logger.info(
                    "Pomodoro aborted: session=%s remaining=%ss",
                    self._session,
                    self._terminal_remaining_seconds,
                )
                return self._result_locked(action, True, REASON_ABORTED, now)

            return self._result_locked(action, False, REASON_UNSUPPORTED_ACTION, now)

    def poll(self) -> Optional[PomodoroTick]:
        """Return tick updates while running (max once per second + completion)."""
        with self._lock:
            if self._phase != PHASE_RUNNING:
                return None

            now = time.monotonic()
            remaining = self._running_remaining_locked(now)
            if remaining <= 0:
                if self._phase != PHASE_COMPLETED:
                    self._phase = PHASE_COMPLETED
                    self._terminal_remaining_seconds = 0
                    self._last_emitted_remaining = 0
                    self._logger.info("Pomodoro completed: session=%s", self._session)
                    return PomodoroTick(snapshot=self._snapshot_locked(now), completed=True)
                return None

            if self._last_emitted_remaining == remaining:
                return None

            self._last_emitted_remaining = remaining
            return PomodoroTick(snapshot=self._snapshot_locked(now), completed=False)

    def _start_locked(
        self,
        now: float,
        *,
        session: Optional[str],
        duration_seconds: Optional[int] = None,
    ) -> None:
        if duration_seconds is not None and int(duration_seconds) > 0:
            self._duration_seconds = int(duration_seconds)

        session_name = _sanitize_session_name(
            session or self._session or DEFAULT_POMODORO_SESSION_NAME
        )
        self._session = session_name
        self._phase = PHASE_RUNNING
        self._started_at_monotonic = now
        self._paused_at_monotonic = None
        self._paused_total_seconds = 0.0
        self._terminal_remaining_seconds = self._duration_seconds
        self._last_emitted_remaining = None
        self._logger.info(
            "Pomodoro started: session=%s duration=%ss",
            self._session,
            self._duration_seconds,
        )

    def _result_locked(
        self,
        action: PomodoroAction,
        accepted: bool,
        reason: str,
        now: float,
    ) -> PomodoroActionResult:
        return PomodoroActionResult(
            action=action,
            accepted=accepted,
            reason=reason,
            snapshot=self._snapshot_locked(now),
        )

    def _snapshot_locked(self, now: float) -> PomodoroSnapshot:
        return PomodoroSnapshot(
            phase=self._phase,
            session=self._session,
            duration_seconds=self._duration_seconds,
            remaining_seconds=self._current_remaining_locked(now),
        )

    def _current_remaining_locked(self, now: float) -> int:
        if self._phase == PHASE_IDLE:
            return self._duration_seconds
        if self._phase == PHASE_RUNNING:
            return self._running_remaining_locked(now)
        if self._phase == PHASE_PAUSED:
            paused_at = self._paused_at_monotonic or now
            return self._running_remaining_locked(paused_at)
        if self._phase == PHASE_COMPLETED:
            return 0
        return self._terminal_remaining_seconds

    def _running_remaining_locked(self, now: float) -> int:
        if self._started_at_monotonic is None:
            return self._duration_seconds

        elapsed = now - self._started_at_monotonic - self._paused_total_seconds
        elapsed = max(0.0, elapsed)
        remaining = int(math.ceil(self._duration_seconds - elapsed))
        return max(0, min(self._duration_seconds, remaining))


def _sanitize_session_name(name: str) -> str:
    compact = " ".join(name.split())
    compact = compact.strip()[:60]
    return compact or DEFAULT_POMODORO_SESSION_NAME
