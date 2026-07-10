# Backend

FastAPI service for the Voice-Driven Data Analyst. Handles warehouse connections, schema RAG, and LangGraph-orchestrated NL→SQL chat via OpenRouter.

## Requirements

- Python 3.11+
- Docker (for Postgres)
- OpenRouter API key

Run Makefile targets from the **repo root** (not this folder).

## Setup

```bash
# from repo root
cp .env.example .env
make up && make wait-db
make install          # or: make install-dev
make migrate
make warehouse-init && make warehouse-seed
make dev              # http://localhost:8000
```

Virtualenv lives at `backend/.venv` (gitignored). `make install` creates it if missing, or recreates it if broken/moved.

## Environment

Copy from `.env.example` at repo root. Important keys:

| Variable | Purpose |
|----------|---------|
| `APP_DB_*` | Project database (`bi_app`) |
| `APP_DB_SCHEMA` | Leave empty → PostgreSQL `public` |
| `CREDENTIALS_SECRET` | Encrypts warehouse passwords in `data_sources` |
| `AI_API_KEY` / `AI_BASE_URL` | OpenRouter |
| `LLM_MODEL` / `LLM_MODEL_FALLBACK` | Chat models (fallback defaults to `openrouter/free`) |
| `EMBEDDING_MODEL` / `EMBEDDING_DIMENSIONS` | Schema embeddings |

Warehouse credentials are **not** in `.env` — pass them to `POST /api/data/connect`.

## API

Swagger: [http://localhost:8000/docs](http://localhost:8000/docs)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Liveness |
| `GET` | `/health/db` | Project DB |
| `GET` | `/health/warehouse` | Connected warehouse |
| `GET` | `/health/ai` | OpenRouter smoke test |
| `POST` | `/api/data/connect` | Save + verify warehouse connection |
| `GET` | `/api/data/sources` | List data sources |
| `POST` | `/api/data/embed-schema` | Introspect + embed schema chunks |
| `POST` | `/api/chat` | NL question → SQL → rows → summary |
| `GET` | `/api/chat/sessions/{id}` | Session history |

### Chat body (first message)

```json
{
  "data_source_id": "<uuid from connect>",
  "message": "What are total sales by region for completed orders?"
}
```

Omit `session_id` on the first request; reuse the returned id for follow-ups.

## Chat pipeline (LangGraph)

```text
retrieve (RAG) → generate_sql → validate (sqlglot)
       ↑______________| (retry ≤ SQL_MAX_ATTEMPTS)
                      ↓
                   execute → summarize
```

Only `SELECT` is allowed. Warehouse runs as the connected (preferably readonly) user.

## Layout

```text
backend/
├── app/
│   ├── main.py           # FastAPI entry
│   ├── config.py
│   ├── providers/        # OpenRouter client
│   ├── graph/            # LangGraph nodes + state
│   ├── services/         # RAG, SQL, warehouse, chat
│   ├── routes/           # /api/data, /api/chat
│   ├── models/           # SQLAlchemy ORM
│   └── security/         # credential encryption
├── alembic/              # migrations
├── scripts/              # warehouse init/seed/check
└── tests/
```

## Tests

```bash
make test
make test-cov
```

## Scripts

| Script | Via |
|--------|-----|
| Init warehouse schema | `make warehouse-init` |
| Seed demo sales data | `make warehouse-seed` |
| CLI warehouse check | `make warehouse-check-cli` |
