"""Small-token LLM Intent Router for Text2SQL chat (industry soft-NL layer).

Architecture (Genie / Defog / Vanna-style):
  soft NL  → IntentRouter + EntityLinker (compact JSON, small max_tokens)
  retrieve → embeddings + FK expand (schema-derived, domain-agnostic)
  hard SQL → sqlglot allowlist + SELECT-only (never trust the model)

Heuristics in ``fallback`` / ``apply_safety_nets`` are emergency rails only —
when ``NLP_PREFER_LLM`` is true, production paths call the LLM first.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Literal

from app.config import settings
from app.core.exceptions import AIProviderError
from app.providers.ai import AIClient, get_ai_client
from app.services.catalog_overview import is_catalog_overview_question
from app.services.follow_up import looks_like_follow_up
from app.services.nlp_json import clamp_confidence, extract_json_object
from app.services.scope_guard import ScopeGuard

logger = logging.getLogger(__name__)

IntentLabel = Literal[
    "catalog_overview",
    "analytics",
    "follow_up",
    "out_of_scope",
    "clarify",
]

_VALID_INTENTS = frozenset(
    {
        "catalog_overview",
        "analytics",
        "follow_up",
        "out_of_scope",
        "clarify",
    }
)

# Only rewrite DP→DB when it is used as a database synonym near overview nouns.
_DB_TYPO_RE = re.compile(r"\bdp\b", re.IGNORECASE)
_DB_TYPO_CONTEXT_RE = re.compile(
    r"(?ix)"
    r"(?:"
    r"(?:summar(?:y|ize|ise)|overview|inventory|describe|contents?|catalog)"
    r".{0,40}\bdp\b"
    r"|"
    r"\bdp\b.{0,40}"
    r"(?:summar(?:y|ize|ise)|overview|inventory|database|schema|warehouse|catalog)"
    r")"
)

_SYSTEM = """\
You route questions for a read-only warehouse Text2SQL / BI assistant.

Return ONLY compact JSON (no markdown, no prose):
{"intent":"...","confidence":0.0,"reason":"short","normalized_question":"..."}

intent must be one of:
- catalog_overview — inventory / summary / overview of the whole DB/schema/warehouse
  (typos OK: db, database, schema, warehouse, catalog, data)
- analytics — ask about tables, metrics, dimensions, filters, joins, trends
- follow_up — refinement of the prior warehouse answer (only when prior SQL exists)
- out_of_scope — trivia / world facts / sports winners / coding help / non-warehouse
- clarify — too vague (e.g. only "summary" or "help") with no DB/table/metric cue

Rules:
1. Prefer catalog_overview when the user wants a summary/overview of the database
   even with spelling mistakes in either phrase.
2. Bare "summary" with no DB/table/metric cue → clarify.
3. World Cup, celebrities, weather, general knowledge → out_of_scope.
4. If prior_sql_present is true and the ask refines prior results (by month,
   by a dimension, break down, filter) → follow_up.
5. When unsure between analytics and out_of_scope → analytics.
6. confidence is 0..1. Keep reason under 12 words.
7. Do not assume any industry (retail, HR, IoT, …); use only the provided tables.
8. Normalize obvious warehouse synonyms in normalized_question (e.g. "dp"→"database"
   only when it clearly means the database, not a department code).

Examples:
- "summay of db" → {"intent":"catalog_overview","confidence":0.95,
  "reason":"database overview","normalized_question":"summary of database"}
- "sumary for the warehous" → {"intent":"catalog_overview","confidence":0.95,
  "reason":"warehouse overview","normalized_question":"summary for the warehouse"}
- "north vs south sales" → {"intent":"analytics","confidence":0.95,
  "reason":"regional sales comparison","normalized_question":"north vs south sales"}
"""


@dataclass(frozen=True, slots=True)
class IntentDecision:
    intent: IntentLabel
    confidence: float
    reason: str
    normalized_question: str
    source: Literal["llm", "fallback"]

    def to_metadata(self) -> dict[str, Any]:
        return {
            "intent": self.intent,
            "intent_confidence": round(self.confidence, 3),
            "intent_reason": self.reason,
            "normalized_question": self.normalized_question,
            "intent_source": self.source,
            "llm_router_model": settings.effective_llm_router_model,
            "nlp_prefer_llm": settings.nlp_prefer_llm,
        }

    @property
    def trusted(self) -> bool:
        """True when graph ScopeGuard should accept this without re-LLM."""
        return self.confidence >= settings.nlp_intent_confidence_trust


class IntentRouter:
    """Compact JSON intent classifier with deterministic safety nets."""

    @staticmethod
    def normalize_question(question: str) -> str:
        q = (question or "").strip()
        if not q:
            return ""
        # Only rewrite DP→DB in database-overview contexts (not "DP" as department).
        if _DB_TYPO_CONTEXT_RE.search(q):
            return _DB_TYPO_RE.sub("db", q)
        return q

    @staticmethod
    def parse_decision(
        raw: str,
        *,
        question: str,
        default_intent: IntentLabel = "clarify",
    ) -> IntentDecision | None:
        del default_intent  # fail-closed → None; caller chooses fallback
        payload = extract_json_object(raw)
        if not payload:
            return None
        intent_raw = str(payload.get("intent") or "").strip().lower()
        if intent_raw not in _VALID_INTENTS:
            return None
        confidence = clamp_confidence(payload.get("confidence", 0.5))
        reason = str(payload.get("reason") or "routed").strip()[:120]
        normalized = str(
            payload.get("normalized_question")
            or IntentRouter.normalize_question(question)
        ).strip()
        return IntentDecision(
            intent=intent_raw,  # type: ignore[arg-type]
            confidence=confidence,
            reason=reason or "routed",
            normalized_question=normalized or IntentRouter.normalize_question(question),
            source="llm",
        )

    @staticmethod
    def fallback(
        question: str,
        *,
        history: list[dict[str, str]] | None = None,
        prior_sql_present: bool = False,
        table_names: list[str] | None = None,
    ) -> IntentDecision:
        """Structural heuristic path when the LLM fails (offline / outage)."""
        original = (question or "").strip()
        q = IntentRouter.normalize_question(original)
        if not q:
            return IntentDecision(
                intent="clarify",
                confidence=1.0,
                reason="empty question",
                normalized_question="",
                source="fallback",
            )

        schema_tokens = {n.lower() for n in (table_names or []) if n}
        if prior_sql_present and looks_like_follow_up(
            q, history, schema_tokens=schema_tokens or None
        ):
            return IntentDecision(
                intent="follow_up",
                confidence=0.75,
                reason="heuristic follow-up",
                normalized_question=q,
                source="fallback",
            )
        if is_catalog_overview_question(q):
            return IntentDecision(
                intent="catalog_overview",
                confidence=0.8,
                reason="heuristic catalog overview",
                normalized_question=q,
                source="fallback",
            )
        if ScopeGuard.is_vague_only(q) and not ScopeGuard.has_warehouse_intent(q):
            return IntentDecision(
                intent="clarify",
                confidence=0.7,
                reason="vague without schema cue",
                normalized_question=q,
                source="fallback",
            )
        if ScopeGuard.has_warehouse_intent(q) or ScopeGuard.has_analytics_intent(q):
            return IntentDecision(
                intent="analytics",
                confidence=0.7,
                reason="heuristic analytics intent",
                normalized_question=q,
                source="fallback",
            )
        if _looks_like_trivia(q):
            return IntentDecision(
                intent="out_of_scope",
                confidence=0.7,
                reason="heuristic trivia",
                normalized_question=q,
                source="fallback",
            )
        return IntentDecision(
            intent="analytics",
            confidence=0.55,
            reason="default analytics",
            normalized_question=q,
            source="fallback",
        )

    @staticmethod
    def apply_safety_nets(
        decision: IntentDecision,
        *,
        question: str,
        table_names: list[str] | None = None,
        prior_sql_present: bool = False,
        history: list[dict[str, str]] | None = None,
    ) -> IntentDecision:
        """Deterministic overrides for free-model false refuses / missed catalog."""
        q = IntentRouter.normalize_question(question)
        normalized = (
            IntentRouter.normalize_question(decision.normalized_question)
            if decision.source == "llm"
            else q
        )
        schema_ids = {n.lower() for n in (table_names or []) if n}

        # Trust the LLM's corrected wording when checking a missed overview.
        if decision.intent in {"clarify", "out_of_scope", "analytics"}:
            if is_catalog_overview_question(q) or is_catalog_overview_question(normalized):
                return IntentDecision(
                    intent="catalog_overview",
                    confidence=max(decision.confidence, 0.85),
                    reason="safety: catalog overview",
                    normalized_question=normalized,
                    source=decision.source,
                )

        # False OUT_OF_SCOPE when schema tokens / warehouse intent present.
        if decision.intent == "out_of_scope":
            if ScopeGuard.has_schema_overlap(
                q, "", allowed_tables=list(table_names or [])
            ) or ScopeGuard.has_warehouse_intent(q):
                return IntentDecision(
                    intent="analytics",
                    confidence=max(decision.confidence, 0.7),
                    reason="safety: schema overlap",
                    normalized_question=decision.normalized_question or q,
                    source=decision.source,
                )

        # Follow-up with prior SQL should not be clarified away.
        if (
            decision.intent in {"clarify", "out_of_scope"}
            and prior_sql_present
            and looks_like_follow_up(q, history, schema_tokens=schema_ids or None)
        ):
            return IntentDecision(
                intent="follow_up",
                confidence=max(decision.confidence, 0.75),
                reason="safety: follow-up",
                normalized_question=decision.normalized_question or q,
                source=decision.source,
            )
        return decision

    @staticmethod
    def route(
        question: str,
        *,
        history: list[dict[str, str]] | None = None,
        prior_sql_present: bool = False,
        table_names: list[str] | None = None,
        client: AIClient | None = None,
    ) -> IntentDecision:
        q = (question or "").strip()
        if not q:
            return IntentRouter.fallback(
                q,
                history=history,
                prior_sql_present=prior_sql_present,
                table_names=table_names,
            )

        # Offline / emergency: skip LLM when explicitly disabled.
        if not settings.nlp_prefer_llm:
            decision = IntentRouter.fallback(
                q,
                history=history,
                prior_sql_present=prior_sql_present,
                table_names=table_names,
            )
            return IntentRouter.apply_safety_nets(
                decision,
                question=q,
                table_names=table_names,
                prior_sql_present=prior_sql_present,
                history=history,
            )

        names = sorted({n for n in (table_names or []) if n})[:80]
        history_snip = _format_history(history)
        user_block = (
            f"prior_sql_present: {str(bool(prior_sql_present)).lower()}\n"
            f"tables ({len(names)}): {', '.join(names) if names else '(none indexed)'}\n"
            f"history:\n{history_snip or '(none)'}\n"
            f"question: {q}"
        )
        ai = client or get_ai_client()
        try:
            raw = ai.complete(
                [
                    {"role": "system", "content": _SYSTEM},
                    {"role": "user", "content": user_block},
                ],
                temperature=0.0,
                max_tokens=settings.nlp_router_max_tokens,
                preferred_model=settings.effective_llm_router_model,
            )
            parsed = IntentRouter.parse_decision(raw, question=q)
            if parsed is None:
                logger.info("IntentRouter invalid JSON; asking model to repair")
                repair = ai.complete(
                    [
                        {
                            "role": "system",
                            "content": (
                                _SYSTEM
                                + "\nThe previous reply was invalid. Return one JSON object only."
                            ),
                        },
                        {"role": "user", "content": user_block},
                    ],
                    temperature=0.0,
                    max_tokens=settings.nlp_router_max_tokens,
                    preferred_model=settings.effective_llm_router_model,
                )
                parsed = IntentRouter.parse_decision(repair, question=q)
                decision = parsed or IntentRouter.fallback(
                    q,
                    history=history,
                    prior_sql_present=prior_sql_present,
                    table_names=table_names,
                )
            else:
                decision = parsed
        except AIProviderError as exc:
            logger.warning("IntentRouter LLM failed (%s); using fallback", exc)
            decision = IntentRouter.fallback(
                q,
                history=history,
                prior_sql_present=prior_sql_present,
                table_names=table_names,
            )

        return IntentRouter.apply_safety_nets(
            decision,
            question=q,
            table_names=table_names,
            prior_sql_present=prior_sql_present,
            history=history,
        )


def _format_history(history: list[dict[str, str]] | None) -> str:
    if not history:
        return ""
    lines: list[str] = []
    for turn in history[-4:]:
        role = (turn.get("role") or "user").strip()
        content = (turn.get("content") or "").strip().replace("\n", " ")
        if not content:
            continue
        lines.append(f"- {role}: {content[:160]}")
    return "\n".join(lines)


_TRIVIA_RE = re.compile(
    r"(?ix)\b("
    r"world\s*cup|who\s+won|president|capital\s+of|weather|forecast|"
    r"celebrity|movie\s+star|write\s+(me\s+)?(python|java|code)|"
    r"how\s+do\s+i\s+code|bitcoin\s+price"
    r")\b"
)


def _looks_like_trivia(question: str) -> bool:
    return bool(_TRIVIA_RE.search(question or ""))
