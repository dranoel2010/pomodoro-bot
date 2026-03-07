"""Deterministic fast-path routing for explicit tool commands."""

from __future__ import annotations

from typing import Any, cast

from contracts.tool_contract import (
    INTENT_TO_POMODORO_TOOL,
    INTENT_TO_TIMER_TOOL,
    TOOL_ADD_CALENDAR_EVENT,
    TOOL_SHOW_UPCOMING_EVENTS,
    TOOL_START_POMODORO,
    TOOL_START_TIMER,
    TOOL_STATUS_POMODORO,
    TOOL_TELL_JOKE,
    TOOLS_WITHOUT_ARGUMENTS,
)
from shared.defaults import (
    DEFAULT_CALENDAR_TIME_RANGE,
    DEFAULT_FOCUS_TOPIC_DE,
    DEFAULT_TIMER_MINUTES,
)

from .parser_extractors import (
    extract_calendar_title,
    extract_datetime_literal,
    extract_duration_from_prompt,
    extract_focus_topic,
    extract_time_range,
    normalize_duration,
    sanitize_text,
    sanitize_time_range,
)
from .parser_messages import fallback_assistant_text
from .parser_rules import (
    detect_action,
    has_pomodoro_context,
    has_timer_context,
    looks_like_add_calendar,
    looks_like_pomodoro_status,
    looks_like_show_events,
    looks_like_tell_joke,
)
from .types import StructuredResponse, ToolCall, ToolName


def maybe_fast_path_response(user_prompt: str) -> StructuredResponse | None:
    """Return a deterministic response for explicit tool intents.

    Bypasses llama.cpp entirely by applying stateless intent detection rules.
    Returns None if no deterministic tool intent is recognised.
    """
    prompt = user_prompt.strip()
    if not prompt:
        return None

    tool_call = _infer_tool_call(prompt)
    if tool_call is None:
        return None

    return {
        "assistant_text": fallback_assistant_text(tool_call),
        "tool_call": tool_call,
    }


def _infer_tool_call(prompt: str) -> ToolCall | None:
    """Stateless deterministic intent → ToolCall mapping."""
    lowered = prompt.lower()

    if looks_like_tell_joke(lowered):
        return _tool_call(TOOL_TELL_JOKE, {})

    if looks_like_add_calendar(lowered):
        title = sanitize_text(extract_calendar_title(prompt), max_len=120)
        start_time = extract_datetime_literal(prompt)
        if not title or not start_time:
            return None
        payload: dict[str, Any] = {"title": title, "start_time": start_time}
        return _tool_call(TOOL_ADD_CALENDAR_EVENT, payload)

    if looks_like_show_events(lowered):
        time_range = sanitize_time_range(
            extract_time_range(prompt) or DEFAULT_CALENDAR_TIME_RANGE
        )
        return _tool_call(TOOL_SHOW_UPCOMING_EVENTS, {"time_range": time_range})

    if looks_like_pomodoro_status(lowered) and has_pomodoro_context(lowered):
        return _tool_call(TOOL_STATUS_POMODORO, {})

    action = detect_action(prompt)
    if action is None:
        return None

    has_pomodoro = has_pomodoro_context(lowered)
    has_timer = has_timer_context(lowered)
    duration = extract_duration_from_prompt(prompt)

    if has_pomodoro:
        name = INTENT_TO_POMODORO_TOOL.get(action)
        if name is None:
            return None
        if name == TOOL_START_POMODORO:
            topic = sanitize_text(
                extract_focus_topic(prompt) or DEFAULT_FOCUS_TOPIC_DE, max_len=60
            )
            return _tool_call(name, {"focus_topic": topic})
        if name in TOOLS_WITHOUT_ARGUMENTS:
            return _tool_call(name, {})
        return None

    if has_timer or duration is not None:
        name = INTENT_TO_TIMER_TOOL.get(action)
        if name is None:
            return None
        if name == TOOL_START_TIMER:
            dur = normalize_duration(duration) or str(DEFAULT_TIMER_MINUTES)
            return _tool_call(name, {"duration": dur})
        if name in TOOLS_WITHOUT_ARGUMENTS:
            return _tool_call(name, {})
        return None

    return None


def _tool_call(name: str, arguments: dict[str, Any]) -> ToolCall:
    return {"name": cast(ToolName, name), "arguments": arguments}
