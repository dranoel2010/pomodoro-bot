import unittest

from tool_contract import (
    CALENDAR_TOOL_NAMES,
    INTENT_TO_POMODORO_TOOL,
    INTENT_TO_TIMER_TOOL,
    POMODORO_TOOL_TO_RUNTIME_ACTION,
    TIMER_TOOL_TO_RUNTIME_ACTION,
    TOOL_NAME_ORDER,
    TOOL_NAMES,
    tool_name_gbnf_alternatives,
    tool_names_one_of_csv,
)


class ToolContractConsistencyTests(unittest.TestCase):
    def test_tool_name_order_has_no_duplicates(self) -> None:
        self.assertEqual(len(TOOL_NAME_ORDER), len(set(TOOL_NAME_ORDER)))

    def test_runtime_dispatch_and_calendar_cover_all_tools(self) -> None:
        covered = (
            set(TIMER_TOOL_TO_RUNTIME_ACTION)
            | set(POMODORO_TOOL_TO_RUNTIME_ACTION)
            | set(CALENDAR_TOOL_NAMES)
        )
        self.assertEqual(set(TOOL_NAMES), covered)

    def test_intent_mappings_resolve_to_known_tools(self) -> None:
        for tool_name in INTENT_TO_TIMER_TOOL.values():
            self.assertIn(tool_name, TOOL_NAMES)
            self.assertIn(tool_name, TIMER_TOOL_TO_RUNTIME_ACTION)
        for tool_name in INTENT_TO_POMODORO_TOOL.values():
            self.assertIn(tool_name, TOOL_NAMES)
            self.assertIn(tool_name, POMODORO_TOOL_TO_RUNTIME_ACTION)

    def test_prompt_and_grammar_helpers_cover_all_tools(self) -> None:
        csv_value = tool_names_one_of_csv()
        grammar_value = tool_name_gbnf_alternatives()
        for tool_name in TOOL_NAME_ORDER:
            self.assertIn(tool_name, csv_value)
            self.assertIn(f'"\\\"{tool_name}\\\""', grammar_value)


if __name__ == "__main__":
    unittest.main()
