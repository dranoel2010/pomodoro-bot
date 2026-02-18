import json
import re
from typing import Any, Optional

from .types import StructuredResponse


class ResponseParser:
    def __init__(self):
        self._last_session: Optional[str] = None

    def parse(self, content: str, user_prompt: str) -> StructuredResponse:
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            return {
                "assistant_text": "Sorry - I could not format that correctly. Could you rephrase?",
                "tool_call": None,
            }

        try:
            return self._validate_and_normalize(parsed, user_prompt)
        except Exception:
            return {
                "assistant_text": "I'm not fully sure what timer action you want. What should I do (start, pause, stop, or reset), and what session name?",
                "tool_call": None,
            }

    def _sanitize_session(self, session: str) -> str:
        text = session.strip()
        text = re.sub(r"\s+", " ", text)
        text = text[:60].strip()
        return text or "Focus"

    def _default_session(self, user_prompt: str) -> str:
        prompt = user_prompt.strip().lower()
        match = re.search(r"\b(?:for|on)\s+([a-z0-9][\w\s\-]{0,50})", prompt, re.I)
        if match:
            return self._sanitize_session(match.group(1))
        if self._last_session:
            return self._last_session
        return "Focus"

    def _validate_and_normalize(
        self, obj: dict[str, Any], user_prompt: str
    ) -> StructuredResponse:
        if not isinstance(obj, dict):
            raise ValueError("Model output is not a JSON object.")

        if set(obj.keys()) != {"assistant_text", "tool_call"}:
            raise ValueError(f"Unexpected keys: {set(obj.keys())}")

        assistant_text = obj["assistant_text"]
        tool_call = obj["tool_call"]
        if not isinstance(assistant_text, str):
            raise ValueError("assistant_text must be a string.")

        if tool_call is None:
            return {"assistant_text": assistant_text.strip(), "tool_call": None}

        if not isinstance(tool_call, dict) or set(tool_call.keys()) != {
            "name",
            "arguments",
        }:
            raise ValueError("Invalid tool_call object.")

        name = tool_call["name"]
        if name not in ("timer_start", "timer_pause", "timer_stop", "timer_reset"):
            raise ValueError(f"Invalid tool name: {name}")

        args = tool_call["arguments"]
        if not isinstance(args, dict):
            raise ValueError("tool_call.arguments must be an object.")

        session = args.get("session")
        if not isinstance(session, str) or not session.strip():
            session = self._default_session(user_prompt)
        session = self._sanitize_session(session)

        self._last_session = session
        return {
            "assistant_text": assistant_text.strip(),
            "tool_call": {
                "name": name,
                "arguments": {"session": session},
            },
        }
