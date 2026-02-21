import tempfile
import sys
import types
import unittest
from pathlib import Path

# Import server.static_files without executing src/server/__init__.py.
_SERVER_DIR = Path(__file__).resolve().parents[2] / "src" / "server"
if "server" not in sys.modules:
    _pkg = types.ModuleType("server")
    _pkg.__path__ = [str(_SERVER_DIR)]  # type: ignore[attr-defined]
    sys.modules["server"] = _pkg

from server.static_files import guess_content_type, resolve_static_file


class ServerStaticFilesTests(unittest.TestCase):
    def test_resolve_static_file_returns_file_inside_ui_root(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            ui_root = Path(temp_dir)
            app_js = ui_root / "assets" / "app.js"
            app_js.parent.mkdir(parents=True, exist_ok=True)
            app_js.write_text("console.log('ok');", encoding="utf-8")

            resolved = resolve_static_file(ui_root, "/assets/app.js")
            self.assertEqual(app_js.resolve(), resolved)

    def test_resolve_static_file_rejects_path_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            ui_root = root / "ui"
            ui_root.mkdir(parents=True, exist_ok=True)
            outside = root / "secret.txt"
            outside.write_text("x", encoding="utf-8")

            resolved = resolve_static_file(ui_root, "/../secret.txt")
            self.assertIsNone(resolved)

    def test_resolve_static_file_rejects_root_or_missing_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            ui_root = Path(temp_dir)
            self.assertIsNone(resolve_static_file(ui_root, "/"))
            self.assertIsNone(resolve_static_file(ui_root, "/missing.txt"))

    def test_guess_content_type_sets_charset_for_text(self) -> None:
        self.assertEqual("text/css; charset=utf-8", guess_content_type(Path("styles.css")))
        js_type = guess_content_type(Path("app.js"))
        self.assertTrue(js_type.endswith("; charset=utf-8"))
        self.assertIn("javascript", js_type)

    def test_guess_content_type_falls_back_for_unknown_extensions(self) -> None:
        self.assertEqual(
            "application/octet-stream",
            guess_content_type(Path("blob.unknownbinaryextension")),
        )


if __name__ == "__main__":
    unittest.main()
