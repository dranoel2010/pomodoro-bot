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


if __name__ == "__main__":
    unittest.main()
