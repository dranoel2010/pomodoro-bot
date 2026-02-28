from __future__ import annotations

"""Shared cross-module contracts and protocol constants.

The single canonical namespace for all interface definitions.
"""

from contracts.ipc import _RequestEnvelope, _ResponseEnvelope
from contracts.oracle import OracleProviders
from contracts.pipeline import LLMClient, STTClient, TTSClient


class StartupError(Exception):
    """Raised when runtime startup cannot continue."""


__all__ = [
    "StartupError",
    "STTClient",
    "LLMClient",
    "TTSClient",
    "OracleProviders",
    "_RequestEnvelope",
    "_ResponseEnvelope",
]
