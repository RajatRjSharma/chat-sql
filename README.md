# Voice-Driven Data Analyst

Conversational BI assistant: ask questions in natural language, get validated SQL against a connected warehouse, plus a plain-language answer, table, and chart.

**Stack:** Next.js · FastAPI · SQLAlchemy · Alembic · LangGraph · LangChain · PostgreSQL (+ pgvector) · Recharts

**Repo:** [github.com/RajatRjSharma/chat-sql](https://github.com/RajatRjSharma/chat-sql)

[![CI](https://github.com/RajatRjSharma/chat-sql/actions/workflows/ci.yml/badge.svg)](https://github.com/RajatRjSharma/chat-sql/actions/workflows/ci.yml)

## Architecture

| Database | Port (local) | Role |
|----------|----------------|------|
| `bi_app` | 5432 | Users, sessions, messages, RAG embeddings, encrypted data sources, **CSV upload tables** (`u_<id>` schemas) |
| `bi_warehouse` | 5433 | Optional local demo analytics data (`sales` schema) for **Connect** demos |

- **Connect:** user supplies external warehouse credentials at runtime (stored encrypted in `bi_app`).
- **Upload:** CSV/Excel is parsed and loaded into an isolated schema on the **project database** (`APP_DB_*`). No second warehouse service is required.
- Project DB credentials live in `.env` (`APP_DB_*`).

## Quick start (local)

```bash
cp .env.example .env   # set APP_DB_*, AI_API_KEY, JWT_SECRET, CREDENTIALS_SECRET
make up && make wait-db
make install
make migrate
make warehouse-init      # optional — only for local demo warehouse (Connect flow)
make warehouse-seed      # optional — demo sales data
make frontend-install
make dev                 # terminal A — API on :8000
make frontend-dev        # terminal B — UI on :3000
```

- UI: [http://localhost:3000](http://localhost:3000)
- API docs: [http://localhost:8000/docs](http://localhost:8000/docs)

Copy `frontend/.env.local.example` to `frontend/.env.local` if you need a non-default API URL (`NEXT_PUBLIC_API_URL`).

## Authentication

Register with **email + username + password** (no Google Sign-In).

| Mode | `EMAIL_OTP_ENABLED` | Behaviour |
|------|---------------------|-----------|
| **Local (default)** | `true` | After register, verify email via OTP sent through Gmail SMTP (`SMTP_USER`, `SMTP_PASSWORD` app password). |
| **Production (e.g. Render)** | `false` | Register marks the user verified immediately; user signs in without OTP. Use this when the host blocks outbound SMTP (Render free tier). |

When OTP is enabled, set `SMTP_USER` to your Gmail address and `SMTP_PASSWORD` to a [Google App Password](https://myaccount.google.com/apppasswords). Optional: `SMTP_FROM=Voice-Driven Data Analyst <you@gmail.com>`.

JWT settings: `JWT_SECRET`, `JWT_ISSUER` (default `voice-driven-data-analyst`).

## Typical flow

1. **Register / sign in**
2. Open the UI — pick a **saved warehouse**, **connect** credentials, or **upload CSV/Excel**
3. Schema indexing runs when needed (`POST /api/data/embed-schema`)
4. Sidebar suggestions load from schema (+ recent successes) (`GET /api/data/sources/{id}/suggested-questions`)
5. Ask a question — type or use the **mic** (`POST /api/chat/stream` for live pipeline stages; `POST /api/chat` still works)
6. **Play** any answer summary (chat bubble or insight panel) via offline Piper TTS (`POST /api/voice/speak`)
7. Reopen past chats via **History** in the sidebar (`GET /api/chat/sessions?data_source_id=…`, then `GET /api/chat/sessions/{id}`)
8. **Switch warehouse** returns to the connect screen to open another saved source

### Offline text-to-speech

Summaries are spoken with **Piper** on the API (local ONNX, no cloud TTS at request time). The English voice `en_US-amy-low` is committed under `backend/models/piper/` and used for local, Docker, and production.

Play uses **`POST /api/voice/speak-stream`**: the API splits the full summary into chunks and streams each WAV as NDJSON so the UI plays continuously through the whole paragraph (nothing is dropped for length).

| Env | Default | Notes |
|-----|---------|-------|
| `TTS_ENABLED` | `true` | Set `false` to disable speak endpoints |
| `TTS_VOICE_PATH` | `models/piper/en_US-amy-low.onnx` | Relative to `backend/` |
| `TTS_MAX_CHARS` | `220` | **Per-chunk** size only — full paragraph is still spoken (split into chunks). Lower = faster first audio on Render. |
| `TTS_LENGTH_SCALE` | `0.85` | `<1` = faster/shorter speech (less CPU) |
| `TTS_ONNX_THREADS` | `1` | Best on tiny CPUs (avoid thread oversubscription) |
| `TTS_WARMUP_ENABLED` | `true` | One-shot synthesize after model load |
| `TTS_WARMUP_TEXT` | `Ready.` | Warmup phrase (discarded) |
| `TTS_RATE_LIMIT_PER_MINUTE` | `10` | Per IP / user |

Refresh the bundled voice: `make tts-models`. Mic input still uses the browser Web Speech API (STT). Browser TTS is only used if the speak API fails.

### Keep Render awake (free tier)

Render free instances sleep after ~15 minutes idle, which makes the first TTS call very slow. Add a GitHub Actions keep-alive:

1. Repo **Settings → Secrets → Actions** → add `KEEPALIVE_HEALTH_URL` = `https://your-api.onrender.com/health`
2. Workflow [`.github/workflows/keep-alive.yml`](.github/workflows/keep-alive.yml) pings every 12 minutes (and on manual dispatch)

Without the secret, the workflow no-ops safely.

### CSV / Excel upload

```text
POST /api/data/upload  →  POST /api/data/embed-schema  →  chat
```

- Upload uses **`APP_DB_*`** only: creates schema `u_<id>`, loads the table, registers a read-only data source.
- Limits (defaults): **10 MB**, **50,000 rows**, `.csv` / `.xlsx` (first sheet only). See `UPLOAD_MAX_BYTES`, `UPLOAD_MAX_ROWS`.
- `UPLOAD_WH_*` in `.env.example` is **legacy / unused** — safe to omit.

You do **not** need `make warehouse-init` for uploads; you only need migrations (`make migrate`) on the app database.

### Local demo warehouse (Connect only)

| Field | Value |
|-------|-------|
| host | `localhost` |
| port | `5433` |
| database | `bi_warehouse` |
| schema | `sales` |
| username | `bi_readonly` |
| password | `readonly_pass` |

Requires `make warehouse-init` and `make warehouse-seed`.

## Deployment (Render + Vercel)

| Service | Host | Root directory |
|---------|------|----------------|
| API | [Render](https://render.com) | `backend` |
| UI | [Vercel](https://vercel.com) | `frontend` |

### Render (backend)

- **Root directory:** `backend`
- **Python:** **3.12** — pinned via `backend/runtime.txt` (do not use 3.14; SSRF/`ipaddress` and other stdlib differences break production)
- Also set **Environment → Python Version → 3.12** in the Render dashboard so the pin is double-checked
- **Health check:** `/health`
- **Build:** `pip install -r requirements.txt`
- **Start:** `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- Run migrations once (local against Render Postgres): `alembic upgrade head` with `APP_DB_*` pointing at Render.
- Enable **pgvector** on the Render Postgres instance if embeddings fail.

**Important environment variables:**

| Variable | Notes |
|----------|--------|
| `APP_ENV` | `production` |
| `APP_DB_*` | Render Postgres connection |
| `CORS_ORIGINS` | Your Vercel URL (e.g. `https://your-app.vercel.app`) |
| `AI_API_KEY` | OpenRouter (or compatible) key |
| `JWT_SECRET` | Long random secret |
| `JWT_ISSUER` | `voice-driven-data-analyst` |
| `CREDENTIALS_SECRET` | Encrypts stored warehouse passwords |
| `EMAIL_OTP_ENABLED` | `false` on Render free tier (SMTP ports blocked) |
| `SMTP_*` | Only needed if `EMAIL_OTP_ENABLED=true` |
| `TTS_ENABLED` | `true` (bundled Piper voice ships in the repo; disable if free-tier RAM OOMs) |
| `TTS_MAX_CHARS` | `220` (per chunk; full text is streamed in multiple chunks) |
| `TTS_LENGTH_SCALE` | `0.85` |
| `TTS_ONNX_THREADS` | `1` |

Use Python **3.12** on Render (`backend/runtime.txt` + dashboard). Avoid 3.14.

### Vercel (frontend)

| Variable | Notes |
|----------|--------|
| `NEXT_PUBLIC_API_URL` | Render API URL (e.g. `https://your-api.onrender.com`) |

Set **Root Directory** to `frontend`. Leave **Output Directory** empty (default Next.js).

## Continuous integration

GitHub Actions (`.github/workflows/ci.yml`) runs on every push and PR to `main`:

| Job | What |
|-----|------|
| Backend | Python 3.12 · `pytest` |
| Frontend | Node 20 · Playwright Chromium E2E (mocked API) |

```bash
make test            # same backend suite as CI
make frontend-e2e    # same UI E2E as CI (after make frontend-e2e-install)
```

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
├── .github/workflows/ci.yml
├── backend/          # FastAPI application — see backend/README.md
└── frontend/         # Next.js UI (Voice-Driven Data Analyst)
```

If you move or rename this repository, run `make install` again — it recreates a broken or relocated virtualenv automatically.
