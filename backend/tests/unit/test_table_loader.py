"""TableLoader writes uploads into the project (app) database."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from psycopg2 import sql as pg_sql

from app.core.exceptions import UploadError
from app.services.file_parser import ParsedColumn, ParsedTable
from app.services.table_loader import TableLoader


def _parsed() -> ParsedTable:
    return ParsedTable(
        table_name="sales",
        display_name="Sales",
        columns=[
            ParsedColumn(name="region", pg_type="TEXT"),
            ParsedColumn(name="amount", pg_type="BIGINT"),
        ],
        rows=[{"region": "East", "amount": 10}],
        file_kind="csv",
    )


def _executed_sql(cursor: MagicMock) -> str:
    return " ".join(str(call.args[0]) for call in cursor.execute.call_args_list)


def test_writer_url_targets_app_db() -> None:
    """Uploads must not depend on a separate UPLOAD_WH_* warehouse."""
    with patch("app.services.table_loader.settings") as mock_settings:
        mock_settings.app_db_host = "dpg-example.render.com"
        mock_settings.app_db_port = 5432
        mock_settings.app_db_name = "chat_sql"
        mock_settings.app_db_user = "app_user"
        mock_settings.app_db_password.get_secret_value.return_value = "s3cr3t"
        url = TableLoader.writer_url()

    assert url.startswith("postgresql://")
    assert "+asyncpg" not in url
    assert "dpg-example.render.com:5432" in url
    assert url.endswith("/chat_sql")


def test_writer_url_escapes_special_characters() -> None:
    with patch("app.services.table_loader.settings") as mock_settings:
        mock_settings.app_db_host = "localhost"
        mock_settings.app_db_port = 5432
        mock_settings.app_db_name = "bi_app"
        mock_settings.app_db_user = "user@name"
        mock_settings.app_db_password.get_secret_value.return_value = "p@ss/word"
        url = TableLoader.writer_url()

    assert "p%40ss%2Fword" in url
    assert "user%40name" in url


class TestTableLoaderLoad:
    def _run(self, parsed: ParsedTable | None = None):
        cursor = MagicMock()
        conn = MagicMock()
        conn.cursor.return_value.__enter__.return_value = cursor

        with (
            patch("app.services.table_loader.settings") as mock_settings,
            patch(
                "app.services.table_loader.TableLoader.writer_url",
                return_value="postgresql://u:p@localhost:5432/bi_app",
            ),
            patch(
                "app.services.table_loader.connect_warehouse",
                return_value=conn,
            ) as mock_connect,
            patch("app.services.table_loader.execute_values") as mock_insert,
            # as_string() needs a real libpq cursor to quote identifiers.
            patch.object(pg_sql.Composed, "as_string", return_value="INSERT INTO t VALUES %s"),
        ):
            conn.__enter__.return_value = conn
            mock_settings.app_db_host = "localhost"
            result = TableLoader.load(
                schema_name="u_abcdef123456",
                parsed=parsed or _parsed(),
            )
        return result, cursor, conn, mock_connect, mock_insert

    def test_creates_schema_and_table(self) -> None:
        result, cursor, conn, _, mock_insert = self._run()

        sql_text = _executed_sql(cursor)
        assert "CREATE SCHEMA IF NOT EXISTS" in sql_text
        assert "DROP TABLE IF EXISTS" in sql_text
        assert "CREATE TABLE" in sql_text
        mock_insert.assert_called_once()
        conn.commit.assert_called_once()
        assert result.schema_name == "u_abcdef123456"
        assert result.table_name == "sales"
        assert result.rows_loaded == 1
        assert result.columns == ["region", "amount"]

    def test_does_not_grant_to_a_separate_query_role(self) -> None:
        """Owner and reader are the same app DB user now, so grants are dead weight."""
        _, cursor, _, _, _ = self._run()

        sql_text = _executed_sql(cursor)
        assert "GRANT" not in sql_text.upper()
        assert "DEFAULT PRIVILEGES" not in sql_text.upper()

    def test_connects_to_app_db_host(self) -> None:
        _, _, _, mock_connect, _ = self._run()

        assert mock_connect.call_args.kwargs["host"] == "localhost"

    def test_skips_insert_when_no_rows(self) -> None:
        empty = ParsedTable(
            table_name="sales",
            display_name="Sales",
            columns=[ParsedColumn(name="region", pg_type="TEXT")],
            rows=[],
            file_kind="csv",
        )
        result, _, _, _, mock_insert = self._run(empty)

        mock_insert.assert_not_called()
        assert result.rows_loaded == 0

    def test_rejects_invalid_schema_identifier(self) -> None:
        with pytest.raises(ValueError):
            TableLoader.load(schema_name="bad schema; DROP TABLE x", parsed=_parsed())

    def test_wraps_driver_errors_in_upload_error(self) -> None:
        with (
            patch(
                "app.services.table_loader.TableLoader.writer_url",
                return_value="postgresql://u:p@localhost:5432/bi_app",
            ),
            patch(
                "app.services.table_loader.connect_warehouse",
                side_effect=RuntimeError("password authentication failed for user 'x'"),
            ),
        ):
            with pytest.raises(UploadError) as exc:
                TableLoader.load(schema_name="u_abcdef123456", parsed=_parsed())

        # Driver detail must not reach the client.
        assert "password" not in str(exc.value)
        assert str(exc.value) == "Could not load data into warehouse."
