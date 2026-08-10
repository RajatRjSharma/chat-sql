"""Result summarizer grounding over full (not preview-only) result sets."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

from app.services.result_summarizer import ResultSummarizer, _numeric_extrema


def test_numeric_extrema_scan_all_rows() -> None:
    rows = [
        {"table_name": f"table_{index}", "row_count": index}
        for index in range(1, 51)
    ]
    rows[26] = {"table_name": "order_status_history", "row_count": 2329}

    extrema = _numeric_extrema(rows, ["table_name", "row_count"])

    assert "table_name" not in extrema
    assert extrema["row_count"]["min"]["value"] == 1
    assert extrema["row_count"]["max"]["value"] == 2329
    assert (
        extrema["row_count"]["max"]["row"]["table_name"]
        == "order_status_history"
    )


def test_summarizer_payload_includes_full_result_extrema() -> None:
    rows = [
        {"table_name": f"table_{index}", "row_count": index}
        for index in range(1, 51)
    ]
    rows[40] = {"table_name": "largest_table", "row_count": 5000}
    client = MagicMock()
    client.complete.return_value = "Summary"

    answer = ResultSummarizer.summarize(
        question="Give me a summary of the full database",
        sql="SELECT ...",
        columns=["table_name", "row_count"],
        rows=rows,
        client=client,
    )

    assert answer == "Summary"
    messages = client.complete.call_args.args[0]
    payload_text = messages[-1]["content"].split("Use only the JSON rows below:\n", 1)[1]
    payload = json.loads(payload_text)
    assert len(payload["rows_preview"]) == 20
    maximum = payload["full_result_numeric_extrema"]["row_count"]["max"]
    assert maximum["value"] == 5000
    assert maximum["row"]["table_name"] == "largest_table"


def test_summarizer_prompt_forbids_chain_of_thought() -> None:
    client = MagicMock()
    client.complete.return_value = "Summary"

    ResultSummarizer.summarize(
        question="Revenue by region",
        sql="SELECT region, SUM(amount) ...",
        columns=["region", "revenue"],
        rows=[{"region": "North", "revenue": 10}],
        client=client,
    )

    system = client.complete.call_args.args[0][0]["content"]
    user = client.complete.call_args.args[0][1]["content"]
    assert "chain-of-thought" in system.lower()
    assert "We need to" in system
    assert "Do not restate instructions" in user


def test_summarizer_instructs_multi_dimension_cell_language() -> None:
    client = MagicMock()
    client.complete.return_value = "Summary"

    ResultSummarizer.summarize(
        question="Revenue by region and channel",
        sql="SELECT region, channel, SUM(amount) ...",
        columns=["region", "channel", "revenue"],
        rows=[{"region": "North", "channel": "Web", "revenue": 10}],
        client=client,
    )

    system = client.complete.call_args.args[0][0]["content"]
    assert "highest/lowest COMBINATION" in system
    assert "overall total" in system
