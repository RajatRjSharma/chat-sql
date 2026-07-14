# Voice-Driven Data Analyst

Conversational BI assistant: ask questions in natural language, get validated SQL against a connected warehouse, plus a plain-language answer, table, and chart.

**Stack:** Next.js · FastAPI · SQLAlchemy · Alembic · LangGraph · LangChain · PostgreSQL (+ pgvector) · Recharts

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
make frontend-install
make dev                 # terminal A — API on :8000
make frontend-dev        # terminal B — UI on :3000
```

- UI: [http://localhost:3000](http://localhost:3000)  
- API docs: [http://localhost:8000/docs](http://localhost:8000/docs)

Copy `frontend/.env.local.example` to `frontend/.env.local` if you need a non-default API URL (`NEXT_PUBLIC_API_URL`).

## Typical flow

1. Open the UI — pick a **saved warehouse** or connect a new one (`GET /api/data/sources` / `POST /api/data/connect`)
2. Schema indexing runs when needed (`POST /api/data/embed-schema`)
3. Ask a question in chat — type or use the **mic** (`POST /api/chat` — omit `session_id` on the first message)
4. Optional: play the latest summary aloud from the insight panel
5. Reopen past chats via **History** in the sidebar (`GET /api/chat/sessions?data_source_id=…`, then `GET /api/chat/sessions/{id}`)
6. **Switch warehouse** returns to the connect screen to open another saved source

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
make frontend-e2e  # run Playwright UI E2E (mocked API)
make destroy       # remove DB containers and volumes
```

## Project layout

```text
.
├── Makefile
├── docker-compose.yml
├── .env.example
├── backend/          # FastAPI application — see backend/README.md
└── frontend/         # Next.js UI (Meridian)
```

If you move or rename this repository, run `make install` again — it recreates a broken or relocated virtualenv automatically.
