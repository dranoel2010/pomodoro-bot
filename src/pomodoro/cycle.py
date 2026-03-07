"""Autonomous pomodoro cycle state tracker."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from shared.defaults import DEFAULT_FOCUS_TOPIC_DE
from .constants import (
    ACTION_RESET,
    DEFAULT_LONG_BREAK_SECONDS,
    DEFAULT_LONG_BREAK_SESSION_NAME,
    DEFAULT_POMODORO_SECONDS,
    DEFAULT_SHORT_BREAK_SECONDS,
    DEFAULT_SHORT_BREAK_SESSION_NAME,
    PHASE_TYPE_LONG_BREAK,
    PHASE_TYPE_SHORT_BREAK,
    PHASE_TYPE_WORK,
    SESSIONS_PER_CYCLE,
)

if TYPE_CHECKING:
    from .service import PomodoroTimer


@dataclass(frozen=True, slots=True)
class PhaseTransition:
    """Immutable value object describing an autonomous phase transition."""

    new_phase_type: str
    previous_phase_type: str
    session_count: int
    duration_seconds: int


@dataclass(slots=True)
class PomodoroCycleState:
    """Mutable autonomous cycle state tracker."""

    work_seconds: int = DEFAULT_POMODORO_SECONDS
    break_seconds: int = DEFAULT_SHORT_BREAK_SECONDS
    long_break_seconds: int = DEFAULT_LONG_BREAK_SECONDS
    _active: bool = field(default=False, init=False)
    _phase_type: str = field(default=PHASE_TYPE_WORK, init=False)
    _session_count: int = field(default=0, init=False)
    _work_session_name: str = field(default=DEFAULT_FOCUS_TOPIC_DE, init=False)

    def begin_cycle(self, *, session_name: str) -> None:
        """Start or restart the autonomous cycle in the work phase."""
        self._active = True
        self._phase_type = PHASE_TYPE_WORK
        self._session_count = 0
        self._work_session_name = session_name

    def reset(self) -> None:
        """Deactivate the cycle (e.g. when user manually stops the session)."""
        self._active = False
        self._phase_type = PHASE_TYPE_WORK
        self._session_count = 0

    def advance(self, timer: PomodoroTimer) -> PhaseTransition:
        """Advance to the next phase, reset the timer, and return the transition."""
        if self._phase_type == PHASE_TYPE_WORK:
            self._session_count += 1
            if self._session_count >= SESSIONS_PER_CYCLE:
                self._phase_type = PHASE_TYPE_LONG_BREAK
                timer.apply(
                    ACTION_RESET,
                    session=DEFAULT_LONG_BREAK_SESSION_NAME,
                    duration_seconds=self.long_break_seconds,
                )
                return PhaseTransition(
                    new_phase_type=PHASE_TYPE_LONG_BREAK,
                    previous_phase_type=PHASE_TYPE_WORK,
                    session_count=self._session_count,
                    duration_seconds=self.long_break_seconds,
                )
            else:
                self._phase_type = PHASE_TYPE_SHORT_BREAK
                timer.apply(
                    ACTION_RESET,
                    session=DEFAULT_SHORT_BREAK_SESSION_NAME,
                    duration_seconds=self.break_seconds,
                )
                return PhaseTransition(
                    new_phase_type=PHASE_TYPE_SHORT_BREAK,
                    previous_phase_type=PHASE_TYPE_WORK,
                    session_count=self._session_count,
                    duration_seconds=self.break_seconds,
                )
        elif self._phase_type == PHASE_TYPE_LONG_BREAK:
            self._session_count = 0
            self._phase_type = PHASE_TYPE_WORK
            timer.apply(
                ACTION_RESET,
                session=self._work_session_name,
                duration_seconds=self.work_seconds,
            )
            return PhaseTransition(
                new_phase_type=PHASE_TYPE_WORK,
                previous_phase_type=PHASE_TYPE_LONG_BREAK,
                session_count=self._session_count,
                duration_seconds=self.work_seconds,
            )
        else:  # PHASE_TYPE_SHORT_BREAK
            self._phase_type = PHASE_TYPE_WORK
            timer.apply(
                ACTION_RESET,
                session=self._work_session_name,
                duration_seconds=self.work_seconds,
            )
            return PhaseTransition(
                new_phase_type=PHASE_TYPE_WORK,
                previous_phase_type=PHASE_TYPE_SHORT_BREAK,
                session_count=self._session_count,
                duration_seconds=self.work_seconds,
            )

    @property
    def active(self) -> bool:
        """True when an autonomous cycle is running."""
        return self._active

    @property
    def session_count(self) -> int:
        """Number of completed work sessions in the current cycle."""
        return self._session_count

    @property
    def phase_type(self) -> str:
        """Current phase type: PHASE_TYPE_WORK, PHASE_TYPE_SHORT_BREAK, or PHASE_TYPE_LONG_BREAK."""
        return self._phase_type
