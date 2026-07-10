"""API routes for user-provided analytics database connections."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import OpenRouterError, SchemaEmbeddingError
from app.database import get_db
from app.schemas.chat import EmbedSchemaRequest, EmbedSchemaResponse
from app.schemas.data_source import (
    DataSourceSummary,
    WarehouseConnectRequest,
    WarehouseConnectResponse,
)
from app.services.data_source_service import DataSourceService
from app.services.schema_embedding_service import SchemaEmbeddingService

router = APIRouter(prefix="/api/data", tags=["data"])


@router.post("/connect", response_model=WarehouseConnectResponse)
async def connect_warehouse(
    request: WarehouseConnectRequest,
    db: AsyncSession = Depends(get_db),
) -> WarehouseConnectResponse:
    """
    Connect a user-provided analytics database.
    Credentials are validated, then stored encrypted in the project DB.
    """
    try:
        return await DataSourceService.connect(db, request)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Could not connect to warehouse: {exc}",
        ) from exc


@router.post("/embed-schema", response_model=EmbedSchemaResponse)
async def embed_schema(
    request: EmbedSchemaRequest,
    db: AsyncSession = Depends(get_db),
) -> EmbedSchemaResponse:
    """
    Introspect the connected warehouse schema, embed table chunks, and store
    vectors in schema_embeddings for RAG.
    """
    try:
        count = await SchemaEmbeddingService.embed_data_source(db, request.data_source_id)
        return EmbedSchemaResponse(
            data_source_id=request.data_source_id,
            chunks_embedded=count,
            status="ok",
        )
    except ValueError as exc:
        # Missing or inactive data source.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except (SchemaEmbeddingError, OpenRouterError) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Schema embedding failed: {exc}",
        ) from exc


@router.get("/sources", response_model=list[DataSourceSummary])
async def list_data_sources(db: AsyncSession = Depends(get_db)) -> list[DataSourceSummary]:
    """List active user-connected data sources (passwords never returned)."""
    sources = await DataSourceService.list_active(db)
    return [DataSourceSummary.model_validate(source) for source in sources]


@router.get("/sources/{data_source_id}", response_model=DataSourceSummary)
async def get_data_source(
    data_source_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> DataSourceSummary:
    try:
        source = await DataSourceService.get_active(db, data_source_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return DataSourceSummary.model_validate(source)
