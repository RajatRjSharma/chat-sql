"""User-provided warehouse / analytics database connection input."""

from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.core.schema import validate_optional_schema


class WarehouseConnectRequest(BaseModel):
    """
    Credentials supplied by the user to connect an analytics database.
    Never stored in .env — persisted encrypted in app.data_sources.
    schema_name is optional — leave empty to use the PostgreSQL connection default.
    """

    name: str = Field(..., min_length=1, max_length=100, examples=["Acme Sales Warehouse"])
    db_type: str = Field(default="postgres", pattern=r"^postgres$")
    host: str = Field(..., min_length=1, max_length=255, examples=["localhost"])
    port: int = Field(default=5432, ge=1, le=65535)
    database: str = Field(..., min_length=1, max_length=100, examples=["bi_warehouse"])
    schema_name: Optional[str] = Field(
        default=None,
        max_length=100,
        description="Target schema. Leave empty to use the PostgreSQL connection default.",
        examples=["sales"],
    )
    username: str = Field(..., min_length=1, max_length=100, examples=["bi_readonly"])
    password: str = Field(..., min_length=1, max_length=256)
    is_readonly: bool = Field(default=True)

    @field_validator("schema_name", mode="before")
    @classmethod
    def normalize_schema_name(cls, value: str | None) -> str | None:
        return validate_optional_schema(value)


class WarehouseConnectResponse(BaseModel):
    data_source_id: UUID
    name: str
    host: str
    port: int
    database: str
    schema_name: Optional[str] = None
    status: str = "connected"


class DataSourceSummary(BaseModel):
    id: UUID
    name: str
    host: str
    port: int
    database: str
    schema_name: Optional[str] = None
    db_type: str
    is_readonly: bool
    is_active: bool

    model_config = {"from_attributes": True}
