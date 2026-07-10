# Voice-Driven Data Analyst

Conversational BI assistant: ask questions in natural language, get validated SQL against a connected warehouse, plus a plain-language answer.

**Stack:** FastAPI · SQLAlchemy · Alembic · LangGraph · OpenRouter · PostgreSQL (+ pgvector)

## Architecture

| Database | Port | Role |
|----------|------|------|
| `bi_app` | 5432 | Sessions, messages, RAG embeddings, encrypted data sources |
| `bi_warehouse` | 5433 | Demo analytics data (`sales` schema) |

Warehouse credentials are provided via the API and stored encrypted. Project database credentials are configured in `.env`.

## Quick start

```bash
cp .env.example .env   # set APP_DB_* and AI_API_KEY
make up && make wait-db
make install
make migrate
make warehouse-init
make warehouse-seed
make dev
```

API documentation: [http://localhost:8000/docs](http://localhost:8000/docs)

## Typical API flow

1. `POST /api/data/connect` — connect a warehouse  
2. `POST /api/data/embed-schema` — index schema metadata for retrieval  
3. `POST /api/chat` — ask a question (omit `session_id` on the first message)

### Local demo warehouse

| Field | Value |
|-------|-------|
| host | `localhost` |
| port | `5433` |
| database | `bi_warehouse` |
| schema | `sales` |
| username | `bi_readonly` |
| password | `readonly_pass` |

## Useful commands

```bash
make help          # list all targets
make test          # run backend tests
make destroy       # remove DB containers and volumes
```

## Project layout

```text
.
├── Makefile
├── docker-compose.yml
├── .env.example
└── backend/          # FastAPI application — see backend/README.md
```

If you move or rename this repository, run `make install` again — it recreates a broken or relocated virtualenv automatically.
