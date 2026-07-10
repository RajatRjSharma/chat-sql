"""Domain exceptions for the analytics chat pipeline."""

from __future__ import annotations


class AppError(Exception):
    """Base application error."""


class OpenRouterError(AppError):
    """OpenRouter / LLM provider failure."""


class SqlValidationError(AppError):
    """Generated SQL failed safety checks."""


class WarehouseQueryError(AppError):
    """Warehouse query execution failed."""


class SchemaEmbeddingError(AppError):
    """Schema introspection or embedding failed."""


class ChatPipelineError(AppError):
    """Chat graph pipeline failed after retries or hard error."""
