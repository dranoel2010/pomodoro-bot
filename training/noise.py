"""ASR-style noise augmentation utilities."""

from __future__ import annotations

import random
import re

from .common import replace_umlauts_ascii


FILLER_WORDS = {
    "bitte",
    "mal",
    "kurz",
    "doch",
    "jetzt",
    "gerade",
    "ein",
    "eine",
    "den",
    "die",
    "das",
}

MORPHOLOGY_RULES = (
    ("pausiere", "pausier"),
    ("stoppe", "stopp"),
    ("setze", "setz"),
    ("zurueck", "zuruck"),
    ("zeige", "zeig"),
    ("fuege", "fug"),
    ("hinzu", "dazu"),
    ("fort", "weiter"),
)


def _normalize_spacing(text: str) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    return compact


def apply_noise(text: str, *, rng: random.Random, enabled: bool) -> tuple[str, list[str]]:
    """Apply controlled STT-like noise mutations to a prompt."""
    if not enabled:
        return _normalize_spacing(text), []

    out = text
    tags: list[str] = []

    if rng.random() < 0.45:
        normalized = replace_umlauts_ascii(out)
        if normalized != out:
            out = normalized
            tags.append("char_norm")

    if rng.random() < 0.40:
        replaced = out
        for old, new in MORPHOLOGY_RULES:
            replaced = re.sub(rf"\b{re.escape(old)}\b", new, replaced, flags=re.I)
        if replaced != out:
            out = replaced
            tags.append("morphology")

    if rng.random() < 0.35:
        without_punct = re.sub(r"[,.!?;:]", "", out)
        if without_punct != out:
            out = without_punct
            tags.append("punct_drop")

    if rng.random() < 0.35:
        tokens = out.split()
        kept: list[str] = []
        for token in tokens:
            token_norm = re.sub(r"[^a-zA-Z0-9]", "", token).lower()
            if token_norm in FILLER_WORDS and rng.random() < 0.45:
                continue
            kept.append(token)
        dropped = " ".join(kept)
        if dropped and dropped != out:
            out = dropped
            tags.append("omission")

    if rng.random() < 0.25:
        if rng.random() < 0.5:
            out = out.lower()
        else:
            out = out.upper()
        tags.append("casing_drift")

    if rng.random() < 0.22:
        clauses = re.split(r"\bund\b", out, flags=re.I)
        if len(clauses) == 2:
            swapped = f"{clauses[1].strip()} und {clauses[0].strip()}"
            if swapped and swapped != out:
                out = swapped
                tags.append("clause_reorder")

    normalized = _normalize_spacing(out)
    if not normalized:
        return _normalize_spacing(text), []
    return normalized, sorted(set(tags))
