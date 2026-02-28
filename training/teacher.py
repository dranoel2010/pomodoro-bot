"""Teacher paraphrase providers for dataset expansion."""

from __future__ import annotations

import json
import os
import random
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from .common import replace_umlauts_ascii


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


@dataclass(slots=True)
class TeacherClient:
    """Paraphrase client with optional OpenAI fallback."""

    model: str
    provider: str = "auto"
    timeout_seconds: float = 25.0

    def __post_init__(self) -> None:
        chosen = self.provider.strip().lower()
        if chosen not in {"auto", "openai", "local"}:
            raise ValueError("provider must be one of: auto, openai, local")
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
            provider = "openai" if os.getenv("OPENAI_API_KEY", "").strip() else "local"

        if provider == "openai":
            paraphrase = self._paraphrase_openai(
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
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError):
            return None

        try:
            content = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            return None

        if not isinstance(content, str):
            return None

        snippet = content.strip()
        if snippet.startswith("```"):
            snippet = snippet.strip("`\n ")
            if snippet.lower().startswith("json"):
                snippet = snippet[4:].strip()

        try:
            parsed = json.loads(snippet)
        except json.JSONDecodeError:
            return None

        paraphrase = parsed.get("paraphrase") if isinstance(parsed, dict) else None
        if not isinstance(paraphrase, str):
            return None

        cleaned = " ".join(paraphrase.strip().split())
        return cleaned or None
