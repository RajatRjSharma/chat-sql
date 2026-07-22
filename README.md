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
cp .env.example .env   # set APP_DB_*, AI_API_KEY, SMTP_USER, SMTP_PASSWORD, JWT_SECRET
make up && make wait-db
make install
make migrate
make warehouse-init
make warehouse-seed
make frontend-install
make dev                 # terminal A — API on :8000
make frontend-dev        # terminal B — UI on :3000
```

Auth uses **Gmail SMTP** for OTP (set `SMTP_USER` to your Gmail and `SMTP_PASSWORD` to a [Google App Password](https://myaccount.google.com/apppasswords)). There is no “Sign in with Google”.

- UI: [http://localhost:3000](http://localhost:3000)  
- API docs: [http://localhost:8000/docs](http://localhost:8000/docs)

Copy `frontend/.env.local.example` to `frontend/.env.local` if you need a non-default API URL (`NEXT_PUBLIC_API_URL`).

## Typical flow

1. **Register / sign in** (email + username + password; Gmail SMTP OTP verifies email — no Google Sign-In)
2. Open the UI — pick a **saved warehouse**, **connect** credentials, or **upload CSV/Excel**
3. Schema indexing runs when needed (`POST /api/data/embed-schema`)
4. Sidebar suggestions load from schema (+ recent successes) (`GET /api/data/sources/{id}/suggested-questions`)
5. Ask a question — type or use the **mic** (`POST /api/chat/stream` for live pipeline stages; `POST /api/chat` still works)
5. Optional: play the latest summary aloud from the insight panel
6. Reopen past chats via **History** in the sidebar (`GET /api/chat/sessions?data_source_id=…`, then `GET /api/chat/sessions/{id}`)
7. **Switch warehouse** returns to the connect screen to open another saved source

### CSV / Excel upload

```bash
# After make warehouse-init (creates bi_uploader + bi_readonly)
# POST multipart /api/data/upload  →  POST /api/data/embed-schema  →  chat
```

Upload creates an isolated schema (`u_<id>`), loads the table, registers a read-only data source, then the UI indexes schema for RAG.

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
