from __future__ import annotations

import datetime as dt


def format_spoken_clock(value: dt.datetime | dt.time) -> str:
    hour = int(value.hour)
    minute = int(value.minute)
    if minute == 0:
        return f"{hour} Uhr"
    return f"{hour} Uhr {minute}"
