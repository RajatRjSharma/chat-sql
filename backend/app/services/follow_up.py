"""Detect conversational follow-ups so prior SQL is only reused when appropriate."""

from __future__ import annotations

import re

# Hard refinement / continuation cues (domain-agnostic BI follow-ups).
_HARD_FOLLOW_UP_RE = re.compile(
    r"\b("
    r"break\s+(?:that|it|this)\s+down|"
    r"break\s+down|"
    r"drill\s+down|"
    r"slice\s+by|"
    r"only\s+for|"
    r"just\s+for|"
    r"for\s+\w+\s+only|"
    r"just\s+the\s+top|"
    r"same\s+(?:but|query|breakdown|thing|analysis)|"
    r"do\s+the\s+same|"
    r"filter\s+(?:to|by|on)|"
    r"narrow\s+(?:to|it)|"
    r"restrict\s+to|"
    r"limit\s+to|"
    r"exclude|"
    r"for\s+the\s+top|"
    r"top\s+\w+\s+only|"
    r"and\s+for|"
    r"also\s+show|"
    r"now\s+show|"
    r"now\s+only|"
    r"per\s+month\s+only|"
    r"by\s+month\s+only|"
    r"follow[- ]?up|"
    r"instead\s+(?:of|filter|show|group|by)"
    r")\b",
    re.IGNORECASE,
)

# Soft cues — only follow-ups when paired with BI / refinement vocabulary.
_SOFT_FOLLOW_UP_RE = re.compile(
    r"\b(what\s+about|how\s+about|instead)\b",
    re.IGNORECASE,
)

_ANAPHORA_RE = re.compile(
    r"\b(that|those|these|them|it|previous|above|earlier)\b",
    re.IGNORECASE,
)

# Enough signal that a soft/anaphoric cue is still about warehouse analytics.
_BI_CONTINUATION_RE = re.compile(
    r"\b("
    r"month|months|monthly|year|years|yearly|quarter|quarters|"
    r"week|weeks|weekly|day|days|daily|date|dates|"
    r"region|regions|territory|territories|channel|channels|"
    r"segment|segments|customer|customers|product|products|"
    r"order|orders|revenue|sales|amount|total|totals|sum|count|"
    r"avg|average|top|bottom|filter|group|grouped|breakdown|"
    r"compare|metric|metrics|trend|trends|enterprise|smb|"
    r"only|by\s+\w+"
    r")\b",
    re.IGNORECASE,
)


def looks_like_follow_up(
    question: str,
    history: list[dict[str, str]] | None,
) -> bool:
    """
    True when the user is refining a prior turn rather than starting a new ask.

    Industry pattern: reuse prior SQL / join paths only for clear continuations,
    so unrelated questions in the same session stay unbiased.
    """
    q = (question or "").strip()
    if not q:
        return False
    if not history:
        return False

    if _HARD_FOLLOW_UP_RE.search(q):
        return True

    has_bi = bool(_BI_CONTINUATION_RE.search(q))
    if _SOFT_FOLLOW_UP_RE.search(q) and has_bi:
        return True

    # Short anaphoric refinements only when still clearly analytics-shaped.
    words = q.split()
    if len(words) <= 14 and _ANAPHORA_RE.search(q) and has_bi:
        return True

    return False


def sanitize_source_metadata_for_client(
    metadata: dict | None,
) -> dict | None:
    """Drop planner-only fields before returning metadata to the UI/API."""
    if not metadata:
        return metadata
    if "prior_successful_sql" not in metadata:
        return metadata
    return {k: v for k, v in metadata.items() if k != "prior_successful_sql"}
