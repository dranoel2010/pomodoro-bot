"""Provider protocols and container types used by oracle services."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class OracleProviders:
    """Container bundling optional provider instances built at startup."""
    ens160: object | None = None
    temt6000: object | None = None
    calendar: object | None = None
