from __future__ import annotations

import logging
import sys
import types
import unittest
from pathlib import Path

_SRC_DIR = Path(__file__).resolve().parents[2] / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from pomodoro import PomodoroTimer

# Inject runtime package without triggering __init__.py (avoids pulling in RuntimeEngine)
_RUNTIME_DIR = _SRC_DIR / "runtime"
if "runtime" not in sys.modules:
    _pkg = types.ModuleType("runtime")
    _pkg.__path__ = [str(_RUNTIME_DIR)]  # type: ignore[attr-defined]
    sys.modules["runtime"] = _pkg

from runtime.tools.dispatch import RuntimeToolDispatcher
from runtime.ui import RuntimeUIPublisher

# Inject llm package for fast-path tests
_LLM_DIR = _SRC_DIR / "llm"
if "llm" not in sys.modules:
    _llm_pkg = types.ModuleType("llm")
    _llm_pkg.__path__ = [str(_LLM_DIR)]  # type: ignore[attr-defined]
    sys.modules["llm"] = _llm_pkg

from llm.fast_path import maybe_fast_path_response


class _UIServerStub:
    def __init__(self):
        self.events: list[tuple[str, dict[str, object]]] = []
        self.states: list[tuple[str, str | None, dict[str, object]]] = []

    def publish(self, event_type: str, **payload):
        self.events.append((event_type, payload))

    def publish_state(self, state: str, *, message=None, **payload):
        self.states.append((state, message, payload))


class _OracleSettingsStub:
    google_calendar_max_results = 3


class _AppConfigStub:
    oracle = _OracleSettingsStub()


class TellJokeDispatchTests(unittest.TestCase):
    """Verify tell_joke tool dispatch via RuntimeToolDispatcher."""

    def setUp(self) -> None:
        self.ui_server = _UIServerStub()
        self.ui = RuntimeUIPublisher(self.ui_server)
        self.dispatcher = RuntimeToolDispatcher(
            logger=logging.getLogger("test"),
            app_config=_AppConfigStub(),
            oracle_service=None,
            pomodoro_timer=PomodoroTimer(duration_seconds=25 * 60),
            countdown_timer=PomodoroTimer(duration_seconds=10 * 60),
            ui=self.ui,
        )

    def test_tell_joke_returns_non_empty_string(self) -> None:
        result = self.dispatcher.handle_tool_call(
            {"name": "tell_joke", "arguments": {}}, ""
        )
        self.assertIsInstance(result, str)
        self.assertTrue(len(result) > 10)
        self.assertIn("Geister", result, "Response must be the hardcoded German ghost joke")

    def test_tell_joke_response_is_deterministic(self) -> None:
        r1 = self.dispatcher.handle_tool_call({"name": "tell_joke", "arguments": {}}, "")
        r2 = self.dispatcher.handle_tool_call({"name": "tell_joke", "arguments": {}}, "anything")
        self.assertEqual(r1, r2)

    def test_tell_joke_ignores_assistant_text(self) -> None:
        result = self.dispatcher.handle_tool_call(
            {"name": "tell_joke", "arguments": {}}, "some LLM text"
        )
        # The handler ignores assistant_text — result should be the hardcoded joke
        self.assertNotEqual("some LLM text", result)


class ToolContractGuardTests(unittest.TestCase):
    """Verify TOOL_TELL_JOKE contract compliance."""

    def test_tool_tell_joke_in_tool_name_order(self) -> None:
        from contracts.tool_contract import TOOL_NAME_ORDER, TOOL_TELL_JOKE
        self.assertIn(TOOL_TELL_JOKE, TOOL_NAME_ORDER)

    def test_tool_tell_joke_in_tools_without_arguments(self) -> None:
        from contracts.tool_contract import TOOLS_WITHOUT_ARGUMENTS, TOOL_TELL_JOKE
        self.assertIn(
            TOOL_TELL_JOKE,
            TOOLS_WITHOUT_ARGUMENTS,
            "TOOL_TELL_JOKE must be in TOOLS_WITHOUT_ARGUMENTS — omitting breaks GBNF grammar",
        )

    def test_tool_tell_joke_in_pure_llm_tool_names(self) -> None:
        from contracts.tool_contract import PURE_LLM_TOOL_NAMES, TOOL_TELL_JOKE
        self.assertIn(TOOL_TELL_JOKE, PURE_LLM_TOOL_NAMES)

    def test_tool_tell_joke_not_in_timer_tool_names(self) -> None:
        from contracts.tool_contract import TIMER_TOOL_NAMES, TOOL_TELL_JOKE
        self.assertNotIn(TOOL_TELL_JOKE, TIMER_TOOL_NAMES)

    def test_tool_tell_joke_not_in_pomodoro_tool_names(self) -> None:
        from contracts.tool_contract import POMODORO_TOOL_NAMES, TOOL_TELL_JOKE
        self.assertNotIn(TOOL_TELL_JOKE, POMODORO_TOOL_NAMES)

    def test_tool_tell_joke_not_in_calendar_tool_names(self) -> None:
        from contracts.tool_contract import CALENDAR_TOOL_NAMES, TOOL_TELL_JOKE
        self.assertNotIn(TOOL_TELL_JOKE, CALENDAR_TOOL_NAMES)


class FastPathTellJokeTests(unittest.TestCase):
    """Tests for fast-path routing of tell_joke."""

    def test_fast_path_routes_erzaehl_mir_einen_witz(self) -> None:
        result = maybe_fast_path_response("Erzähl mir einen Witz")
        self.assertIsNotNone(result)
        if result is None:
            self.fail("Expected fast-path to route joke request")
        tool_call = result["tool_call"]
        self.assertIsNotNone(tool_call)
        if tool_call is None:
            self.fail("Expected tool_call")
        self.assertEqual("tell_joke", tool_call["name"])
        self.assertEqual({}, tool_call["arguments"])

    def test_fast_path_routes_witz_keyword(self) -> None:
        result = maybe_fast_path_response("Hast du einen guten Witz für mich?")
        self.assertIsNotNone(result)
        if result is None:
            self.fail("Expected fast-path to route joke request")
        tool_call = result["tool_call"]
        self.assertIsNotNone(tool_call)
        if tool_call is None:
            self.fail("Expected tool_call")
        self.assertEqual("tell_joke", tool_call["name"])

    def test_fast_path_timer_not_misrouted_as_tell_joke(self) -> None:
        result = maybe_fast_path_response("Starte einen Timer für 10 Minuten")
        self.assertIsNotNone(result, "Timer command must be detected by fast-path")
        tool_call = result["tool_call"] if result else None
        self.assertIsNotNone(tool_call)
        self.assertEqual("start_timer", tool_call["name"])

    def test_fast_path_tell_joke_has_no_arguments(self) -> None:
        result = maybe_fast_path_response("Erzähl mir einen Witz")
        self.assertIsNotNone(result)
        tool_call = result["tool_call"] if result else None
        self.assertIsNotNone(tool_call)
        if tool_call:
            self.assertEqual({}, tool_call["arguments"])


if __name__ == "__main__":
    unittest.main()
