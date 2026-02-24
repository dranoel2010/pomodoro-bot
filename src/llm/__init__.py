"""Public exports for the local LLM integration module."""

from .config import LLMConfig
from .factory import create_llm_client
from .model_store import HFModelSpec, ensure_model_downloaded
from .service import PomodoroAssistantLLM
from .types import EnvironmentContext, StructuredResponse, ToolCall, ToolName

__all__ = [
    "EnvironmentContext",
    "HFModelSpec",
    "LLMConfig",
    "PomodoroAssistantLLM",
    "StructuredResponse",
    "ToolCall",
    "ToolName",
    "create_llm_client",
    "ensure_model_downloaded",
]
