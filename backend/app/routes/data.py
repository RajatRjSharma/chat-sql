"""API routes for user-provided analytics database connections."""

from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.exceptions import AIProviderError, SchemaEmbeddingError, UploadError
from app.database import get_db
from app.schemas.chat import (
    EmbedSchemaRequest,
    EmbedSchemaResponse,
    SuggestedQuestionsResponse,
)
from app.schemas.data_source import (
    DataSourceSummary,
    WarehouseConnectRequest,
    WarehouseConnectResponse,
)
from app.schemas.upload import UploadResponse
from app.services.data_source_service import DataSourceService
from app.services.schema_embedding_service import SchemaEmbeddingService
from app.services.suggestion_service import SuggestionService
from app.services.upload_service import UploadService

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


@router.post("/upload", response_model=UploadResponse)
async def upload_tabular_file(
    db: AsyncSession = Depends(get_db),
    file: UploadFile = File(..., description="CSV or Excel (.xlsx) file"),
    name: str | None = Form(
        default=None,
        description="Optional display name for the data source",
    ),
) -> UploadResponse:
    """
    Upload CSV/Excel → load into an isolated warehouse schema → register a
    read-only data source. Call POST /api/data/embed-schema next (same as connect).
    """
    filename = file.filename or "upload.csv"
    try:
        content = await file.read()
        if len(content) > settings.upload_max_bytes:
            raise UploadError(
                f"File exceeds the {settings.upload_max_bytes // (1024 * 1024)} MB limit."
            )
        result = await UploadService.upload(
            db,
            filename=filename,
            content=content,
            display_name=name,
        )
        return UploadResponse.model_validate(result)
    except UploadError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Upload failed: {exc}",
        ) from exc
    finally:
        await file.close()


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
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except (SchemaEmbeddingError, AIProviderError) as exc:
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
    sources = await DataSourceService.list_active_summaries(db)
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


@router.get(
    "/sources/{data_source_id}/suggested-questions",
    response_model=SuggestedQuestionsResponse,
)
async def suggested_questions(
    data_source_id: UUID,
    limit: int = Query(6, ge=1, le=12),
    db: AsyncSession = Depends(get_db),
) -> SuggestedQuestionsResponse:
    """
    Schema-aware suggested prompts for the analyst sidebar.

    Built from embedded table chunks (+ recent successful questions), not an LLM
    call — stays useful under free-tier rate limits.
    """
    try:
        result = await SuggestionService.suggest_for_data_source(
            db, data_source_id, limit=limit
        )
        return SuggestedQuestionsResponse.model_validate(result)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
