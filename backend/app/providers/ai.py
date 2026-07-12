"""AI provider facade for chat completions and embeddings.

Call sites use this module only — never a vendor SDK directly.
"""

from __future__ import annotations

import re
import time
from functools import lru_cache
from typing import Sequence

from langchain_core.embeddings import Embeddings
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from app.config import settings
from app.core.exceptions import AIProviderError

_ROLE_TO_MESSAGE: dict[str, type[BaseMessage]] = {
    "system": SystemMessage,
    "user": HumanMessage,
    "assistant": AIMessage,
}

_FREE_ROUTER_MODEL = "openrouter/free"
_RETRY_AFTER_RE = re.compile(r"retry_after_seconds(?:_raw)?['\":\s]+([0-9.]+)", re.I)


def _to_langchain_messages(messages: Sequence[dict[str, str]]) -> list[BaseMessage]:
    converted: list[BaseMessage] = []
    for item in messages:
        role = item.get("role", "user")
        content = item.get("content", "")
        cls = _ROLE_TO_MESSAGE.get(role, HumanMessage)
        converted.append(cls(content=content))
    return converted


def _message_text(content: object) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text", "")))
            else:
                parts.append(str(block))
        return "".join(parts).strip()
    return str(content).strip()


def _is_rate_limited(exc: BaseException) -> bool:
    text = str(exc)
    return "429" in text or "rate-limited" in text.lower() or "rate limited" in text.lower()


def _retry_after_seconds(exc: BaseException, *, default: float = 2.0, cap: float = 35.0) -> float:
    match = _RETRY_AFTER_RE.search(str(exc))
    if not match:
        return default
    try:
        return min(float(match.group(1)), cap)
    except ValueError:
        return default


def build_chat_model(
    *,
    model: str,
    temperature: float = 0.1,
    max_tokens: int = 2048,
    api_key: str | None = None,
    base_url: str | None = None,
) -> ChatOpenAI:
    return ChatOpenAI(
        model=model,
        api_key=api_key or settings.ai_api_key.get_secret_value(),
        base_url=base_url or settings.ai_base_url,
        temperature=temperature,
        max_tokens=max_tokens,
    )


def build_embeddings(
    *,
    model: str | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
) -> OpenAIEmbeddings:
    return OpenAIEmbeddings(
        model=model or settings.embedding_model,
        api_key=api_key or settings.ai_api_key.get_secret_value(),
        base_url=base_url or settings.ai_base_url,
        check_embedding_ctx_length=False,
        model_kwargs={"encoding_format": "float"},
    )


class AIClient:
    """Application facade for chat and embeddings."""

    def __init__(
        self,
        *,
        chat_model: BaseChatModel | None = None,
        fallback_chat_model: BaseChatModel | None = None,
        embeddings: Embeddings | None = None,
        llm_model: str | None = None,
        llm_model_fallback: str | None = None,
        embedding_model: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> None:
        self._api_key = api_key or settings.ai_api_key.get_secret_value()
        self._base_url = base_url or settings.ai_base_url
        self._llm_model = llm_model or settings.llm_model
        self._llm_model_fallback = llm_model_fallback or settings.llm_model_fallback
        self._embedding_model = embedding_model or settings.embedding_model

        self._chat = chat_model or build_chat_model(
            model=self._llm_model,
            api_key=self._api_key,
            base_url=self._base_url,
        )
        self._fallback_chat = fallback_chat_model or build_chat_model(
            model=self._llm_model_fallback,
            api_key=self._api_key,
            base_url=self._base_url,
        )
        self._embeddings = embeddings or build_embeddings(
            model=self._embedding_model,
            api_key=self._api_key,
            base_url=self._base_url,
        )
        self._enable_extra_router = (
            chat_model is None
            and fallback_chat_model is None
            and self._llm_model != _FREE_ROUTER_MODEL
            and self._llm_model_fallback != _FREE_ROUTER_MODEL
        )

    def complete(
        self,
        messages: Sequence[dict[str, str]],
        *,
        temperature: float = 0.1,
        max_tokens: int = 2048,
    ) -> str:
        """Chat completion with primary, then configured fallback models."""
        lc_messages = _to_langchain_messages(messages)
        errors: list[str] = []

        for model in self._chat_models_for_attempt(temperature, max_tokens):
            text, error = self._invoke_with_rate_limit_retry(
                model,
                lc_messages,
                max_tokens=max_tokens,
                temperature=temperature,
            )
            if text:
                return text
            if error:
                errors.append(error)

        detail = "; ".join(errors) if errors else "unknown error"
        raise AIProviderError(f"AI request failed: {detail}")

    def _invoke_with_rate_limit_retry(
        self,
        model: BaseChatModel,
        lc_messages: list[BaseMessage],
        *,
        max_tokens: int,
        temperature: float,
    ) -> tuple[str | None, str | None]:
        label = getattr(model, "model_name", None) or getattr(model, "model", None) or str(model)
        for attempt in range(2):
            try:
                response = model.invoke(lc_messages)
                text = _message_text(getattr(response, "content", None))
                if text:
                    return text, None
                # Some free models return empty at very low max_tokens; retry once higher.
                if attempt == 0 and max_tokens < 64:
                    model = self._bound_chat(model, temperature, max(64, max_tokens * 4))
                    continue
                return None, f"{label} returned empty content"
            except Exception as exc:  # noqa: BLE001
                if attempt == 0 and _is_rate_limited(exc):
                    time.sleep(_retry_after_seconds(exc))
                    continue
                return None, str(exc)
        return None, f"{label} failed"

    def _chat_models_for_attempt(
        self,
        temperature: float,
        max_tokens: int,
    ) -> list[BaseChatModel]:
        models: list[BaseChatModel] = [
            self._bound_chat(self._chat, temperature, max_tokens),
            self._bound_chat(self._fallback_chat, temperature, max_tokens),
        ]
        if self._enable_extra_router:
            models.append(
                build_chat_model(
                    model=_FREE_ROUTER_MODEL,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    api_key=self._api_key,
                    base_url=self._base_url,
                )
            )
        return models

    @staticmethod
    def _bound_chat(
        model: BaseChatModel,
        temperature: float,
        max_tokens: int,
    ) -> BaseChatModel:
        try:
            return model.bind(temperature=temperature, max_tokens=max_tokens)
        except Exception:  # noqa: BLE001
            return model

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        try:
            vectors = self._embeddings.embed_documents(list(texts))
        except Exception as exc:  # noqa: BLE001
            if len(texts) > 1:
                return [self.embed_one(text) for text in texts]
            raise AIProviderError(
                f"Embedding request failed for model {self._embedding_model!r}: {exc}"
            ) from exc

        if not vectors or any(not vector for vector in vectors):
            if len(texts) > 1:
                return [self.embed_one(text) for text in texts]
            raise AIProviderError(
                f"Embedding provider returned no data for model {self._embedding_model!r}."
            )
        return [list(vector) for vector in vectors]

    def embed_one(self, text: str) -> list[float]:
        try:
            vector = self._embeddings.embed_query(text)
        except Exception as exc:  # noqa: BLE001
            raise AIProviderError(
                f"Embedding request failed for model {self._embedding_model!r}: {exc}"
            ) from exc
        if not vector:
            raise AIProviderError(
                f"Embedding provider returned no data for model {self._embedding_model!r}."
            )
        return list(vector)


@lru_cache
def get_ai_client() -> AIClient:
    return AIClient()
