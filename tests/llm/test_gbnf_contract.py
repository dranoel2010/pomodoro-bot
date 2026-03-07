from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path

# Import llm modules without executing src/llm/__init__.py.
_LLM_DIR = Path(__file__).resolve().parents[2] / "src" / "llm"
if "llm" not in sys.modules:
    _pkg = types.ModuleType("llm")
    _pkg.__path__ = [str(_LLM_DIR)]  # type: ignore[attr-defined]
    sys.modules["llm"] = _pkg

from contracts.tool_contract import TOOL_NAME_ORDER
from llm.llama_backend import build_gbnf_schema


class GBNFContractTests(unittest.TestCase):
    def test_build_gbnf_schema_covers_all_canonical_tool_names(self) -> None:
        schema = build_gbnf_schema()
        for tool_name in TOOL_NAME_ORDER:
            self.assertIn(f'\\"{tool_name}\\"', schema)

    def test_build_gbnf_schema_contains_no_unresolved_placeholders(self) -> None:
        schema = build_gbnf_schema()
        self.assertNotIn("__TOOLNAME_ALTERNATIVES__", schema)


if __name__ == "__main__":
    unittest.main()
