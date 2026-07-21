"""Unit tests for CSV/Excel parsing and identifier sanitization."""

from __future__ import annotations

import io

import pytest

from app.core.exceptions import UploadError
from app.services.file_parser import (
    FileParser,
    infer_pg_type,
    sanitize_identifier,
    unique_identifiers,
)
import pandas as pd


class TestSanitizeIdentifier:
    def test_basic(self) -> None:
        assert sanitize_identifier("Sales Report!") == "sales_report"

    def test_leading_digit(self) -> None:
        assert sanitize_identifier("2024_sales") == "c_2024_sales"

    def test_empty_fallback(self) -> None:
        assert sanitize_identifier("@@@") == "col"


class TestUniqueIdentifiers:
    def test_dedupes(self) -> None:
        assert unique_identifiers(["Region", "region", "Amount"]) == [
            "region",
            "region_2",
            "amount",
        ]


class TestInferPgType:
    def test_integer(self) -> None:
        assert infer_pg_type(pd.Series([1, 2, 3])) == "BIGINT"

    def test_float(self) -> None:
        assert infer_pg_type(pd.Series([1.5, 2.0])) == "DOUBLE PRECISION"

    def test_text(self) -> None:
        assert infer_pg_type(pd.Series(["East", "West"])) == "TEXT"


class TestFileParser:
    def test_detect_csv(self) -> None:
        assert FileParser.detect_kind("sales.csv") == "csv"

    def test_detect_xlsx(self) -> None:
        assert FileParser.detect_kind("sales.XLSX") == "xlsx"

    def test_rejects_unknown(self) -> None:
        with pytest.raises(UploadError, match="Unsupported"):
            FileParser.detect_kind("notes.txt")

    def test_parse_csv(self) -> None:
        raw = b"region,amount\nEast,100\nWest,50\n"
        parsed = FileParser.parse(filename="sales.csv", content=raw)
        assert parsed.table_name == "sales"
        assert parsed.file_kind == "csv"
        assert [c.name for c in parsed.columns] == ["region", "amount"]
        assert parsed.columns[1].pg_type == "BIGINT"
        assert parsed.rows == [
            {"region": "East", "amount": 100},
            {"region": "West", "amount": 50},
        ]

    def test_parse_empty_raises(self) -> None:
        with pytest.raises(UploadError, match="empty"):
            FileParser.parse(filename="empty.csv", content=b"")

    def test_parse_xlsx(self) -> None:
        frame = pd.DataFrame({"product": ["A", "B"], "units": [3, 7]})
        buf = io.BytesIO()
        frame.to_excel(buf, index=False, engine="openpyxl")
        parsed = FileParser.parse(filename="products.xlsx", content=buf.getvalue())
        assert parsed.file_kind == "xlsx"
        assert parsed.table_name == "products"
        assert len(parsed.rows) == 2
        assert parsed.columns[1].pg_type == "BIGINT"
