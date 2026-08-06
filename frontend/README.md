# Voice-Driven Data Analyst — frontend

Next.js App Router UI for Voice-Driven Data Analyst.

System overview: [docs/architecture.md](../docs/architecture.md) · [architecture diagram](../docs/architecture.png)

## Setup

```bash
cp .env.local.example .env.local   # optional; defaults to same-origin /api rewrite
npm install
npx playwright install chromium    # once — for UI E2E
npm run dev
```

Or from the repo root: `make frontend-install` then `make frontend-dev`.

| Variable | Where | Purpose |
|----------|-------|---------|
| `API_PROXY_TARGET` | server (Next) | Rewrite `/api` + `/health` → FastAPI (local or Render) |
| `NEXT_PUBLIC_API_URL` | browser | Leave unset in production; set only to call the API host directly |
| `PLAYWRIGHT_PORT` / `PLAYWRIGHT_BASE_URL` | E2E optional | Defaults in `playwright.config.ts` |

Backend env vars are documented in the repo-root [`.env.example`](../.env.example).

## Flow

1. Connect warehouse (demo defaults prefilled), open a **saved source**, or **upload** CSV/Excel
2. Schema embed runs automatically when needed (`POST /api/data/embed-schema`)
3. Chat (type or **mic**) → answer + SQL + table + chart (when chartable)
4. **Evidence panel** shows warehouse provenance + schema index; use **Refresh schema index** after warehouse DDL changes
5. Optional **Play** reads a summary aloud (Piper TTS via the API)
6. History sidebar loads past sessions; **Switch warehouse** returns to the picker

Backend prepare does **schema RAG + FK neighborhood expand** before LangGraph SQL, so multi-table joins are not limited to cosine top-K alone. See the root README “Schema linking” section.

### Voice notes

- Uses the browser **Web Speech API** (best in Chrome on `localhost` or HTTPS)
- Grant microphone permission when prompted
- If unsupported, the mic is hidden and typing still works

## UI E2E (Playwright, mocked API)

```bash
# once per machine
make frontend-e2e-install

make frontend-e2e
```

Specs under `e2e/` stub `/api/**` so tests do not need FastAPI, Docker, or an AI key.
`npm install` alone is not enough — Playwright must download Chromium separately.
Includes `e2e/schema-index.spec.ts` for Evidence **Refresh schema index**.
