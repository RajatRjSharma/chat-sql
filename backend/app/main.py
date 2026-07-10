"""FastAPI application entrypoint."""

from contextlib import asynccontextmanager
from uuid import UUID

import psycopg2
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.config import settings
from app.database import AsyncSessionLocal, engine
from app.routes.chat import router as chat_router
from app.routes.data import router as data_router
from app.core.schema import read_connection_schema
from app.services.data_source_service import DataSourceService
from app.providers.openrouter import get_openrouter_client
from app.core.exceptions import OpenRouterError

APP_NAME = "Voice-Driven Data Analyst"
APP_VERSION = "0.1.0"


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Application lifespan hooks for startup and shutdown."""
    yield
    await engine.dispose()


app = FastAPI(
    title=APP_NAME,
    version=APP_VERSION,
    description="Conversational BI assistant powered by voice and natural language.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

app.include_router(data_router)
app.include_router(chat_router)


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    return {"status": "ok", "app": APP_NAME, "version": APP_VERSION}


@app.get("/health/ai", tags=["health"])
async def health_ai() -> dict[str, str]:
    """Verify OpenRouter connectivity with a short completion request."""
    try:
        client = get_openrouter_client()
        reply = client.complete(
            [{"role": "user", "content": "Reply with exactly: ok"}],
            temperature=0,
            max_tokens=8,
        )
        return {
            "status": "ok",
            "model": settings.llm_model,
            "sample": reply[:80],
        }
    except OpenRouterError as exc:
        return {"status": "error", "detail": str(exc)}
    except Exception as exc:
        return {"status": "error", "detail": str(exc)}


@app.get("/health/db", tags=["health"])
async def health_db() -> dict[str, str | None]:
    """Verify project database connectivity."""
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
            if settings.app_db_schema:
                schema: str | None = settings.app_db_schema
            else:
                result = await conn.execute(text("SELECT current_schema()"))
                schema = result.scalar_one()
        return {
            "status": "ok",
            "host": settings.app_db_host,
            "database": settings.app_db_name,
            "schema": schema,
        }
    except Exception as exc:
        return {
            "status": "error",
            "database": settings.app_db_name,
            "detail": str(exc),
        }


@app.get("/health/warehouse", tags=["health"])
async def health_warehouse(
    data_source_id: UUID = Query(..., description="Connected warehouse data_source_id"),
) -> dict[str, str | int]:
    """Verify a user-connected warehouse database (credentials from project DB)."""
    try:
        async with AsyncSessionLocal() as session:
            data_source = await DataSourceService.get_active(session, data_source_id)
            info = DataSourceService.connection_info_from_record(data_source)

        with psycopg2.connect(info.connection_url) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
                schema = read_connection_schema(cur, info.schema_name)
                cur.execute(
                    """
                    SELECT COUNT(*)
                    FROM information_schema.tables
                    WHERE table_schema = %s
                    """,
                    (schema,),
                )
                table_count = cur.fetchone()[0]

        return {
            "status": "ok",
            "data_source_id": str(data_source_id),
            "name": info.name,
            "database": info.database,
            "schema": schema,
            "table_count": table_count,
        }
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        return {
            "status": "error",
            "data_source_id": str(data_source_id),
            "detail": str(exc),
        }
