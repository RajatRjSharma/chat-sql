"""Parse CSV / Excel uploads into typed columnar tables."""

from __future__ import annotations

import io
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import pandas as pd

from app.config import settings
from app.core.exceptions import UploadError

FileKind = Literal["csv", "xlsx"]

_ALLOWED_EXTENSIONS = {".csv": "csv", ".xlsx": "xlsx"}
_IDENT_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_NON_ALNUM = re.compile(r"[^a-z0-9]+")


@dataclass(frozen=True, slots=True)
class ParsedColumn:
    name: str
    pg_type: str


@dataclass(frozen=True, slots=True)
class ParsedTable:
    table_name: str
    display_name: str
    columns: list[ParsedColumn]
    rows: list[dict[str, Any]]
    file_kind: FileKind
    sheet_name: str | None = None


def sanitize_identifier(raw: str, *, fallback: str = "col", max_len: int = 48) -> str:
    """Turn a filename/header into a safe lowercase Postgres identifier."""
    cleaned = _NON_ALNUM.sub("_", raw.strip().lower()).strip("_")
    if cleaned and cleaned[0].isdigit():
        cleaned = f"c_{cleaned}"
    if not cleaned:
        cleaned = fallback
    cleaned = cleaned[:max_len].rstrip("_")
    if not _IDENT_RE.match(cleaned):
        cleaned = fallback
    return cleaned


def unique_identifiers(names: list[str], *, fallback: str = "col") -> list[str]:
    """Deduplicate sanitized names (region, region → region, region_2)."""
    seen: dict[str, int] = {}
    result: list[str] = []
    for raw in names:
        base = sanitize_identifier(str(raw), fallback=fallback)
        count = seen.get(base, 0) + 1
        seen[base] = count
        result.append(base if count == 1 else f"{base}_{count}"[:63])
    return result


def infer_pg_type(series: pd.Series) -> str:
    """Map a pandas Series to a conservative PostgreSQL type."""
    non_null = series.dropna()
    if non_null.empty:
        return "TEXT"

    if pd.api.types.is_bool_dtype(series):
        return "BOOLEAN"
    if pd.api.types.is_integer_dtype(series):
        return "BIGINT"
    if pd.api.types.is_float_dtype(series):
        return "DOUBLE PRECISION"
    if pd.api.types.is_datetime64_any_dtype(series):
        return "TIMESTAMP"

    # Object columns: try numeric / boolean coercion for CSV strings
    sample = non_null.head(200)
    try:
        as_num = pd.to_numeric(sample, errors="raise")
        if (as_num % 1 == 0).all():
            return "BIGINT"
        return "DOUBLE PRECISION"
    except (ValueError, TypeError):
        pass

    lowered = sample.astype(str).str.strip().str.lower()
    if set(lowered.unique()).issubset({"true", "false", "0", "1", "yes", "no"}):
        return "BOOLEAN"

    return "TEXT"


def _normalize_cell(value: Any, pg_type: str) -> Any:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime()
    if pg_type == "BOOLEAN":
        if isinstance(value, bool):
            return value
        text = str(value).strip().lower()
        if text in {"true", "1", "yes"}:
            return True
        if text in {"false", "0", "no"}:
            return False
        return None
    if pg_type in {"BIGINT", "DOUBLE PRECISION"}:
        try:
            num = pd.to_numeric(value, errors="raise")
            if pg_type == "BIGINT":
                return int(num)
            return float(num)
        except (ValueError, TypeError):
            return None
    return str(value)


class FileParser:
    """Validate and parse uploaded tabular files."""

    @staticmethod
    def detect_kind(filename: str) -> FileKind:
        ext = Path(filename).suffix.lower()
        kind = _ALLOWED_EXTENSIONS.get(ext)
        if kind is None:
            raise UploadError(
                "Unsupported file type. Upload a .csv or .xlsx file."
            )
        return kind  # type: ignore[return-value]

    @staticmethod
    def parse(
        *,
        filename: str,
        content: bytes,
        display_name: str | None = None,
    ) -> ParsedTable:
        if not content:
            raise UploadError("Uploaded file is empty.")
        if len(content) > settings.upload_max_bytes:
            raise UploadError(
                f"File exceeds the {settings.upload_max_bytes // (1024 * 1024)} MB limit."
            )

        kind = FileParser.detect_kind(filename)
        stem = Path(filename).stem or "upload"
        table_name = sanitize_identifier(stem, fallback="upload", max_len=40)
        title = (display_name or stem).strip() or stem

        try:
            if kind == "csv":
                frame = pd.read_csv(io.BytesIO(content))
                sheet_name = None
            else:
                frame = pd.read_excel(io.BytesIO(content), sheet_name=0, engine="openpyxl")
                sheet_name = "Sheet1"
        except UploadError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise UploadError(f"Could not parse file: {exc}") from exc

        if frame.empty and len(frame.columns) == 0:
            raise UploadError("File has no columns or rows.")
        if len(frame) > settings.upload_max_rows:
            raise UploadError(
                f"File has {len(frame)} rows; limit is {settings.upload_max_rows}."
            )

        col_names = unique_identifiers([str(c) for c in frame.columns], fallback="col")
        frame.columns = col_names

        columns = [
            ParsedColumn(name=name, pg_type=infer_pg_type(frame[name]))
            for name in col_names
        ]

        rows: list[dict[str, Any]] = []
        type_by_name = {c.name: c.pg_type for c in columns}
        for record in frame.to_dict(orient="records"):
            rows.append(
                {
                    key: _normalize_cell(value, type_by_name[key])
                    for key, value in record.items()
                }
            )

        return ParsedTable(
            table_name=table_name,
            display_name=title[:100],
            columns=columns,
            rows=rows,
            file_kind=kind,
            sheet_name=sheet_name,
        )
