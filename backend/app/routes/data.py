"""API routes for user-provided analytics database connections."""

from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.exceptions import AIProviderError, SchemaEmbeddingError, UploadError
from app.database import get_db
from app.deps.auth import get_current_user
from app.models.user import User
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
from app.security.http_errors import (
    GENERIC_CONNECT,
    GENERIC_EMBED,
    GENERIC_UPLOAD,
    raise_http,
    safe_public_detail,
)
from app.security.rate_limit import (
    enforce_connect_rate_limit,
    enforce_embed_rate_limit,
    enforce_upload_rate_limit,
)
from app.services.data_source_service import DataSourceService
from app.services.schema_embedding_service import SchemaEmbeddingService
from app.services.suggestion_service import SuggestionService
from app.services.upload_service import UploadService

router = APIRouter(prefix="/api/data", tags=["data"])


@router.post("/connect", response_model=WarehouseConnectResponse)
async def connect_warehouse(
    request: WarehouseConnectRequest,
    raw: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> WarehouseConnectResponse:
    """
    Connect a user-provided analytics database.
    Credentials are validated, then stored encrypted in the project DB.
    """
    enforce_connect_rate_limit(raw, user_id=str(current_user.id))
    try:
        return await DataSourceService.connect(db, request, user_id=current_user.id)
    except ValueError as exc:
        raise_http(
            status.HTTP_400_BAD_REQUEST,
            detail=safe_public_detail(exc, fallback="Invalid warehouse connection."),
            exc=exc,
        )
    except Exception as exc:
        raise_http(
            status.HTTP_502_BAD_GATEWAY,
            detail=GENERIC_CONNECT,
            exc=exc,
        )


@router.post("/upload", response_model=UploadResponse)
async def upload_tabular_file(
    raw: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
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
    enforce_upload_rate_limit(raw, user_id=str(current_user.id))
    filename = file.filename or "upload.csv"
    try:
        content = await file.read()
        if len(content) > settings.upload_max_bytes:
            raise UploadError(
                f"File exceeds the {settings.upload_max_bytes // (1024 * 1024)} MB limit."
            )
        result = await UploadService.upload(
            db,
            user_id=current_user.id,
            filename=filename,
            content=content,
            display_name=name,
        )
        return UploadResponse.model_validate(result)
    except UploadError as exc:
        raise_http(
            status.HTTP_400_BAD_REQUEST,
            detail=safe_public_detail(exc, fallback=GENERIC_UPLOAD),
            exc=exc,
        )
    except ValueError as exc:
        raise_http(
            status.HTTP_400_BAD_REQUEST,
            detail=safe_public_detail(exc, fallback=GENERIC_UPLOAD),
            exc=exc,
        )
    except Exception as exc:
        raise_http(status.HTTP_502_BAD_GATEWAY, detail=GENERIC_UPLOAD, exc=exc)
    finally:
        await file.close()


@router.post("/embed-schema", response_model=EmbedSchemaResponse)
async def embed_schema(
    request: EmbedSchemaRequest,
    raw: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> EmbedSchemaResponse:
    """
    Introspect the connected warehouse schema, embed table chunks, and store
    vectors in schema_embeddings for RAG.
    """
    enforce_embed_rate_limit(raw, user_id=str(current_user.id))
    try:
        count = await SchemaEmbeddingService.embed_data_source(
            db,
            request.data_source_id,
            user_id=current_user.id,
        )
        return EmbedSchemaResponse(
            data_source_id=request.data_source_id,
            chunks_embedded=count,
            status="ok",
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except (SchemaEmbeddingError, AIProviderError) as exc:
        raise_http(
            status.HTTP_502_BAD_GATEWAY,
            detail=safe_public_detail(exc, fallback=GENERIC_EMBED),
            exc=exc,
        )
    except Exception as exc:
        raise_http(status.HTTP_502_BAD_GATEWAY, detail=GENERIC_EMBED, exc=exc)


@router.get("/sources", response_model=list[DataSourceSummary])
async def list_data_sources(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[DataSourceSummary]:
    """List active user-connected data sources (passwords never returned)."""
    sources = await DataSourceService.list_active_summaries(db, user_id=current_user.id)
    return [DataSourceSummary.model_validate(source) for source in sources]


@router.get("/sources/{data_source_id}", response_model=DataSourceSummary)
async def get_data_source(
    data_source_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DataSourceSummary:
    try:
        source = await DataSourceService.get_active(
            db, data_source_id, user_id=current_user.id
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return DataSourceSummary.model_validate(source)


@router.delete("/sources/{data_source_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_data_source(
    data_source_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    """Remove a saved warehouse from this user's list (soft-delete)."""
    try:
        await DataSourceService.deactivate(
            db, data_source_id, user_id=current_user.id
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get(
    "/sources/{data_source_id}/suggested-questions",
    response_model=SuggestedQuestionsResponse,
)
async def suggested_questions(
    data_source_id: UUID,
    limit: int = Query(6, ge=1, le=12),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SuggestedQuestionsResponse:
    """
    Schema-aware suggested prompts for the analyst sidebar.

    Built from embedded table chunks (+ recent successful questions), not an LLM
    call — stays useful under free-tier rate limits.
    """
    try:
        result = await SuggestionService.suggest_for_data_source(
            db,
            data_source_id,
            user_id=current_user.id,
            limit=limit,
        )
        return SuggestedQuestionsResponse.model_validate(result)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
