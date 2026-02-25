"""Deterministic fast-path routing for explicit tool commands."""

from __future__ import annotations

from .parser import ResponseParser
from .types import StructuredResponse


def maybe_fast_path_response(user_prompt: str) -> StructuredResponse | None:
    """Return a deterministic response for explicit tool intents.

    The fast path bypasses llama.cpp entirely and uses existing parser intent
    rules. This preserves behavior for command-like utterances while reducing
    CPU usage and response latency.
    """
    prompt = user_prompt.strip()
    if not prompt:
        return None

    parser = ResponseParser()
    tool_call = parser._infer_tool_call_from_prompt(prompt)
    if tool_call is None:
        return None

    return {
        "assistant_text": parser._fallback_assistant_text(tool_call),
        "tool_call": tool_call,
    }
