"""OpenRouter client — OpenAI-compatible chat and embeddings."""

from __future__ import annotations

from functools import lru_cache
from typing import Sequence

from openai import APIError, OpenAI

from app.config import settings
from app.core.exceptions import OpenRouterError


class OpenRouterClient:
    """Thin wrapper around the OpenAI SDK pointed at OpenRouter."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        llm_model: str | None = None,
        llm_model_fallback: str | None = None,
        embedding_model: str | None = None,
        client: OpenAI | None = None,
    ) -> None:
        self._api_key = api_key or settings.ai_api_key.get_secret_value()
        self._base_url = base_url or settings.ai_base_url
        self._llm_model = llm_model or settings.llm_model
        self._llm_model_fallback = llm_model_fallback or settings.llm_model_fallback
        self._embedding_model = embedding_model or settings.embedding_model
        self._client = client or OpenAI(api_key=self._api_key, base_url=self._base_url)

    def complete(
        self,
        messages: Sequence[dict[str, str]],
        *,
        temperature: float = 0.1,
        max_tokens: int = 2048,
        use_fallback: bool = False,
    ) -> str:
        """Chat completion. Retries once with fallback model on API failure."""
        model = self._llm_model_fallback if use_fallback else self._llm_model
        try:
            response = self._client.chat.completions.create(
                model=model,
                messages=list(messages),
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except APIError as exc:
            if use_fallback:
                # Final attempt: OpenRouter free router selects an available free model
                if model != "openrouter/free":
                    try:
                        response = self._client.chat.completions.create(
                            model="openrouter/free",
                            messages=list(messages),
                            temperature=temperature,
                            max_tokens=max_tokens,
                        )
                        choice = (
                            response.choices[0].message.content if response.choices else None
                        )
                        if choice:
                            return choice.strip()
                    except APIError:
                        pass
                raise OpenRouterError(f"LLM request failed: {exc}") from exc
            return self.complete(
                messages,
                temperature=temperature,
                max_tokens=max_tokens,
                use_fallback=True,
            )

        choice = response.choices[0].message.content if response.choices else None
        if not choice:
            raise OpenRouterError("LLM returned an empty response.")
        return choice.strip()

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed one or more texts. Returns vectors in input order."""
        if not texts:
            return []

        # Request float vectors; some OpenRouter providers mishandle base64 encoding.
        try:
            response = self._client.embeddings.create(
                model=self._embedding_model,
                input=list(texts),
                encoding_format="float",
            )
        except APIError as exc:
            raise OpenRouterError(
                f"Embedding request failed for model {self._embedding_model!r}: {exc}"
            ) from exc
        except ValueError as exc:
            # OpenAI SDK raises ValueError when the provider returns an empty embedding payload.
            raise OpenRouterError(
                f"Embedding provider returned no data for model {self._embedding_model!r}. "
                f"The model may be rate-limited or unavailable. Detail: {exc}"
            ) from exc

        if not response.data:
            # Retry per-text when the provider rejects batched embedding requests.
            if len(texts) > 1:
                return [self.embed_one(text) for text in texts]
            raise OpenRouterError(
                f"Embedding provider returned no data for model {self._embedding_model!r}."
            )

        by_index = {item.index: list(item.embedding) for item in response.data}
        try:
            return [by_index[i] for i in range(len(texts))]
        except KeyError as exc:
            raise OpenRouterError(
                "Embedding response indices do not match input texts."
            ) from exc

    def embed_one(self, text: str) -> list[float]:
        try:
            response = self._client.embeddings.create(
                model=self._embedding_model,
                input=text,
                encoding_format="float",
            )
        except APIError as exc:
            raise OpenRouterError(
                f"Embedding request failed for model {self._embedding_model!r}: {exc}"
            ) from exc
        except ValueError as exc:
            raise OpenRouterError(
                f"Embedding provider returned no data for model {self._embedding_model!r}. "
                f"Detail: {exc}"
            ) from exc

        if not response.data:
            raise OpenRouterError(
                f"Embedding provider returned no data for model {self._embedding_model!r}."
            )
        return list(response.data[0].embedding)


@lru_cache
def get_openrouter_client() -> OpenRouterClient:
    return OpenRouterClient()
