import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

# Import llm modules without executing src/llm/__init__.py.
_LLM_DIR = Path(__file__).resolve().parents[2] / "src" / "llm"
if "llm" not in sys.modules:
    _pkg = types.ModuleType("llm")
    _pkg.__path__ = [str(_LLM_DIR)]  # type: ignore[attr-defined]
    sys.modules["llm"] = _pkg

from llm.model_store import HFModelSpec, ensure_model_downloaded


class ModelStoreSymlinkReplacementTests(unittest.TestCase):
    def test_existing_symlink_target_is_replaced_with_regular_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            models_dir = root / "models"
            models_dir.mkdir(parents=True, exist_ok=True)

            target = models_dir / "tiny.gguf"
            downloaded_blob = root / "blob.gguf"
            downloaded_blob.write_bytes(b"GGUFtest")
            target.symlink_to(downloaded_blob)

            spec = HFModelSpec(repo_id="fake/repo", filename=target.name)

            with patch("llm.model_store.hf_hub_download", return_value=str(downloaded_blob)):
                resolved = ensure_model_downloaded(
                    spec,
                    models_dir=models_dir,
                    validate_gguf=True,
                )

            self.assertEqual(target, resolved)
            self.assertTrue(resolved.is_file())
            self.assertFalse(resolved.is_symlink())
            self.assertEqual(b"GGUF", resolved.read_bytes()[:4])

    def test_downloaded_symlink_source_is_dereferenced_before_install(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            models_dir = root / "models"
            models_dir.mkdir(parents=True, exist_ok=True)

            target = models_dir / "tiny.gguf"
            downloaded_blob = root / "blob.gguf"
            downloaded_blob.write_bytes(b"GGUFtest")
            snapshot_file = root / "snapshot.gguf"
            snapshot_file.symlink_to(downloaded_blob)

            spec = HFModelSpec(repo_id="fake/repo", filename=target.name)

            def _hardlink_to(self: Path, source: Path) -> None:
                # Simulate Linux behavior where hard-linking a symlink links the symlink inode.
                if source.is_symlink():
                    self.symlink_to(os.readlink(source))
                    return
                os.link(source, self)

            with (
                patch("llm.model_store.hf_hub_download", return_value=str(snapshot_file)),
                patch("llm.model_store.Path.hardlink_to", new=_hardlink_to),
            ):
                resolved = ensure_model_downloaded(
                    spec,
                    models_dir=models_dir,
                    validate_gguf=True,
                )

            self.assertEqual(target, resolved)
            self.assertTrue(resolved.is_file())
            self.assertFalse(resolved.is_symlink())
            self.assertEqual(b"GGUF", resolved.read_bytes()[:4])


if __name__ == "__main__":
    unittest.main()
