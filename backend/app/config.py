"""Application configuration loaded from environment variables."""

from functools import lru_cache
from pathlib import Path

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
    app_db_schema: str | None = Field(default=None, alias="APP_DB_SCHEMA")

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
    # Optional fast/small model for IntentRouter + EntityLinker (defaults to LLM_MODEL).
    llm_router_model: str | None = Field(default=None, alias="LLM_ROUTER_MODEL")
    # Prefer small-token LLM for soft NL (intent/entities/scope). Heuristics = fallback only.
    nlp_prefer_llm: bool = Field(default=True, alias="NLP_PREFER_LLM")
    nlp_router_max_tokens: int = Field(
        default=120, alias="NLP_ROUTER_MAX_TOKENS", ge=64, le=512
    )
    nlp_entity_max_tokens: int = Field(
        default=180, alias="NLP_ENTITY_MAX_TOKENS", ge=64, le=512
    )
    nlp_intent_confidence_trust: float = Field(
        default=0.55,
        alias="NLP_INTENT_CONFIDENCE_TRUST",
        ge=0.0,
        le=1.0,
        description="Trust IntentRouter pre_decision at/above this confidence",
    )
    embedding_model: str = Field(
        default="nvidia/llama-nemotron-embed-vl-1b-v2:free",
        alias="EMBEDDING_MODEL",
    )
    embedding_dimensions: int = Field(default=2048, alias="EMBEDDING_DIMENSIONS")

    # Chat / RAG pipeline knobs
    rag_top_k: int = Field(default=5, alias="RAG_TOP_K", ge=1, le=20)
    rag_expand_hops: int = Field(default=1, alias="RAG_EXPAND_HOPS", ge=0, le=3)
    rag_max_tables: int = Field(default=15, alias="RAG_MAX_TABLES", ge=1, le=50)
    rag_expand_on_retry: bool = Field(default=True, alias="RAG_EXPAND_ON_RETRY")
    sql_max_attempts: int = Field(default=3, alias="SQL_MAX_ATTEMPTS", ge=1, le=5)
    warehouse_max_rows: int = Field(default=500, alias="WAREHOUSE_MAX_ROWS", ge=1, le=5000)
    chat_history_limit: int = Field(default=5, alias="CHAT_HISTORY_LIMIT", ge=0, le=20)
    # Modest pools (each asyncpg connection holds buffers). Raise if you need more concurrency.
    db_pool_size: int = Field(default=5, alias="DB_POOL_SIZE", ge=1, le=20)
    db_max_overflow: int = Field(default=5, alias="DB_MAX_OVERFLOW", ge=0, le=20)
    warehouse_connect_timeout_seconds: int = Field(
        default=10,
        alias="WAREHOUSE_CONNECT_TIMEOUT_SECONDS",
        ge=1,
        le=60,
    )
    warehouse_statement_timeout_ms: int = Field(
        default=15_000,
        alias="WAREHOUSE_STATEMENT_TIMEOUT_MS",
        ge=1000,
        le=120_000,
    )
    # None → allow private/loopback only when APP_ENV=local (demo Docker)
    warehouse_allow_private_hosts: bool | None = Field(
        default=None,
        alias="WAREHOUSE_ALLOW_PRIVATE_HOSTS",
    )

    # CSV/Excel upload target (legacy — uploads now use APP_DB_*).
    # Kept so existing env files do not break; unused by the upload path.
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

    # Auth (JWT + Gmail SMTP OTP — no Google OIDC)
    jwt_secret: SecretStr = Field(
        default="dev-local-jwt-secret-change-in-production",
        alias="JWT_SECRET",
    )
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")
    jwt_expire_minutes: int = Field(
        default=30,
        alias="JWT_EXPIRE_MINUTES",
        ge=5,
        le=1440,
        description="Access token TTL (short-lived; use refresh)",
    )
    jwt_refresh_expire_minutes: int = Field(
        default=60 * 24 * 7,
        alias="JWT_REFRESH_EXPIRE_MINUTES",
        ge=60,
        le=60 * 24 * 30,
    )
    jwt_issuer: str = Field(default="voice-driven-data-analyst", alias="JWT_ISSUER")
    # httpOnly cookie session — prefer first-party via Next /api rewrite (mobile-safe).
    # Use AUTH_COOKIE_SAMESITE=lax with the proxy. SameSite=none is for direct cross-site
    # API calls only and is unreliable on iOS Safari / Android Chrome.
    auth_access_cookie_name: str = Field(
        default="vdda_access",
        alias="AUTH_ACCESS_COOKIE_NAME",
    )
    auth_refresh_cookie_name: str = Field(
        default="vdda_refresh",
        alias="AUTH_REFRESH_COOKIE_NAME",
    )
    auth_cookie_samesite: str = Field(
        default="lax",
        alias="AUTH_COOKIE_SAMESITE",
        description=(
            "lax with same-origin proxy; none only for direct cross-site API "
            "(needs Secure)"
        ),
    )
    auth_cookie_secure: bool | None = Field(
        default=None,
        alias="AUTH_COOKIE_SECURE",
        description="None → Secure off only when APP_ENV=local",
    )
    auth_rate_limit_per_minute: int = Field(
        default=20,
        alias="AUTH_RATE_LIMIT_PER_MINUTE",
        ge=5,
        le=120,
    )
    connect_rate_limit_per_minute: int = Field(
        default=10,
        alias="CONNECT_RATE_LIMIT_PER_MINUTE",
        ge=1,
        le=120,
    )
    upload_rate_limit_per_minute: int = Field(
        default=5,
        alias="UPLOAD_RATE_LIMIT_PER_MINUTE",
        ge=1,
        le=60,
    )
    chat_rate_limit_per_minute: int = Field(
        default=30,
        alias="CHAT_RATE_LIMIT_PER_MINUTE",
        ge=1,
        le=300,
    )
    embed_rate_limit_per_minute: int = Field(
        default=10,
        alias="EMBED_RATE_LIMIT_PER_MINUTE",
        ge=1,
        le=120,
    )
    tts_rate_limit_per_minute: int = Field(
        default=10,
        alias="TTS_RATE_LIMIT_PER_MINUTE",
        ge=1,
        le=60,
    )

    # Offline Piper TTS (bundled voice under backend/models/piper/)
    # Defaults favor snappy Speak; on ≤512MB hosts set TTS_PRELOAD=false if you OOM.
    tts_enabled: bool = Field(default=True, alias="TTS_ENABLED")
    tts_preload: bool = Field(
        default=True,
        alias="TTS_PRELOAD",
        description="Load Piper at process start so first Speak is warm",
    )
    tts_voice_path: str = Field(
        default="models/piper/en_US-amy-low.onnx",
        alias="TTS_VOICE_PATH",
        description="Path to Piper .onnx voice, relative to backend/ or absolute",
    )
    tts_max_chars: int = Field(
        default=180,
        alias="TTS_MAX_CHARS",
        ge=40,
        le=2000,
        description=(
            "Max characters per synthesis chunk after the first. "
            "Full answer is still spoken via multiple chunks."
        ),
    )
    tts_first_chunk_chars: int = Field(
        default=48,
        alias="TTS_FIRST_CHUNK_CHARS",
        ge=24,
        le=500,
        description="Very short first chunk so audio starts sooner on small CPUs",
    )
    tts_length_scale: float = Field(
        default=0.78,
        alias="TTS_LENGTH_SCALE",
        ge=0.5,
        le=2.0,
        description="Piper speaking rate; <1 = faster/shorter audio (less CPU)",
    )
    tts_onnx_threads: int = Field(
        default=1,
        alias="TTS_ONNX_THREADS",
        ge=1,
        le=8,
        description="ONNX Runtime intra-op threads (1 is best on tiny CPUs)",
    )
    tts_warmup_enabled: bool = Field(default=True, alias="TTS_WARMUP_ENABLED")
    tts_warmup_text: str = Field(
        default="Ready.",
        alias="TTS_WARMUP_TEXT",
        max_length=120,
    )
    tts_wav_cache_max: int = Field(
        default=12,
        alias="TTS_WAV_CACHE_MAX",
        ge=0,
        le=32,
        description="Max distinct answers kept as WAV chunk lists in RAM",
    )
    tts_wav_cache_max_bytes: int = Field(
        default=12_000_000,
        alias="TTS_WAV_CACHE_MAX_BYTES",
        ge=0,
        le=64_000_000,
        description="Hard byte budget for the in-process WAV cache (~12MB default)",
    )

    smtp_host: str = Field(default="smtp.gmail.com", alias="SMTP_HOST")
    smtp_port: int = Field(default=587, alias="SMTP_PORT", ge=1, le=65535)
    smtp_user: str = Field(default="", alias="SMTP_USER")
    smtp_password: SecretStr = Field(default="", alias="SMTP_PASSWORD")
    smtp_from: str = Field(default="", alias="SMTP_FROM")
    smtp_use_tls: bool = Field(default=True, alias="SMTP_USE_TLS")
    otp_expire_minutes: int = Field(default=10, alias="OTP_EXPIRE_MINUTES", ge=1, le=60)
    otp_length: int = Field(default=6, alias="OTP_LENGTH", ge=4, le=8)
    otp_max_attempts: int = Field(
        default=5,
        alias="OTP_MAX_ATTEMPTS",
        ge=3,
        le=20,
        description="Max wrong OTP guesses before the code is invalidated",
    )
    # When false, register marks the user verified and skips SMTP (local / SMTP-blocked hosts).
    # Blocked at boot when APP_ENV=production and REGISTRATION_ENABLED=true.
    email_otp_enabled: bool = Field(default=True, alias="EMAIL_OTP_ENABLED")
    # When false (default), POST /api/auth/register is rejected and the UI hides sign-up.
    # Set REGISTRATION_ENABLED=true to allow new accounts.
    registration_enabled: bool = Field(default=False, alias="REGISTRATION_ENABLED")

    @field_validator("app_db_schema", mode="before")
    @classmethod
    def normalize_app_db_schema(cls, value: str | None) -> str | None:
        return validate_optional_schema(value)

    @field_validator("llm_router_model", mode="before")
    @classmethod
    def normalize_llm_router_model(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @property
    def effective_llm_router_model(self) -> str:
        """Model used for IntentRouter / EntityLinker (falls back to LLM_MODEL)."""
        return self.llm_router_model or self.llm_model

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def is_local(self) -> bool:
        return self.app_env.lower() == "local"

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() in {"production", "prod"}

    def assert_production_ready(self) -> None:
        """Fail closed on weak auth config when APP_ENV is production."""
        if not self.is_production:
            return
        secret = self.jwt_secret.get_secret_value()
        weak_defaults = {
            "dev-local-jwt-secret-change-in-production",
            "change-me-to-a-long-random-jwt-secret",
            "test-jwt-secret-at-least-32-chars!!",
        }
        if len(secret) < 32 or secret in weak_defaults:
            raise RuntimeError(
                "JWT_SECRET must be a unique secret (≥32 chars) when APP_ENV=production"
            )
        if self.registration_enabled and not self.email_otp_enabled:
            raise RuntimeError(
                "EMAIL_OTP_ENABLED=false is not allowed when APP_ENV=production "
                "and REGISTRATION_ENABLED=true (would auto-verify new accounts)"
            )

    @property
    def allow_private_warehouse_hosts(self) -> bool:
        """Private/loopback warehouse hosts: on by default only in local."""
        if self.warehouse_allow_private_hosts is not None:
            return self.warehouse_allow_private_hosts
        return self.is_local

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

    @property
    def resolved_tts_voice_path(self) -> Path:
        """Absolute path to the Piper ONNX voice file."""
        path = Path(self.tts_voice_path)
        if path.is_absolute():
            return path
        backend_root = Path(__file__).resolve().parents[1]
        return (backend_root / path).resolve()


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
