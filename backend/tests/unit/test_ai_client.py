"""Tests for AIClient."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.core.exceptions import AIProviderError
from app.providers.ai import AIClient


def _chat_model(content: str | None = "hello", *, error: Exception | None = None) -> MagicMock:
    model = MagicMock()
    model.bind.return_value = model
    model.model_name = "mock-model"
    if error is not None:
        model.invoke.side_effect = error
    else:
        response = MagicMock()
        response.content = content
        model.invoke.return_value = response
    return model


class TestAIClient:
    def test_complete_success(self) -> None:
        client = AIClient(
            chat_model=_chat_model("hello"),
            fallback_chat_model=_chat_model("unused"),
            embeddings=MagicMock(),
        )
        assert client.complete([{"role": "user", "content": "hi"}]) == "hello"

    def test_complete_falls_back_on_error(self) -> None:
        client = AIClient(
            chat_model=_chat_model(error=RuntimeError("primary down")),
            fallback_chat_model=_chat_model("fallback ok"),
            embeddings=MagicMock(),
        )
        assert client.complete([{"role": "user", "content": "hi"}]) == "fallback ok"

    def test_complete_retries_rate_limit_then_succeeds(self) -> None:
        model = MagicMock()
        model.bind.return_value = model
        model.model_name = "mock-model"
        ok = MagicMock()
        ok.content = "ok after retry"
        model.invoke.side_effect = [
            RuntimeError("Error code: 429 - rate-limited retry_after_seconds: 0.01"),
            ok,
        ]
        client = AIClient(
            chat_model=model,
            fallback_chat_model=_chat_model("unused"),
            embeddings=MagicMock(),
        )
        assert client.complete([{"role": "user", "content": "hi"}]) == "ok after retry"
        assert model.invoke.call_count == 2

    def test_complete_retries_empty_content_with_higher_max_tokens(self) -> None:
        model = MagicMock()
        model.bind.side_effect = lambda **_kwargs: model
        model.model_name = "mock-model"
        empty = MagicMock()
        empty.content = ""
        ok = MagicMock()
        ok.content = "ok"
        model.invoke.side_effect = [empty, ok]
        client = AIClient(
            chat_model=model,
            fallback_chat_model=_chat_model("unused"),
            embeddings=MagicMock(),
        )
        assert client.complete([{"role": "user", "content": "hi"}], max_tokens=8) == "ok"
        assert model.invoke.call_count == 2

    def test_complete_empty_raises(self) -> None:
        client = AIClient(
            chat_model=_chat_model(None),
            fallback_chat_model=_chat_model(""),
            embeddings=MagicMock(),
        )
        with pytest.raises(AIProviderError, match="failed"):
            client.complete([{"role": "user", "content": "hi"}])

    def test_embed_success(self) -> None:
        embeddings = MagicMock()
        embeddings.embed_documents.return_value = [[0.1, 0.2], [0.3, 0.4]]
        client = AIClient(
            chat_model=_chat_model(),
            fallback_chat_model=_chat_model(),
            embeddings=embeddings,
        )
        assert client.embed(["a", "b"]) == [[0.1, 0.2], [0.3, 0.4]]

    def test_embed_failure_raises(self) -> None:
        embeddings = MagicMock()
        embeddings.embed_documents.side_effect = RuntimeError("No embedding data received")
        embeddings.embed_query.side_effect = RuntimeError("No embedding data received")
        client = AIClient(
            chat_model=_chat_model(),
            fallback_chat_model=_chat_model(),
            embeddings=embeddings,
        )
        with pytest.raises(AIProviderError, match="Embedding"):
            client.embed(["hello"])

    def test_embed_one_success(self) -> None:
        embeddings = MagicMock()
        embeddings.embed_query.return_value = [0.1, 0.2]
        client = AIClient(
            chat_model=_chat_model(),
            fallback_chat_model=_chat_model(),
            embeddings=embeddings,
        )
        assert client.embed_one("hello") == [0.1, 0.2]
