from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Callable, Optional, cast

from tool_contract import INTENT_TO_POMODORO_TOOL, INTENT_TO_TIMER_TOOL, TOOL_NAMES

from .parser_extractors import (
    extract_calendar_title,
    extract_datetime_literal,
    extract_duration_from_prompt,
    extract_focus_topic,
    extract_time_range,
    normalize_calendar_datetime_input,
    normalize_duration,
    sanitize_text,
    sanitize_time_range,
)
from .parser_messages import fallback_assistant_text, normalize_assistant_text
from .parser_rules import (
    LEGACY_ACTION_BY_TOOL,
    detect_action,
    has_pomodoro_context,
    has_timer_context,
    looks_like_add_calendar,
    looks_like_show_events,
)
from .types import StructuredResponse, ToolCall, ToolName

class ResponseParser:
    def __init__(self):
        self._last_focus_topic: Optional[str] = None
        self._last_time_range: str = "heute"

    def parse(self, content: str, user_prompt: str) -> StructuredResponse:
        parsed = self._load_json_object(content)
        if parsed is not None:
            normalized = self._validate_and_normalize(parsed, user_prompt)
            if normalized is not None:
                return normalized

        inferred = self._infer_tool_call_from_prompt(user_prompt)
        return {
            "assistant_text": self._fallback_assistant_text(inferred),
            "tool_call": inferred,
        }

    def _load_json_object(self, content: str) -> Optional[dict[str, Any]]:
        text = content.strip()
        if not text:
            return None

        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None

        snippet = text[start : end + 1]
        try:
            parsed = json.loads(snippet)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None

    def _validate_and_normalize(
        self, obj: dict[str, Any], user_prompt: str
    ) -> Optional[StructuredResponse]:
        assistant_raw = obj.get("assistant_text")
        if isinstance(assistant_raw, str):
            assistant_text = assistant_raw.strip()
        elif assistant_raw is None:
            assistant_text = ""
        else:
            assistant_text = str(assistant_raw).strip()

        tool_call = self._normalize_tool_call(obj.get("tool_call"), user_prompt)
        if tool_call is None:
            tool_call = self._infer_tool_call_from_prompt(user_prompt)

        assistant_text = self._normalize_assistant_text(assistant_text, tool_call)
        return {"assistant_text": assistant_text, "tool_call": tool_call}

    def _normalize_tool_call(
        self, tool_call: Any, user_prompt: str
    ) -> Optional[ToolCall]:
        if tool_call is None:
            return None
        if not isinstance(tool_call, dict):
            return None

        raw_name = tool_call.get("name")
        if not isinstance(raw_name, str):
            return None

        raw_arguments = tool_call.get("arguments")
        arguments = raw_arguments if isinstance(raw_arguments, dict) else {}
        normalized_name = self._resolve_tool_name(raw_name, arguments, user_prompt)
        if normalized_name is None:
            return None

        normalized_arguments = self._normalize_arguments_for_tool(
            normalized_name, arguments, user_prompt
        )
        if normalized_arguments is None:
            return None

        return self._tool_call(normalized_name, normalized_arguments)

    def _resolve_tool_name(
        self, raw_name: str, arguments: dict[str, Any], user_prompt: str
    ) -> Optional[str]:
        normalized_name = raw_name.strip()
        if normalized_name in TOOL_NAMES:
            return normalized_name

        action = LEGACY_ACTION_BY_TOOL.get(normalized_name)
        if action is None:
            return None

        if normalized_name == "timer_start":
            if "focus_topic" in arguments or "session" in arguments:
                return INTENT_TO_POMODORO_TOOL[action]
            if "duration" in arguments:
                return INTENT_TO_TIMER_TOOL[action]

        lowered = user_prompt.lower()
        has_pomodoro = has_pomodoro_context(lowered)
        has_timer = has_timer_context(lowered)

        if has_pomodoro and not has_timer:
            return INTENT_TO_POMODORO_TOOL[action]
        if has_timer and not has_pomodoro:
            return INTENT_TO_TIMER_TOOL[action]

        # Keep legacy behavior as default for ambiguous old aliases.
        return INTENT_TO_POMODORO_TOOL[action]

    def _normalize_arguments_for_tool(
        self, tool_name: str, arguments: dict[str, Any], user_prompt: str
    ) -> Optional[dict[str, Any]]:
        if tool_name == "start_timer":
            duration = normalize_duration(arguments.get("duration"))
            if duration is None:
                duration = extract_duration_from_prompt(user_prompt) or "10"
            return {"duration": duration}

        if tool_name in {
            "stop_timer",
            "pause_timer",
            "continue_timer",
            "reset_timer",
            "stop_pomodoro_session",
            "pause_pomodoro_session",
            "continue_pomodoro_session",
            "reset_pomodoro_session",
        }:
            return {}

        if tool_name == "start_pomodoro_session":
            raw_topic = (
                arguments.get("focus_topic")
                or arguments.get("session")
                or extract_focus_topic(user_prompt)
                or self._last_focus_topic
                or "Fokus"
            )
            topic = sanitize_text(raw_topic, max_len=60) or "Fokus"
            self._last_focus_topic = topic
            return {"focus_topic": topic}

        if tool_name == "show_upcoming_events":
            time_range = sanitize_time_range(
                arguments.get("time_range")
                or extract_time_range(user_prompt)
                or self._last_time_range
                or "heute"
            )
            self._last_time_range = time_range
            return {"time_range": time_range}

        if tool_name == "add_calendar_event":
            now_local = datetime.now().astimezone()
            now_fn = lambda: now_local
            title = sanitize_text(
                arguments.get("title") or extract_calendar_title(user_prompt),
                max_len=120,
            )
            start_time = (
                normalize_calendar_datetime_input(
                    arguments.get("start_time"),
                    now_fn=now_fn,
                )
                or self._extract_datetime_literal(user_prompt, now_fn=now_fn)
            )
            end_time = normalize_calendar_datetime_input(
                arguments.get("end_time"),
                now_fn=now_fn,
            )
            duration = normalize_duration(arguments.get("duration"))

            if not title or not start_time:
                return None

            payload: dict[str, Any] = {
                "title": title,
                "start_time": start_time,
            }
            if end_time:
                payload["end_time"] = end_time
            elif duration:
                payload["duration"] = duration
            return payload

        return None

    def _infer_tool_call_from_prompt(self, user_prompt: str) -> Optional[ToolCall]:
        prompt = user_prompt.strip()
        lowered = prompt.lower()

        if looks_like_add_calendar(lowered):
            arguments = self._normalize_arguments_for_tool("add_calendar_event", {}, prompt)
            if arguments is not None:
                return self._tool_call("add_calendar_event", arguments)
            return None

        if looks_like_show_events(lowered):
            arguments = self._normalize_arguments_for_tool(
                "show_upcoming_events", {}, prompt
            )
            if arguments is not None:
                return self._tool_call("show_upcoming_events", arguments)
            return None

        action = detect_action(prompt)
        if action is None:
            return None

        has_pomodoro = has_pomodoro_context(lowered)
        has_timer = has_timer_context(lowered)
        duration = extract_duration_from_prompt(prompt)

        if has_pomodoro:
            name = INTENT_TO_POMODORO_TOOL[action]
            arguments = self._normalize_arguments_for_tool(name, {}, prompt)
            if arguments is None:
                return None
            return self._tool_call(name, arguments)

        if has_timer or duration is not None:
            name = INTENT_TO_TIMER_TOOL[action]
            seed_args = {"duration": duration} if duration and name == "start_timer" else {}
            arguments = self._normalize_arguments_for_tool(name, seed_args, prompt)
            if arguments is None:
                return None
            return self._tool_call(name, arguments)

        return None

    def _normalize_assistant_text(
        self, text: str, tool_call: Optional[ToolCall]
    ) -> str:
        return normalize_assistant_text(text, tool_call)

    @staticmethod
    def _extract_datetime_literal(
        prompt: str,
        *,
        now_fn: Optional[Callable[[], datetime]] = None,
    ) -> Optional[str]:
        effective_now_fn = now_fn or (lambda: datetime.now().astimezone())
        return extract_datetime_literal(
            prompt,
            now_fn=effective_now_fn,
        )

    def _fallback_assistant_text(self, tool_call: Optional[ToolCall]) -> str:
        return fallback_assistant_text(tool_call)

    @staticmethod
    def _tool_call(name: str, arguments: dict[str, Any]) -> ToolCall:
        return {
            "name": cast(ToolName, name),
            "arguments": arguments,
        }
