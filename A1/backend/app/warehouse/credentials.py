"""Warehouse connection credentials — user-provided, not from .env."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import quote_plus, urlunparse

from app.core.schema import validate_optional_schema
from app.models.data_source import DataSource
from app.schemas.data_source import WarehouseConnectRequest
from app.security import decrypt_credential


@dataclass(frozen=True, slots=True)
class WarehouseCredentials:
    """Resolved credentials for connecting to a user warehouse database."""

    name: str
    db_type: str
    host: str
    port: int
    database: str
    schema_name: str | None
    username: str
    password: str
    is_readonly: bool = True

    @classmethod
    def from_request(cls, request: WarehouseConnectRequest) -> WarehouseCredentials:
        return cls(
            name=request.name,
            db_type=request.db_type,
            host=request.host,
            port=request.port,
            database=request.database,
            schema_name=request.schema_name,
            username=request.username,
            password=request.password,
            is_readonly=request.is_readonly,
        )

    @classmethod
    def from_data_source(cls, data_source: DataSource, password: str) -> WarehouseCredentials:
        return cls(
            name=data_source.name,
            db_type=data_source.db_type,
            host=data_source.host,
            port=data_source.port,
            database=data_source.database,
            schema_name=validate_optional_schema(data_source.schema_name),
            username=data_source.username or "",
            password=password,
            is_readonly=data_source.is_readonly,
        )

    @classmethod
    def from_data_source_decrypted(cls, data_source: DataSource) -> WarehouseCredentials:
        if not data_source.username or not data_source.password_encrypted:
            raise ValueError("Data source is missing stored credentials.")
        return cls.from_data_source(
            data_source,
            decrypt_credential(data_source.password_encrypted),
        )

    def connection_url(self) -> str:
        """Build a psycopg2-compatible PostgreSQL URL."""
        user = quote_plus(self.username)
        password = quote_plus(self.password)
        netloc = f"{user}:{password}@{self.host}:{self.port}"
        return urlunparse(("postgresql", netloc, f"/{self.database}", "", "", ""))


@dataclass(frozen=True, slots=True)
class WarehouseConnectionInfo:
    """Connection details used by services and health checks."""

    name: str
    host: str
    port: int
    database: str
    schema_name: str | None
    connection_url: str
    is_readonly: bool

    @classmethod
    def from_credentials(cls, credentials: WarehouseCredentials) -> WarehouseConnectionInfo:
        return cls(
            name=credentials.name,
            host=credentials.host,
            port=credentials.port,
            database=credentials.database,
            schema_name=credentials.schema_name,
            connection_url=credentials.connection_url(),
            is_readonly=credentials.is_readonly,
        )
