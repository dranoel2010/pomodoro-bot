import ast
import unittest
from pathlib import Path


_MAX_PARAMETERS = 4
_RUNTIME_FILES = (
    "loop.py",
    "utterance.py",
    "ticks.py",
)


def _parameter_count(node: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    positional = list(node.args.posonlyargs) + list(node.args.args)
    keyword_only = list(node.args.kwonlyargs)
    params = positional + keyword_only

    if params and params[0].arg == "self":
        params = params[1:]

    count = len(params)
    if node.args.vararg is not None:
        count += 1
    if node.args.kwarg is not None:
        count += 1
    return count


class RuntimeArityTests(unittest.TestCase):
    def test_runtime_entrypoints_have_bounded_parameter_count(self) -> None:
        runtime_dir = Path(__file__).resolve().parents[2] / "src" / "runtime"
        violations: list[str] = []

        for filename in _RUNTIME_FILES:
            source_path = runtime_dir / filename
            module = ast.parse(source_path.read_text(encoding="utf-8"), filename=filename)
            for node in ast.walk(module):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue

                count = _parameter_count(node)
                if count > _MAX_PARAMETERS:
                    violations.append(
                        f"{filename}:{node.lineno} {node.name} has {count} parameters"
                    )

        self.assertEqual([], violations)


if __name__ == "__main__":
    unittest.main()
