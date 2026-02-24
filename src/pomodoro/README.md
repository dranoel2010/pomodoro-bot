# pomodoro module

## Purpose
In-memory state machines for pomodoro sessions and generic countdown timers.

## Key files
- `service.py`: `PomodoroTimer` state machine and snapshot/result dataclasses.
- `constants.py`: action, phase, and reason constants.
- `tool_mapping.py`: remaps timer tools to pomodoro tools when a pomodoro is active.

## Configuration
No direct configuration in this module.
Runtime defaults are imported from `src/shared/defaults.py` and `src/pomodoro/constants.py`.

## Integration notes
- Runtime creates one `PomodoroTimer` for pomodoro and one for generic timer mode.
- Tool dispatch (`src/runtime/tool_dispatch.py`) applies actions and publishes updates.
- `poll()` emits one tick per second plus a completion tick.
