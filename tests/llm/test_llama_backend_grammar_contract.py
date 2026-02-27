import unittest

from contracts.tool_contract import (
    TOOL_ADD_CALENDAR_EVENT,
    TOOL_SHOW_UPCOMING_EVENTS,
    TOOL_START_POMODORO,
    TOOL_START_TIMER,
    TOOL_NAME_ORDER,
    TOOLS_WITHOUT_ARGUMENTS,
)
from llm.llama_backend import build_gbnf_schema


class LlamaBackendGrammarContractTests(unittest.TestCase):
    def test_schema_injects_runtime_tool_names(self) -> None:
        schema = build_gbnf_schema()
        self.assertIn(TOOL_START_TIMER, schema)
        self.assertIn(TOOL_START_POMODORO, schema)
        self.assertIn(TOOL_SHOW_UPCOMING_EVENTS, schema)
        self.assertIn(TOOL_ADD_CALENDAR_EVENT, schema)

        for tool_name in TOOL_NAME_ORDER:
            if tool_name in TOOLS_WITHOUT_ARGUMENTS:
                self.assertIn(tool_name, schema)

        self.assertNotIn("__TOOL_START_TIMER__", schema)
        self.assertNotIn("__TOOL_START_POMODORO__", schema)
        self.assertNotIn("__TOOL_SHOW_UPCOMING_EVENTS__", schema)
        self.assertNotIn("__TOOL_ADD_CALENDAR_EVENT__", schema)
        self.assertNotIn("__EMPTY_TOOL_NAMES__", schema)


if __name__ == "__main__":
    unittest.main()
