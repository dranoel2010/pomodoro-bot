"""LLM package exports."""

__all__ = ["LLMConfig", "PomodoroAssistantLLM"]


def __getattr__(name: str):
    if name == "LLMConfig":
        from .config import LLMConfig

        return LLMConfig
    if name == "PomodoroAssistantLLM":
        from .service import PomodoroAssistantLLM

        return PomodoroAssistantLLM
    raise AttributeError(name)
