from __future__ import annotations

import re
import unittest
from pathlib import Path


_ROOT = Path(__file__).resolve().parents[2]
_WORKER_FILES = (
    _ROOT / "src" / "runtime" / "workers" / "llm.py",
    _ROOT / "src" / "runtime" / "workers" / "stt.py",
    _ROOT / "src" / "runtime" / "workers" / "tts.py",
)
_RUNTIME_SIGNATURE_FILES = (
    _ROOT / "src" / "runtime" / "utterance.py",
    _ROOT / "src" / "runtime" / "tools" / "dispatch.py",
    _ROOT / "src" / "runtime" / "tools" / "calendar.py",
    _ROOT / "src" / "runtime" / "ui.py",
)
_DISSOLVED_CONTRACT_FILES = (
    _ROOT / "src" / "runtime" / "contracts.py",
    _ROOT / "src" / "oracle" / "contracts.py",
)
_FORBIDDEN_CONTRACT_IMPORTS = (
    "runtime.contracts",
    "oracle.contracts",
)
_PACKAGES_WITH_DISSOLVED_CONTRACTS = (
    _ROOT / "src" / "runtime",
    _ROOT / "src" / "oracle",
)


class RuntimeContractGuards(unittest.TestCase):
    def test_worker_modules_do_not_use_mutable_process_instance_globals(self) -> None:
        for file_path in _WORKER_FILES:
            source = file_path.read_text(encoding="utf-8")
            self.assertNotRegex(source, r"\bglobal\s+_")
            self.assertIsNone(re.search(r"_\w+_INSTANCE", source))

    def test_runtime_signatures_do_not_use_dict_object_contracts(self) -> None:
        for file_path in _RUNTIME_SIGNATURE_FILES:
            source = file_path.read_text(encoding="utf-8")
            self.assertNotIn("dict[str, object]", source)


class ContractsConsolidationGuards(unittest.TestCase):
    def test_dissolved_contracts_modules_no_longer_exist(self) -> None:
        for path in _DISSOLVED_CONTRACT_FILES:
            self.assertFalse(
                path.exists(),
                msg=f"Dissolved contracts file still exists: {path.relative_to(_ROOT)}",
            )

    def test_no_source_file_imports_from_dissolved_contracts_modules(self) -> None:
        src_root = _ROOT / "src"
        for py_file in src_root.rglob("*.py"):
            source = py_file.read_text(encoding="utf-8")
            for forbidden in _FORBIDDEN_CONTRACT_IMPORTS:
                self.assertNotIn(
                    forbidden,
                    source,
                    msg=(
                        f"{py_file.relative_to(_ROOT)} still references dissolved "
                        f"module '{forbidden}'"
                    ),
                )

    def test_no_relative_import_from_dissolved_contracts_modules(self) -> None:
        for pkg_dir in _PACKAGES_WITH_DISSOLVED_CONTRACTS:
            for py_file in pkg_dir.rglob("*.py"):
                source = py_file.read_text(encoding="utf-8")
                self.assertNotIn(
                    "from .contracts import",
                    source,
                    msg=(
                        f"{py_file.relative_to(_ROOT)} uses relative import from "
                        f"dissolved .contracts module"
                    ),
                )


_LLM_FAST_PATH = _ROOT / "src" / "llm" / "fast_path.py"
_LLM_LLAMA_BACKEND = _ROOT / "src" / "llm" / "llama_backend.py"
_LLM_PARSER = _ROOT / "src" / "llm" / "parser.py"
_LLM_SERVICE = _ROOT / "src" / "llm" / "service.py"
_LLM_EXTRACTORS = _ROOT / "src" / "llm" / "parser_extractors.py"


class LlmModuleBoundaryGuards(unittest.TestCase):
    def test_fast_path_does_not_import_from_parser(self) -> None:
        source = _LLM_FAST_PATH.read_text(encoding="utf-8")
        self.assertNotIn(
            "from .parser import",
            source,
            msg="fast_path.py must not import from parser.py — violates module boundary",
        )
        self.assertNotIn(
            "from llm.parser import",
            source,
            msg="fast_path.py must not import from llm.parser — violates module boundary",
        )

    def test_llama_backend_does_not_contain_json_parsing(self) -> None:
        source = _LLM_LLAMA_BACKEND.read_text(encoding="utf-8")
        self.assertNotIn(
            "import json",
            source,
            msg="llama_backend.py must not contain JSON parsing — that belongs in parser.py",
        )
        self.assertNotRegex(
            source,
            r"from json import",
            msg="llama_backend.py must not import from json — that belongs in parser.py",
        )
        self.assertNotRegex(
            source,
            r"json\.loads|json\.dumps",
            msg="llama_backend.py must not use json.loads/dumps",
        )

    def test_parser_does_not_import_from_llama_cpp(self) -> None:
        source = _LLM_PARSER.read_text(encoding="utf-8")
        self.assertNotIn(
            "llama_cpp",
            source,
            msg="parser.py must not import from llama_cpp",
        )

    def test_llm_boundary_files_have_future_annotations(self) -> None:
        for path in (_LLM_FAST_PATH, _LLM_LLAMA_BACKEND, _LLM_PARSER, _LLM_SERVICE, _LLM_EXTRACTORS):
            source = path.read_text(encoding="utf-8")
            first_import = next(
                (line.strip() for line in source.splitlines() if line.strip().startswith(("import ", "from "))),
                None,
            )
            self.assertEqual(
                first_import,
                "from __future__ import annotations",
                msg=f"{path.name}: 'from __future__ import annotations' must be the first import statement",
            )


_DISPATCH_FILE = _ROOT / "src" / "runtime" / "tools" / "dispatch.py"


class DispatchPatternGuards(unittest.TestCase):
    def test_dispatch_uses_structural_pattern_matching(self) -> None:
        source = _DISPATCH_FILE.read_text(encoding="utf-8")
        self.assertIn(
            "match raw_name:",
            source,
            msg="dispatch.py must use 'match raw_name:' structural pattern matching in handle_tool_call",
        )

    def test_dispatch_does_not_use_if_chain_for_pomodoro_tools(self) -> None:
        source = _DISPATCH_FILE.read_text(encoding="utf-8")
        self.assertNotIn(
            "if raw_name in POMODORO_TOOL_TO_RUNTIME_ACTION",
            source,
            msg="dispatch.py must not use if-chain for pomodoro tool routing — use match/case",
        )

    def test_dispatch_does_not_use_if_chain_for_timer_tools(self) -> None:
        source = _DISPATCH_FILE.read_text(encoding="utf-8")
        self.assertNotIn(
            "if raw_name in TIMER_TOOL_TO_RUNTIME_ACTION",
            source,
            msg="dispatch.py must not use if-chain for timer tool routing — use match/case",
        )

    def test_dispatch_does_not_use_if_chain_for_calendar_tools(self) -> None:
        source = _DISPATCH_FILE.read_text(encoding="utf-8")
        self.assertNotIn(
            "if raw_name in CALENDAR_TOOL_NAMES",
            source,
            msg="dispatch.py must not use if-chain for calendar tool routing — use match/case",
        )


_TICKS_FILE = _ROOT / "src" / "runtime" / "ticks.py"


class PomodoroPhaseStateMappingGuards(unittest.TestCase):
    def test_phase_to_pomodoro_state_dicts_are_in_sync(self) -> None:
        """ticks.py and dispatch.py define identical _PHASE_TYPE_TO_POMODORO_STATE keys."""
        import re

        def _extract_mapping_keys(source: str) -> set[str]:
            match = re.search(
                r"_PHASE_TYPE_TO_POMODORO_STATE.*?\{(.*?)\}",
                source,
                re.DOTALL,
            )
            if not match:
                return set()
            return set(re.findall(r"PHASE_TYPE_\w+", match.group(1)))

        ticks_source = _TICKS_FILE.read_text(encoding="utf-8")
        dispatch_source = _DISPATCH_FILE.read_text(encoding="utf-8")
        ticks_keys = _extract_mapping_keys(ticks_source)
        dispatch_keys = _extract_mapping_keys(dispatch_source)
        self.assertTrue(ticks_keys, "_PHASE_TYPE_TO_POMODORO_STATE dict not found in ticks.py")
        self.assertEqual(
            ticks_keys,
            dispatch_keys,
            msg=(
                "ticks.py and dispatch.py _PHASE_TYPE_TO_POMODORO_STATE dicts "
                "must define the same PHASE_TYPE_* keys"
            ),
        )


if __name__ == "__main__":
    unittest.main()
