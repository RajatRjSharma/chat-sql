"""Tests for OpenRouter client."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from openai import APIError

from app.core.exceptions import OpenRouterError
from app.providers.openrouter import OpenRouterClient


def _mock_completion(content: str) -> MagicMock:
    choice = MagicMock()
    choice.message.content = content
    response = MagicMock()
    response.choices = [choice]
    return response


def _mock_embedding(vectors: list[list[float]]) -> MagicMock:
    response = MagicMock()
    response.data = []
    for i, vector in enumerate(vectors):
        item = MagicMock()
        item.index = i
        item.embedding = vector
        response.data.append(item)
    return response


class TestOpenRouterClient:
    def test_complete_success(self) -> None:
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _mock_completion("hello")
        client = OpenRouterClient(client=mock_client, api_key="k", base_url="http://x")
        assert client.complete([{"role": "user", "content": "hi"}]) == "hello"

    def test_complete_falls_back_on_api_error(self) -> None:
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = [
            APIError("fail", request=MagicMock(), body=None),
            _mock_completion("fallback ok"),
        ]
        client = OpenRouterClient(
            client=mock_client,
            api_key="k",
            base_url="http://x",
            llm_model="primary",
            llm_model_fallback="fallback",
        )
        assert client.complete([{"role": "user", "content": "hi"}]) == "fallback ok"
        assert mock_client.chat.completions.create.call_count == 2

    def test_complete_empty_raises(self) -> None:
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _mock_completion("")
        # empty content after strip is treated as an empty LLM response
        choice = MagicMock()
        choice.message.content = None
        response = MagicMock()
        response.choices = [choice]
        mock_client.chat.completions.create.return_value = response
        client = OpenRouterClient(client=mock_client, api_key="k", base_url="http://x")
        with pytest.raises(OpenRouterError, match="empty"):
            client.complete([{"role": "user", "content": "hi"}])

    def test_embed_success(self) -> None:
        mock_client = MagicMock()
        mock_client.embeddings.create.return_value = _mock_embedding([[0.1, 0.2], [0.3, 0.4]])
        client = OpenRouterClient(client=mock_client, api_key="k", base_url="http://x")
        assert client.embed(["a", "b"]) == [[0.1, 0.2], [0.3, 0.4]]

    def test_embed_empty_data_raises_openrouter_error(self) -> None:
        mock_client = MagicMock()
        mock_client.embeddings.create.side_effect = ValueError("No embedding data received")
        client = OpenRouterClient(client=mock_client, api_key="k", base_url="http://x")
        with pytest.raises(OpenRouterError, match="no data"):
            client.embed(["hello"])

    def test_embed_requests_float_encoding(self) -> None:
        mock_client = MagicMock()
        mock_client.embeddings.create.return_value = _mock_embedding([[0.1]])
        client = OpenRouterClient(client=mock_client, api_key="k", base_url="http://x")
        client.embed(["a"])
        kwargs = mock_client.embeddings.create.call_args.kwargs
        assert kwargs["encoding_format"] == "float"