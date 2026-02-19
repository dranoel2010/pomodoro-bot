from typing import Any

from .config import LLMConfig


GBNF_SCHEMA = r"""
root ::= "{" ws "\"assistant_text\"" ws ":" ws string ws "," ws "\"tool_call\"" ws ":" ws toolcall ws "}"

toolcall ::= "null" | toolobj

toolobj ::= "{" ws "\"name\"" ws ":" ws toolname ws "," ws "\"arguments\"" ws ":" ws argobj ws "}"

toolname ::= "\"timer_start\"" | "\"timer_pause\"" | "\"timer_continue\"" | "\"timer_abort\"" | "\"timer_stop\"" | "\"timer_reset\""

argobj ::= "{" ws "\"session\"" ws ":" ws string ws "}"

string ::= "\"" chars "\""
chars ::= (char)*
char ::= [^"\\] | escape
escape ::= "\\" (["\\/bfnrt] | "u" hex hex hex hex)
hex ::= [0-9a-fA-F]

ws ::= ([ \t\n\r])*
"""


class LlamaBackend:
    def __init__(self, config: LLMConfig):
        from llama_cpp import Llama, LlamaGrammar

        self._llm = Llama(
            model_path=config.model_path,
            n_threads=config.n_threads,
            n_ctx=config.n_ctx,
            n_batch=config.n_batch,
            verbose=config.verbose,
        )
        self._grammar = LlamaGrammar.from_string(GBNF_SCHEMA)
        self._config = config

    def complete(self, messages: list[dict[str, str]], max_tokens: int) -> str:
        response: dict[str, Any] = self._llm.create_chat_completion(
            messages=messages,
            temperature=self._config.temperature,
            top_p=self._config.top_p,
            repeat_penalty=self._config.repeat_penalty,
            max_tokens=max_tokens,
            grammar=self._grammar,
        )
        return response["choices"][0]["message"]["content"]
