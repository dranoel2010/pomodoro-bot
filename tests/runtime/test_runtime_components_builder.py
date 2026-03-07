from __future__ import annotations

import logging
import sys
import types
import unittest
from datetime import datetime, timezone
from pathlib import Path

_SRC_DIR = Path(__file__).resolve().parents[2] / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

# Inject runtime package without triggering __init__.py (avoids pulling in RuntimeEngine).
_RUNTIME_DIR = _SRC_DIR / "runtime"
if "runtime" not in sys.modules:
    _pkg = types.ModuleType("runtime")
    _pkg.__path__ = [str(_RUNTIME_DIR)]  # type: ignore[attr-defined]
    sys.modules["runtime"] = _pkg

# Inject llm package to avoid llm/__init__.py startup dependencies.
_LLM_DIR = _SRC_DIR / "llm"
if "llm" not in sys.modules:
    _llm_pkg = types.ModuleType("llm")
    _llm_pkg.__path__ = [str(_LLM_DIR)]  # type: ignore[attr-defined]
    sys.modules["llm"] = _llm_pkg

from runtime.components import RuntimeComponents, _build_runtime_components
from stt.events import WakeWordDetectedEvent


class _OracleSettingsStub:
    google_calendar_max_results = 3


class _AppConfigStub:
    oracle = _OracleSettingsStub()


class RuntimeComponentsBuilderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.components = _build_runtime_components(
            logger=logging.getLogger("test-runtime-components"),
            app_config=_AppConfigStub(),
            oracle_service=None,
            ui_server=None,
        )

    def tearDown(self) -> None:
        self.components.utterance_executor.shutdown(wait=False, cancel_futures=True)

    def test_builder_returns_runtime_components_with_collaborators(self) -> None:
        self.assertIsInstance(self.components, RuntimeComponents)
        self.assertIsNotNone(self.components.ui)
        self.assertIsNotNone(self.components.pomodoro_timer)
        self.assertIsNotNone(self.components.countdown_timer)
        self.assertIsNotNone(self.components.dispatcher)
        self.assertIsNotNone(self.components.event_queue)
        self.assertIsNotNone(self.components.publisher)
        self.assertIsNotNone(self.components.pomodoro_cycle)

    def test_publisher_pushes_events_to_returned_queue(self) -> None:
        event = WakeWordDetectedEvent(occurred_at=datetime.now(timezone.utc))

        self.components.publisher.publish(event)

        queued_event = self.components.event_queue.get_nowait()
        self.assertIs(queued_event, event)

    def test_utterance_executor_uses_single_worker(self) -> None:
        executor = self.components.utterance_executor
        self.assertEqual(1, getattr(executor, "_max_workers", None))


if __name__ == "__main__":
    unittest.main()
