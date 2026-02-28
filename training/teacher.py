"""Teacher paraphrase providers for dataset expansion."""

from __future__ import annotations

import json
import os
import random
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any

from .common import replace_umlauts_ascii


DEFAULT_OLLAMA_HOST = "http://127.0.0.1:11434"


def _local_paraphrase(text: str, *, rng: random.Random) -> str:
    """Return a deterministic-ish local paraphrase when no external API is available."""
    replacements = [
        ("bitte", ""),
        ("starte", "start"),
        ("pausiere", "pausier"),
        ("stoppe", "stopp"),
        ("setze", "setz"),
        ("zurueck", "neu"),
        ("zeige", "zeig"),
        ("kalender", "termine"),
        ("pomodoro", "fokussitzung"),
        ("timer", "countdown"),
    ]

    out = replace_umlauts_ascii(text).strip()
    lowered = out.lower()
    for old, new in replacements:
        if old in lowered and rng.random() < 0.45:
            lowered = lowered.replace(old, new)

    lowered = " ".join(lowered.split())
    if rng.random() < 0.3:
        lowered = lowered.rstrip(".?!")
    if rng.random() < 0.25 and len(lowered.split()) > 4:
        tokens = lowered.split()
        cut = rng.randint(1, 2)
        lowered = " ".join(tokens[:-cut])

    if lowered and lowered[-1] not in ".!?":
        lowered += "."
    return lowered[0].upper() + lowered[1:] if lowered else text


def _extract_paraphrase(content: Any) -> str | None:
    if not isinstance(content, str):
        return None

    snippet = content.strip()
    if not snippet:
        return None

    if snippet.startswith("```"):
        snippet = snippet.strip("`\n ")
        if snippet.lower().startswith("json"):
            snippet = snippet[4:].strip()

    try:
        parsed = json.loads(snippet)
    except json.JSONDecodeError:
        return None

    if not isinstance(parsed, dict):
        return None

    paraphrase = parsed.get("paraphrase")
    if not isinstance(paraphrase, str):
        return None

    cleaned = " ".join(paraphrase.strip().split())
    if len(cleaned) < 3:
        return None
    return cleaned


@dataclass(slots=True)
class TeacherClient:
    """Paraphrase client with OpenAI/Ollama/local providers."""

    model: str
    provider: str = "auto"
    timeout_seconds: float = 25.0
    _ollama_available: bool | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        chosen = self.provider.strip().lower()
        if chosen not in {"auto", "openai", "ollama", "local"}:
            raise ValueError("provider must be one of: auto, openai, ollama, local")
        self.provider = chosen

    def paraphrase(
        self,
        *,
        user_text: str,
        intent_class: str,
        target_tool_name: str | None,
        rng: random.Random,
    ) -> tuple[str, bool]:
        provider = self.provider
        if provider == "auto":
            if os.getenv("OPENAI_API_KEY", "").strip():
                provider = "openai"
            elif self._is_ollama_ready():
                provider = "ollama"
            else:
                provider = "local"

        if provider == "openai":
            paraphrase = self._paraphrase_openai(
                user_text=user_text,
                intent_class=intent_class,
                target_tool_name=target_tool_name,
            )
            if paraphrase:
                return paraphrase, True

        if provider == "ollama":
            paraphrase = self._paraphrase_ollama(
                user_text=user_text,
                intent_class=intent_class,
                target_tool_name=target_tool_name,
            )
            if paraphrase:
                return paraphrase, True

        return _local_paraphrase(user_text, rng=rng), False

    def _paraphrase_openai(
        self,
        *,
        user_text: str,
        intent_class: str,
        target_tool_name: str | None,
    ) -> str | None:
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key:
            return None

        instruction = (
            "Erzeuge genau eine deutsche Paraphrase der Nutzereingabe. "
            "Behalte die gleiche Tool-Absicht und Slots bei. "
            "Antwort nur als JSON: {\"paraphrase\": string}."
        )
        user_payload = {
            "intent_class": intent_class,
            "target_tool_name": target_tool_name,
            "user_text": user_text,
        }

        body = {
            "model": self.model,
            "temperature": 0.4,
            "max_tokens": 120,
            "messages": [
                {"role": "system", "content": instruction},
                {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
            ],
        }

        request = urllib.request.Request(
            url="https://api.openai.com/v1/chat/completions",
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (
            urllib.error.URLError,
            urllib.error.HTTPError,
            TimeoutError,
            json.JSONDecodeError,
            OSError,
        ):
            return None

        try:
            content = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            return None

        return _extract_paraphrase(content)

    def _paraphrase_ollama(
        self,
        *,
        user_text: str,
        intent_class: str,
        target_tool_name: str | None,
    ) -> str | None:
        payload = {
            "model": self.model,
            "prompt": (
                "Erzeuge genau eine deutsche Paraphrase der Nutzereingabe. "
                "Behalte identische Tool-Absicht und Slots. "
                "Antwort nur als JSON: {\"paraphrase\": string}.\n\n"
                f"intent_class={intent_class}\n"
                f"target_tool_name={target_tool_name}\n"
                f"user_text={user_text}"
            ),
            "stream": False,
            "format": "json",
            "options": {
                "temperature": 0.4,
            },
        }

        request = urllib.request.Request(
            url=self._ollama_url("/api/generate"),
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                body = json.loads(response.read().decode("utf-8"))
        except (
            urllib.error.URLError,
            urllib.error.HTTPError,
            TimeoutError,
            json.JSONDecodeError,
            OSError,
        ):
            self._ollama_available = False
            return None

        content = body.get("response") if isinstance(body, dict) else None
        return _extract_paraphrase(content)

    def _is_ollama_ready(self) -> bool:
        if self._ollama_available is not None:
            return self._ollama_available

        request = urllib.request.Request(
            url=self._ollama_url("/api/tags"),
            method="GET",
        )

        try:
            with urllib.request.urlopen(request, timeout=min(self.timeout_seconds, 2.0)):
                self._ollama_available = True
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError):
            self._ollama_available = False

        return self._ollama_available

    @staticmethod
    def _ollama_url(path: str) -> str:
        host = os.getenv("OLLAMA_HOST", DEFAULT_OLLAMA_HOST).strip()
        if not host:
            host = DEFAULT_OLLAMA_HOST
        if not host.startswith("http://") and not host.startswith("https://"):
            host = f"http://{host}"
        return f"{host.rstrip('/')}{path}"
