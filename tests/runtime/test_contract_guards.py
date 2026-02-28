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


if __name__ == "__main__":
    unittest.main()
