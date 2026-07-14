"""Validate generated SQL with sqlglot — SELECT-only, schema-scoped."""

from __future__ import annotations

import re

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError, TokenError

from app.core.exceptions import SqlValidationError
from app.core.schema import validate_optional_schema

_FORBIDDEN_TYPES = (
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Drop,
    exp.Create,
    exp.Alter,
    exp.Command,
)

_SQL_FENCE_RE = re.compile(r"```(?:sql)?\s*(.*?)```", re.IGNORECASE | re.DOTALL)


def extract_sql(raw: str) -> str:
    """Pull SQL out of markdown fences or plain text."""
    text = raw.strip()
    fence = _SQL_FENCE_RE.search(text)
    if fence:
        text = fence.group(1).strip()
    # Drop a leading "SQL:" label when present.
    if text.lower().startswith("sql:"):
        text = text[4:].strip()
    return text.rstrip(";").strip()


class SqlValidator:
    """Safety gate before warehouse execution."""

    @staticmethod
    def validate(
        sql: str,
        *,
        allowed_schema: str | None = None,
        allowed_tables: set[str] | None = None,
        dialect: str = "postgres",
    ) -> str:
        cleaned = extract_sql(sql)
        if not cleaned:
            raise SqlValidationError("Empty SQL.")

        schema = validate_optional_schema(allowed_schema)
        read_dialect = dialect or "postgres"

        try:
            statements = sqlglot.parse(cleaned, read=read_dialect)
        except (ParseError, TokenError) as exc:
            raise SqlValidationError(
                f"Generated SQL is not valid for dialect '{read_dialect}'. "
                "Fix syntax and return one complete SELECT. "
                f"Parser detail: {exc}"
            ) from exc
        except Exception as exc:  # noqa: BLE001 — never let parser crashes kill retries
            raise SqlValidationError(
                "SQL could not be parsed safely. Return a simpler SELECT. "
                f"Detail: {exc}"
            ) from exc

        if not statements:
            raise SqlValidationError("No SQL statements found.")
        if len(statements) != 1:
            raise SqlValidationError("Only a single SQL statement is allowed.")

        statement = statements[0]
        if statement is None:
            raise SqlValidationError("Empty SQL statement.")

        if not isinstance(statement, (exp.Select, exp.Union)):
            raise SqlValidationError("Only SELECT (or UNION of SELECTs) is allowed.")

        for node in statement.walk():
            if isinstance(node, _FORBIDDEN_TYPES):
                raise SqlValidationError(
                    f"Forbidden SQL construct: {type(node).__name__}."
                )

        if schema or allowed_tables:
            SqlValidator._check_tables(
                statement, schema=schema, allowed_tables=allowed_tables
            )

        return cleaned

    @staticmethod
    def _check_tables(
        statement: exp.Expression,
        *,
        schema: str | None,
        allowed_tables: set[str] | None,
    ) -> None:
        for table in statement.find_all(exp.Table):
            table_name = table.name
            table_schema = table.db or None

            if schema and table_schema and table_schema != schema:
                raise SqlValidationError(
                    f"Table {table_schema}.{table_name} is outside allowed schema {schema!r}."
                )

            if allowed_tables and table_name not in allowed_tables:
                raise SqlValidationError(
                    f"Table {table_name!r} is not in the allowed table set."
                )
