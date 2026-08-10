# Backend

FastAPI service for the Voice-Driven Data Analyst. Handles warehouse connections, schema RAG, and LangGraph-orchestrated NL→SQL chat.

## Requirements

- Python **3.12** (pinned for Render via `runtime.txt`; local `.python-version` is `3.12.10`)
- Docker (for Postgres)
- AI provider API key

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

Copy from `.env.example` at repo root (complete list of Settings aliases). Important keys:

| Variable | Purpose |
|----------|---------|
| `APP_DB_*` | Project database (`bi_app`) |
| `APP_DB_SCHEMA` | Leave empty → PostgreSQL `public` |
| `DB_POOL_SIZE` / `DB_MAX_OVERFLOW` | SQLAlchemy async pool (default 5 / 5) |
| `CREDENTIALS_SECRET` | Encrypts warehouse passwords in `data_sources` |
| `AI_API_KEY` / `AI_BASE_URL` | AI provider endpoint and credentials |
| `LLM_MODEL` / `LLM_MODEL_FALLBACK` | Primary and fallback chat models |
| `EMBEDDING_MODEL` / `EMBEDDING_DIMENSIONS` | Schema embeddings |
| `RAG_TOP_K` | Cosine seed count for schema RAG (default 5) |
| `RAG_EXPAND_HOPS` | FK neighborhood depth after seeds (default 1) |
| `RAG_MAX_TABLES` | Cap on tables in schema context (default 15) |
| `RAG_EXPAND_ON_RETRY` | One expand-and-retry on allowlist miss (default true) |
| `SQL_MAX_ATTEMPTS` / `WAREHOUSE_MAX_ROWS` / `CHAT_HISTORY_LIMIT` | SQL retry + result caps |
| `TTS_*` | Offline Piper Speak (see root `.env.example`) |
| `REGISTRATION_ENABLED` | Allow new sign-ups (default `false`) |
| `EMAIL_OTP_ENABLED` | `true` locally (SMTP OTP); `false` on Render when SMTP is blocked |
| `SMTP_*` | Required only when `EMAIL_OTP_ENABLED=true` |
| `UPLOAD_MAX_BYTES` / `UPLOAD_MAX_ROWS` | CSV/Excel limits |

CSV uploads write to **`APP_DB_*`** (isolated `u_<id>` schemas). `UPLOAD_WH_*` is legacy and unused.

Warehouse credentials are **not** in `.env` — pass them to `POST /api/data/connect`.

## API

Swagger: [http://localhost:8000/docs](http://localhost:8000/docs)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Liveness |
| `GET` | `/health/db` | Project DB |
| `GET` | `/health/warehouse` | Connected warehouse |
| `GET` | `/health/ai` | AI provider smoke test |
| `POST` | `/api/data/connect` | Save + verify warehouse connection |
| `POST` | `/api/data/upload` | CSV/Excel → isolated schema + data source |
| `GET` | `/api/data/sources` | List data sources |
| `GET` | `/api/data/sources/{id}/suggested-questions` | Schema-aware prompt suggestions |
| `POST` | `/api/data/embed-schema` | Introspect + embed schema chunks (also used by Evidence **Refresh schema index**) |
| `POST` | `/api/chat` | NL question → prepare (RAG + FK expand) → SQL → rows → summary |
| `POST` | `/api/chat/stream` | Same pipeline over SSE (`stage` / `result` / `error`) |
| `GET` | `/api/chat/sessions` | List sessions for a data source |
| `GET` | `/api/chat/sessions/{id}` | Session history |

### Chat body (first message)

```json
{
  "data_source_id": "<uuid from connect>",
  "question": "What are total sales by region for completed orders?"
}
```

Omit `session_id` on the first request; reuse the returned id for follow-ups.

### Streaming (`POST /api/chat/stream`)

SSE events:

- `stage` — `{ "stage", "label", "attempts", "sql" }`
- `result` — full chat response payload
- `error` — `{ "detail": "..." }`

## Chat pipeline (LangGraph end-to-end)

```text
ChatService bootstrap (NOT LangGraph)
  auth + chat session + history + catalog load
       │
       ▼
LangGraph (ainvoke / astream)
  route_intent → link_entities → retrieve_and_link
  → assess_relevance
  → generate_sql → validate_sql ↺ → execute_sql → summarize
  expand_schema (allowlist miss / UNANSWERABLE BI) → generate again
  prepare_empty_retry (zero rows) → generate again → resolve best
```

See [docs/architecture.md](../docs/architecture.md) for the system diagram.

**Soft NLP:** IntentRouter + EntityLinker use small-token LLM JSON (`NLP_PREFER_LLM`; optional `LLM_ROUTER_MODEL`). Heuristics are fallback-only. Schema vocabulary is derived from the connected warehouse (any domain).

**Hard rails:** SELECT-only sqlglot validation + table allowlist. Scope may still end early; SQL may still return `UNANSWERABLE`.

**Schema linking:** seeds stay small (`RAG_TOP_K`); FK expand grows context up to `RAG_MAX_TABLES`.

Only `SELECT` is allowed. Warehouse runs as the connected (preferably readonly) user.

## Layout

```text
backend/
├── app/
│   ├── main.py           # FastAPI entry
│   ├── config.py
│   ├── providers/        # AI client
│   ├── graph/            # LangGraph nodes + state
│   ├── services/         # RAG, schema linker, SQL, warehouse, chat
│   ├── routes/           # /api/data, /api/chat, /api/voice
│   ├── models/           # SQLAlchemy ORM
│   └── security/         # credential encryption
├── models/piper/         # Bundled offline Piper voice (en_US-amy-low)
├── alembic/              # migrations
├── scripts/
│   ├── init_warehouse.sql / seed_warehouse.py
│   └── sales_extended/   # ~50-table sales schema + seeder
└── tests/
```

## Offline TTS

```bash
make tts-models   # download/refresh en_US-amy-low into models/piper/
```

- `POST /api/voice/speak` — full WAV (simple clients)
- `POST /api/voice/speak-stream` — NDJSON sentence WAVs (UI Play button; lower time-to-first-audio)

Tuned for small hosts without slowing the happy path: preload + warmup for warm Speak, `TTS_ONNX_THREADS=1`, bounded WAV cache, and short critical-section locks so chat and TTS do not peak together. No network calls at speak time. If a ≤512MB instance still OOMs, set `TTS_PRELOAD=false` or `TTS_ENABLED=false`.

On Render free tier, set secret `KEEPALIVE_HEALTH_URL` so `.github/workflows/keep-alive.yml` can ping `/health` every 5 minutes (GitHub Actions only). If the workflow fails with “runner not acquired” / Internal server error while `curl …/health` still returns OK, that is a GitHub hosted-runner outage — re-run later (see root README).

### Chat troubleshooting (Render logs)

Search service logs for:

- `chat stage=` — node breadcrumbs (`assess_relevance`, `generate_sql`, …)
- `chat graph stream failed` — full traceback (e.g. bad history indexing used to show here)
- `chat SSE error` — what the browser received (`error_type`, stage, question preview)
- `AI complete exhausted models` / `AI model … failed` — provider / empty-response issues

Multi-turn SQL prompts use `SqlGenerator._history_for_prompt` (last N turns via **slice**). Scenario tests: `tests/unit/test_chat_history_scenarios.py`.

## Tests / quality

```bash
make lint           # ruff
make test           # pytest (unit + API + graph + eval + history scenarios)
make backend-check  # ruff + pytest (CI backend job)
make check          # backend + frontend quality (no E2E)
```

## Scripts

| Script | Via |
|--------|-----|
| Init warehouse schema | `make warehouse-init` |
| Seed demo sales data | `make warehouse-seed` |
| Extend sales schema (~50 tables) | `make warehouse-extend` |
| Seed extended sales dims/joins | `make warehouse-seed-extended` |
| CLI warehouse check | `make warehouse-check-cli` |

Extended warehouse docs: [scripts/sales_extended/README.md](scripts/sales_extended/README.md).
