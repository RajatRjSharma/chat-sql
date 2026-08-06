"""Follow-up detection and client metadata sanitization."""

from __future__ import annotations

from app.services.follow_up import looks_like_follow_up, sanitize_source_metadata_for_client


class TestLooksLikeFollowUp:
    def test_break_that_down(self) -> None:
        assert (
            looks_like_follow_up(
                "Break that down by month only for the top region.",
                [{"role": "user", "content": "orders by region"}],
            )
            is True
        )

    def test_what_about(self) -> None:
        assert (
            looks_like_follow_up(
                "What about the West region?",
                [{"role": "assistant", "content": "North leads"}],
            )
            is True
        )

    def test_independent_question_not_follow_up(self) -> None:
        assert (
            looks_like_follow_up(
                "What is total revenue by customer segment and sales channel?",
                [{"role": "user", "content": "orders by region and month"}],
            )
            is False
        )

    def test_no_history_never_follow_up(self) -> None:
        assert looks_like_follow_up("Break that down by month.", []) is False
        assert looks_like_follow_up("Break that down by month.", None) is False

    def test_independent_new_topic_after_history(self) -> None:
        """Second question that is NOT a follow-up still has history for context."""
        assert (
            looks_like_follow_up(
                "Total revenue by customer segment",
                [
                    {"role": "user", "content": "Total revenue by region and channel"},
                    {"role": "assistant", "content": "North led"},
                ],
            )
            is False
        )

    def test_follow_up_after_successful_turn(self) -> None:
        assert (
            looks_like_follow_up(
                "Break that down by month",
                [
                    {"role": "user", "content": "Total revenue by region and channel"},
                    {"role": "assistant", "content": "North led"},
                ],
            )
            is True
        )


class TestSanitizeMetadata:
    def test_strips_prior_sql(self) -> None:
        meta = {"engine": "PostgreSQL", "prior_successful_sql": "SELECT 1"}
        out = sanitize_source_metadata_for_client(meta)
        assert out is not None
        assert "prior_successful_sql" not in out
        assert out["engine"] == "PostgreSQL"

    def test_none_passthrough(self) -> None:
        assert sanitize_source_metadata_for_client(None) is None
