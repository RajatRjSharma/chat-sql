"""Generate schema-aware suggested analytics questions."""

from __future__ import annotations

import re
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import QueryHistory, SchemaEmbedding
from app.models.session import ChatSession
from app.services.data_source_service import DataSourceService

_NUMERIC_TYPES = (
    "int",
    "numeric",
    "decimal",
    "float",
    "double",
    "real",
    "money",
    "bigint",
    "smallint",
)
_ID_NAME_RE = re.compile(r"(^id$|_id$)", re.IGNORECASE)
_METRIC_HINTS = (
    "amount",
    "total",
    "revenue",
    "sales",
    "price",
    "cost",
    "qty",
    "quantity",
    "units",
    "count",
    "value",
)
_CATEGORY_HINTS = (
    "region",
    "category",
    "status",
    "city",
    "country",
    "segment",
    "type",
    "name",
    "product",
    "customer",
)
_FALLBACK_QUESTIONS = [
    "What tables are available in this warehouse?",
    "Summarize the main entities in this schema.",
    "Which tables look most useful for sales analysis?",
    "Show me a high-level overview of the data model.",
]

_COLUMN_RE = re.compile(
    r"^\s*-\s*(?P<name>[A-Za-z_][\w]*)\s*:\s*(?P<type>[^\s(]+)",
    re.MULTILINE,
)
_TABLE_RE = re.compile(r"^Table:\s*(?P<name>.+)$", re.MULTILINE)


def _is_numeric(data_type: str) -> bool:
    lowered = data_type.lower()
    return any(token in lowered for token in _NUMERIC_TYPES)


def _is_id_column(name: str) -> bool:
    return bool(_ID_NAME_RE.search(name))


def _rank_metrics(names: list[str]) -> list[str]:
    """Prefer business measures over surrogate keys like order_id."""
    scored: list[tuple[int, str]] = []
    for name in names:
        lowered = name.lower()
        if _is_id_column(name):
            score = 0
        elif any(hint in lowered for hint in _METRIC_HINTS):
            score = 3
        else:
            score = 2
        scored.append((score, name))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [name for score, name in scored if score > 0] or names


def _is_categorical(name: str, data_type: str) -> bool:
    lowered_name = name.lower()
    lowered_type = data_type.lower()
    if any(hint in lowered_name for hint in _CATEGORY_HINTS):
        return True
    return "char" in lowered_type or "text" in lowered_type or "enum" in lowered_type


def parse_schema_chunk(content: str) -> dict[str, Any] | None:
    """Extract table name + columns from a stored schema chunk."""
    table_match = _TABLE_RE.search(content)
    if not table_match:
        return None
    qualified = table_match.group("name").strip()
    table = qualified.split(".")[-1]
    columns = [
        {"name": m.group("name"), "data_type": m.group("type")}
        for m in _COLUMN_RE.finditer(content)
    ]
    return {"qualified_name": qualified, "table": table, "columns": columns}


def build_questions_from_tables(
    tables: list[dict[str, Any]],
    *,
    history_titles: list[str] | None = None,
    limit: int = 6,
) -> list[dict[str, Any]]:
    """
    Deterministic, schema-grounded prompt templates.
    Prefer reliable heuristics over LLM so free-tier rate limits do not empty the UI.
    """
    questions: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(text: str, *, source: str, table: str | None = None) -> None:
        normalized = " ".join(text.lower().split())
        if normalized in seen or len(questions) >= limit:
            return
        seen.add(normalized)
        questions.append(
            {
                "question": text,
                "source": source,
                "table": table,
            }
        )

    for title in history_titles or []:
        cleaned = title.strip()
        if cleaned:
            add(cleaned, source="history")

    for table in tables:
        name = table["table"]
        cols = table["columns"]
        numeric = _rank_metrics(
            [c["name"] for c in cols if _is_numeric(c["data_type"])]
        )
        categorical = [
            c["name"]
            for c in cols
            if _is_categorical(c["name"], c["data_type"]) and not _is_id_column(c["name"])
        ]

        add(
            f"Give me a quick summary of the {name} table.",
            source="schema",
            table=name,
        )

        if numeric and categorical:
            metric = numeric[0]
            dim = categorical[0]
            add(
                f"What is total {metric} by {dim} in {name}?",
                source="schema",
                table=name,
            )
            if len(categorical) > 1:
                add(
                    f"How does {metric} break down by {categorical[1]} in {name}?",
                    source="schema",
                    table=name,
                )
        elif numeric:
            add(
                f"What is the total and average {numeric[0]} in {name}?",
                source="schema",
                table=name,
            )
        elif categorical:
            add(
                f"What are the top values of {categorical[0]} in {name}?",
                source="schema",
                table=name,
            )

    if len(tables) >= 2:
        names = ", ".join(t["table"] for t in tables[:3])
        add(
            f"How are {names} related, and what should I analyze first?",
            source="schema",
        )

    if not questions:
        for text in _FALLBACK_QUESTIONS:
            add(text, source="fallback")

    return questions[:limit]


class SuggestionService:
    """Schema-aware suggested questions for the Meridian sidebar."""

    @staticmethod
    async def suggest_for_data_source(
        session: AsyncSession,
        data_source_id: uuid.UUID,
        *,
        user_id: uuid.UUID | None = None,
        limit: int = 6,
    ) -> dict[str, Any]:
        await DataSourceService.get_active(session, data_source_id, user_id=user_id)

        result = await session.execute(
            select(SchemaEmbedding.content, SchemaEmbedding.metadata_)
            .where(SchemaEmbedding.data_source_id == data_source_id)
            .order_by(SchemaEmbedding.id.asc())
            .limit(30)
        )
        rows = result.all()

        tables: list[dict[str, Any]] = []
        for content, metadata in rows:
            parsed = parse_schema_chunk(content)
            if parsed is None:
                continue
            if metadata and metadata.get("table") and not parsed.get("table"):
                parsed["table"] = metadata["table"]
            tables.append(parsed)

        history_titles = await SuggestionService._recent_successful_titles(
            session, data_source_id
        )
        suggestions = build_questions_from_tables(
            tables,
            history_titles=history_titles,
            limit=limit,
        )

        return {
            "data_source_id": data_source_id,
            "suggestions": suggestions,
            "schema_tables": [t["table"] for t in tables],
        }

    @staticmethod
    async def _recent_successful_titles(
        session: AsyncSession,
        data_source_id: uuid.UUID,
        *,
        limit: int = 3,
    ) -> list[str]:
        stmt = (
            select(QueryHistory.question)
            .join(ChatSession, ChatSession.session_id == QueryHistory.session_id)
            .where(ChatSession.data_source_id == data_source_id)
            .where(QueryHistory.status == "ok")
            .order_by(QueryHistory.created_at.desc())
            .limit(limit)
        )
        result = await session.execute(stmt)
        return [q for q in result.scalars().all() if q and q.strip()]
