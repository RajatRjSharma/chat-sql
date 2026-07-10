# Voice-Driven Data Analyst

Conversational BI assistant: ask questions in natural language, get validated SQL against a connected warehouse, plus a plain-language answer.

**Stack:** FastAPI · SQLAlchemy · Alembic · LangGraph · OpenRouter · PostgreSQL (+ pgvector)

## Architecture

| Database | Port | Role |
|----------|------|------|
| `bi_app` | 5432 | Sessions, messages, RAG embeddings, encrypted data sources |
| `bi_warehouse` | 5433 | Demo analytics data (`sales` schema) |

Warehouse credentials are **user-provided** via API (never stored in `.env`). Project DB credentials live in `.env`.

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

API docs: [http://localhost:8000/docs](http://localhost:8000/docs)

## Day 2 flow (Swagger)

1. `POST /api/data/connect` — connect warehouse  
2. `POST /api/data/embed-schema` — embed schema for RAG  
3. `POST /api/chat` — ask a question (omit `session_id` on first message)

Demo warehouse (local):

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
make help          # all targets
make test          # backend tests
make destroy       # wipe DB containers + volumes
```

## Project layout

```text
.
├── Makefile
├── docker-compose.yml
├── .env.example
└── backend/          # FastAPI app — see backend/README.md
```

## Status

- **Day 1:** Dual Postgres, connect API, migrations, warehouse seed  
- **Day 2:** OpenRouter, schema RAG, LangGraph NL→SQL chat  
- **Later:** Next.js UI, charts, voice (STT/TTS)
