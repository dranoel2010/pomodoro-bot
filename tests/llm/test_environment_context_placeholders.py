import sys
import types
import unittest
from pathlib import Path

# Import llm.types without executing src/llm/__init__.py.
_LLM_DIR = Path(__file__).resolve().parents[2] / "src" / "llm"
if "llm" not in sys.modules:
    _pkg = types.ModuleType("llm")
    _pkg.__path__ = [str(_LLM_DIR)]  # type: ignore[attr-defined]
    sys.modules["llm"] = _pkg

from llm.types import EnvironmentContext


class EnvironmentContextPlaceholderTests(unittest.TestCase):
    def test_next_appointment_uses_natural_language_window(self) -> None:
        ctx = EnvironmentContext(
            now_local="2026-02-21T10:00:00+00:00",
            upcoming_events=[
                {
                    "summary": "Leotreffen",
                    "start": "2026-02-21T12:30:00+00:00",
                    "end": "2026-02-21T13:00:00+00:00",
                }
            ],
        )

        placeholders = ctx.to_prompt_placeholders()
        self.assertEqual(
            "Leotreffen (heute von 12:30 bis 13:00)",
            placeholders["next_appointment"],
        )

    def test_next_appointment_uses_natural_language_point(self) -> None:
        ctx = EnvironmentContext(
            now_local="2026-02-21T10:00:00+00:00",
            upcoming_events=[
                {
                    "summary": "Standup",
                    "start": "2026-02-22T09:15:00+00:00",
                }
            ],
        )

        placeholders = ctx.to_prompt_placeholders()
        self.assertEqual(
            "Standup (morgen um 09:15)",
            placeholders["next_appointment"],
        )


if __name__ == "__main__":
    unittest.main()
