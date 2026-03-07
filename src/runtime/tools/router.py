"""Routing helpers for normalized runtime tool calls."""

from __future__ import annotations

from dataclasses import dataclass

import contracts.tool_contract as _tc
from llm.types import JSONObject, ToolCall
from pomodoro import remap_timer_tool_for_active_pomodoro


@dataclass(frozen=True, slots=True)
class RoutedToolCall:
    """Normalized tool call resolved to a runtime route."""

    tool_name: str
    arguments: JSONObject
    route: str


def route_tool_call(
    tool_call: ToolCall,
    *,
    pomodoro_active: bool,
) -> RoutedToolCall:
    raw_name = tool_call["name"]
    arguments: JSONObject = tool_call.get("arguments", {})
    normalized_name = remap_timer_tool_for_active_pomodoro(
        raw_name,
        pomodoro_active=pomodoro_active,
    )

    match normalized_name:
        case _tc.TOOL_STATUS_POMODORO:
            route = "pomodoro_status"
        case (
            _tc.TOOL_START_POMODORO
            | _tc.TOOL_STOP_POMODORO
            | _tc.TOOL_PAUSE_POMODORO
            | _tc.TOOL_CONTINUE_POMODORO
            | _tc.TOOL_RESET_POMODORO
        ):
            route = "pomodoro"
        case (
            _tc.TOOL_START_TIMER
            | _tc.TOOL_STOP_TIMER
            | _tc.TOOL_PAUSE_TIMER
            | _tc.TOOL_CONTINUE_TIMER
            | _tc.TOOL_RESET_TIMER
        ):
            route = "timer"
        case _tc.TOOL_SHOW_UPCOMING_EVENTS | _tc.TOOL_ADD_CALENDAR_EVENT:
            route = "calendar"
        case _tc.TOOL_TELL_JOKE:
            route = "tell_joke"
        case _:
            route = "unsupported"

    return RoutedToolCall(
        tool_name=normalized_name,
        arguments=arguments,
        route=route,
    )
