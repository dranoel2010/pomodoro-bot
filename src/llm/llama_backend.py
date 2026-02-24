"""llama.cpp backend wrapper with constrained JSON grammar output."""

from dataclasses import dataclass
from typing import Any

from contracts.tool_contract import tool_name_gbnf_alternatives

from .config import LLMConfig


GBNF_SCHEMA_TEMPLATE = r"""
root ::= "{" ws "\"assistant_text\"" ws ":" ws string ws "," ws "\"tool_call\"" ws ":" ws toolcall ws "}"
toolcall ::= "null" | toolobj
toolobj ::= "{" ws "\"name\"" ws ":" ws toolname ws "," ws "\"arguments\"" ws ":" ws argobj ws "}"
toolname ::= __TOOLNAME_ALTERNATIVES__
argobj ::= "{" ws "}" | "{" ws kv-list ws "}"
kv-list ::= kv-pair | kv-pair ws "," ws kv-list
kv-pair ::= string ws ":" ws value
value ::= string | number | "null"
string ::= "\"" (char)* "\""
char ::= [^"\\] | escape
escape ::= "\\" (["\\/bfnrt] | "u" hex hex hex hex)
hex ::= [0-9a-fA-F]
number ::= int frac? exp?
int ::= "-"? ([0-9] | [1-9] (digit)*)
frac ::= "." (digit)+
exp ::= [eE] [-+]? (digit)+
digit ::= [0-9]
ws ::= ([ \t\n\r])*
""".strip()


@dataclass(frozen=True, slots=True)
class CompletionUsage:
    finish_reason: str | None
    prompt_tokens: int | None
    completion_tokens: int | None
    total_tokens: int | None
    derived_completion_tokens: int | None
    accounting_consistent: bool | None
    accounting_delta: int | None
    raw_usage: dict[str, object] | None


def build_gbnf_schema() -> str:
    """Build the runtime GBNF schema with current canonical tool names."""
    return GBNF_SCHEMA_TEMPLATE.replace(
        "__TOOLNAME_ALTERNATIVES__",
        tool_name_gbnf_alternatives(),
    )


class LlamaBackend:
    """Thin wrapper around llama.cpp chat completion with grammar constraints."""
    def __init__(self, config: LLMConfig):
        from llama_cpp import Llama, LlamaGrammar

        self._llm = Llama(
            model_path=config.model_path,
            n_threads=config.n_threads,
            n_ctx=config.n_ctx,
            n_batch=config.n_batch,
            verbose=config.verbose,
        )
        self._grammar = LlamaGrammar.from_string(build_gbnf_schema())
        self._config = config
        self._last_finish_reason: str | None = None
        self._last_prompt_tokens: int | None = None
        self._last_completion_tokens: int | None = None
        self._last_total_tokens: int | None = None
        self._last_usage: CompletionUsage | None = None

    def complete(self, messages: list[dict[str, str]], max_tokens: int) -> str:
        response: dict[str, Any] = self._llm.create_chat_completion(
            messages=messages,
            temperature=self._config.temperature,
            top_p=self._config.top_p,
            repeat_penalty=self._config.repeat_penalty,
            max_tokens=max_tokens,
            grammar=self._grammar,
        )
        choice = response["choices"][0]
        finish_reason = choice.get("finish_reason")
        self._last_finish_reason = (
            str(finish_reason) if finish_reason is not None else None
        )

        usage = response.get("usage")
        if isinstance(usage, dict):
            prompt_tokens = _as_int(usage.get("prompt_tokens"))
            completion_tokens = _as_int(usage.get("completion_tokens"))
            total_tokens = _as_int(usage.get("total_tokens"))
            usage_raw = {
                key: value
                for key, value in usage.items()
                if isinstance(key, str)
            }
        else:
            prompt_tokens = None
            completion_tokens = None
            total_tokens = None
            usage_raw = None

        self._last_prompt_tokens = prompt_tokens
        self._last_completion_tokens = completion_tokens
        self._last_total_tokens = total_tokens
        self._last_usage = _build_completion_usage(
            finish_reason=self._last_finish_reason,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            raw_usage=usage_raw,
        )

        return choice["message"]["content"]

    @property
    def last_finish_reason(self) -> str | None:
        return self._last_finish_reason

    @property
    def last_prompt_tokens(self) -> int | None:
        return self._last_prompt_tokens

    @property
    def last_completion_tokens(self) -> int | None:
        return self._last_completion_tokens

    @property
    def last_total_tokens(self) -> int | None:
        return self._last_total_tokens

    @property
    def last_usage(self) -> CompletionUsage | None:
        return self._last_usage


def _build_completion_usage(
    *,
    finish_reason: str | None,
    prompt_tokens: int | None,
    completion_tokens: int | None,
    total_tokens: int | None,
    raw_usage: dict[str, object] | None,
) -> CompletionUsage:
    derived_completion_tokens: int | None = None
    if (
        isinstance(total_tokens, int)
        and isinstance(prompt_tokens, int)
    ):
        derived_completion_tokens = total_tokens - prompt_tokens

    accounting_consistent: bool | None = None
    accounting_delta: int | None = None
    if (
        isinstance(total_tokens, int)
        and isinstance(prompt_tokens, int)
        and isinstance(completion_tokens, int)
    ):
        accounting_delta = total_tokens - (prompt_tokens + completion_tokens)
        accounting_consistent = accounting_delta == 0

    return CompletionUsage(
        finish_reason=finish_reason,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        derived_completion_tokens=derived_completion_tokens,
        accounting_consistent=accounting_consistent,
        accounting_delta=accounting_delta,
        raw_usage=raw_usage,
    )


def _as_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None
