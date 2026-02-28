"""Runtime worker implementations."""

from __future__ import annotations

from importlib import import_module

__all__ = [
    "STTWorker",
    "LLMWorker",
    "TTSWorker",
    "create_stt_worker",
    "create_llm_worker",
    "create_tts_worker",
]

_EXPORTS = {
    "STTWorker": ("runtime.workers.stt", "STTWorker"),
    "LLMWorker": ("runtime.workers.llm", "LLMWorker"),
    "TTSWorker": ("runtime.workers.tts", "TTSWorker"),
    "create_stt_worker": ("runtime.workers.stt", "create_stt_worker"),
    "create_llm_worker": ("runtime.workers.llm", "create_llm_worker"),
    "create_tts_worker": ("runtime.workers.tts", "create_tts_worker"),
}


def __getattr__(name: str):
    if name not in _EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    module_name, attribute_name = _EXPORTS[name]
    module = import_module(module_name)
    value = getattr(module, attribute_name)
    globals()[name] = value
    return value
