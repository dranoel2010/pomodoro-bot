"""Provider protocols and container types used by oracle services."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class OracleProviders:
    """Container bundling optional provider instances built at startup."""
    ens160: Optional[object] = None
    temt6000: Optional[object] = None
    calendar: Optional[object] = None
