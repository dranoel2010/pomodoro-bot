"""Runtime engine exports."""

__all__ = ["PipecatRuntimeEngine"]


def __getattr__(name: str):
    if name == "PipecatRuntimeEngine":
        from .pipecat_engine import PipecatRuntimeEngine

        return PipecatRuntimeEngine
    raise AttributeError(name)
