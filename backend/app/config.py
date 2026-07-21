"""Application configuration loaded from environment variables."""

from functools import lru_cache
from pathlib import Path
from typing import List, Optional

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.db_url import build_postgres_url, to_sync_url
from app.core.schema import validate_optional_schema

_PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """
    Application-level configuration only.
    Warehouse/analytics DB credentials are user-provided at runtime — not stored here.
    """

    model_config = SettingsConfigDict(
        env_file=str(_PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_env: str = Field(default="local", alias="APP_ENV")
    cors_origins: str = Field(
        default="http://localhost:3000",
        alias="CORS_ORIGINS",
    )

    # Project database (ORM + Alembic) — discrete connection fields
    app_db_host: str = Field(default="localhost", alias="APP_DB_HOST")
    app_db_port: int = Field(default=5432, alias="APP_DB_PORT", ge=1, le=65535)
    app_db_name: str = Field(default="bi_app", alias="APP_DB_NAME")
    app_db_user: str = Field(default="postgres", alias="APP_DB_USER")
    app_db_password: SecretStr = Field(default="postgres", alias="APP_DB_PASSWORD")
    # Optional — leave empty to use PostgreSQL default schema (public)
    app_db_schema: Optional[str] = Field(default=None, alias="APP_DB_SCHEMA")

    # Encrypts user-provided warehouse passwords stored in app.data_sources
    credentials_secret: SecretStr = Field(alias="CREDENTIALS_SECRET")

    # AI provider
    ai_base_url: str = Field(
        default="https://openrouter.ai/api/v1",
        alias="AI_BASE_URL",
    )
    ai_api_key: SecretStr = Field(alias="AI_API_KEY")
    llm_model: str = Field(
        default="openai/gpt-oss-20b:free",
        alias="LLM_MODEL",
    )
    llm_model_fallback: str = Field(
        default="google/gemma-4-31b-it:free",
        alias="LLM_MODEL_FALLBACK",
    )
    embedding_model: str = Field(
        default="nvidia/llama-nemotron-embed-vl-1b-v2:free",
        alias="EMBEDDING_MODEL",
    )
    embedding_dimensions: int = Field(default=2048, alias="EMBEDDING_DIMENSIONS")

    # Chat / RAG pipeline knobs
    rag_top_k: int = Field(default=5, alias="RAG_TOP_K", ge=1, le=20)
    sql_max_attempts: int = Field(default=3, alias="SQL_MAX_ATTEMPTS", ge=1, le=5)
    warehouse_max_rows: int = Field(default=500, alias="WAREHOUSE_MAX_ROWS", ge=1, le=5000)
    chat_history_limit: int = Field(default=5, alias="CHAT_HISTORY_LIMIT", ge=0, le=20)

    # CSV/Excel upload target (server-side write; chat uses query user)
    upload_wh_host: str = Field(default="localhost", alias="UPLOAD_WH_HOST")
    upload_wh_port: int = Field(default=5433, alias="UPLOAD_WH_PORT", ge=1, le=65535)
    upload_wh_database: str = Field(default="bi_warehouse", alias="UPLOAD_WH_DATABASE")
    upload_wh_user: str = Field(default="bi_uploader", alias="UPLOAD_WH_USER")
    upload_wh_password: SecretStr = Field(
        default="uploader_pass", alias="UPLOAD_WH_PASSWORD"
    )
    upload_wh_query_user: str = Field(default="bi_readonly", alias="UPLOAD_WH_QUERY_USER")
    upload_wh_query_password: SecretStr = Field(
        default="readonly_pass", alias="UPLOAD_WH_QUERY_PASSWORD"
    )
    upload_max_bytes: int = Field(
        default=10 * 1024 * 1024, alias="UPLOAD_MAX_BYTES", ge=1024, le=50 * 1024 * 1024
    )
    upload_max_rows: int = Field(default=50_000, alias="UPLOAD_MAX_ROWS", ge=1, le=200_000)

    @field_validator("app_db_schema", mode="before")
    @classmethod
    def normalize_app_db_schema(cls, value: str | None) -> str | None:
        return validate_optional_schema(value)

    @property
    def cors_origins_list(self) -> List[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def is_local(self) -> bool:
        return self.app_env == "local"

    @property
    def database_url(self) -> str:
        """Async SQLAlchemy URL built from discrete project DB credentials."""
        return build_postgres_url(
            host=self.app_db_host,
            port=self.app_db_port,
            database=self.app_db_name,
            username=self.app_db_user,
            password=self.app_db_password.get_secret_value(),
            driver="asyncpg",
        )

    @property
    def alembic_database_url(self) -> str:
        """Sync driver URL for Alembic migrations."""
        return to_sync_url(self.database_url)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
