import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

# Import stt modules without executing src/stt/__init__.py.
_STT_DIR = Path(__file__).resolve().parents[2] / "src" / "stt"
if "stt" not in sys.modules:
    _pkg = types.ModuleType("stt")
    _pkg.__path__ = [str(_STT_DIR)]  # type: ignore[attr-defined]
    sys.modules["stt"] = _pkg

from stt.stt import FasterWhisperSTT, StreamingFasterWhisperSTT


class _WhisperModelStub:
    calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def __init__(self, *args, **kwargs):
        type(self).calls.append((args, kwargs))


class STTDownloadRootTests(unittest.TestCase):
    def setUp(self) -> None:
        _WhisperModelStub.calls.clear()

    def test_default_download_root_materializes_local_models_directory(self) -> None:
        created = False
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path.cwd()
            os.chdir(tmp)
            try:
                with patch("stt.stt.WhisperModel", _WhisperModelStub):
                    FasterWhisperSTT(model_size="tiny")
                created = (Path(tmp) / "models" / "stt").is_dir()
            finally:
                os.chdir(cwd)

        self.assertTrue(_WhisperModelStub.calls)
        _, kwargs = _WhisperModelStub.calls[-1]
        self.assertEqual(str(Path("models") / "stt"), kwargs["download_root"])
        self.assertTrue(created)

    def test_streaming_variant_forwards_explicit_download_root(self) -> None:
        created = False
        with tempfile.TemporaryDirectory() as tmp:
            explicit_root = Path(tmp) / "custom-models"
            with patch("stt.stt.WhisperModel", _WhisperModelStub):
                StreamingFasterWhisperSTT(model_size="tiny", download_root=str(explicit_root))
            created = explicit_root.is_dir()

        self.assertTrue(_WhisperModelStub.calls)
        _, kwargs = _WhisperModelStub.calls[-1]
        self.assertEqual(str(explicit_root), kwargs["download_root"])
        self.assertTrue(created)


if __name__ == "__main__":
    unittest.main()
