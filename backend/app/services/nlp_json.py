"""Shared small-token JSON parsing for NLP LLM contracts.

Industry practice: soft NL steps return compact JSON; parsers are strict and
fail closed so callers can fall back to structural heuristics.
"""

from __future__ import annotations

import json
import re
from typing import Any

_JSON_FENCE_RE = re.compile(
    r"```(?:json)?\s*(\{.*?\})\s*```",
    re.IGNORECASE | re.DOTALL,
)
# Non-greedy innermost-ish object; callers retry with full text if needed.
_BARE_JSON_RE = re.compile(r"\{[^{}]*\}", re.DOTALL)
_BALANCED_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


def extract_json_object(raw: str) -> dict[str, Any] | None:
    """Parse the first JSON object from an LLM reply (fence / bare / whole)."""
    text = (raw or "").strip()
    if not text:
        return None

    candidates: list[str] = []
    fence = _JSON_FENCE_RE.search(text)
    if fence:
        candidates.append(fence.group(1))
    bare = _BARE_JSON_RE.search(text)
    if bare:
        candidates.append(bare.group(0))
    balanced = _BALANCED_JSON_RE.search(text)
    if balanced:
        candidates.append(balanced.group(0))
    candidates.append(text)

    seen: set[str] = set()
    for candidate in candidates:
        key = candidate.strip()
        if not key or key in seen:
            continue
        seen.add(key)
        try:
            data = json.loads(key)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            return data
    return None


def clamp_confidence(value: Any, *, default: float = 0.5) -> float:
    try:
        conf = float(value)
    except (TypeError, ValueError):
        conf = default
    return max(0.0, min(1.0, conf))
