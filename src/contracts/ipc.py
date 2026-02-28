from __future__ import annotations

"""IPC envelope types for typed cross-process message passing."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class _RequestEnvelope:
    call_id: int
    payload: object


@dataclass(frozen=True, slots=True)
class _ResponseEnvelope:
    kind: str
    call_id: int | None = None
    payload: object | None = None
    error_type: str | None = None
    error_message: str | None = None
