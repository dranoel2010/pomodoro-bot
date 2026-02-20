from typing import Any

from .config import LLMConfig


GBNF_SCHEMA = r"""
root ::= "{" ws "\"assistant_text\"" ws ":" ws string ws "," ws "\"tool_call\"" ws ":" ws toolcall ws "}"
toolcall ::= "null" | toolobj
toolobj ::= "{" ws "\"name\"" ws ":" ws toolname ws "," ws "\"arguments\"" ws ":" ws argobj ws "}"
toolname ::= "\"start_timer\"" | "\"stop_timer\"" | "\"pause_timer\"" | "\"continue_timer\"" | "\"reset_timer\"" | "\"start_pomodoro_session\"" | "\"stop_pomodoro_session\"" | "\"pause_pomodoro_session\"" | "\"continue_pomodoro_session\"" | "\"reset_pomodoro_session\""
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
