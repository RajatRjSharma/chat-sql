# Meridian — frontend

Next.js App Router UI for Voice-Driven Data Analyst.

## Setup

```bash
cp .env.local.example .env.local   # optional; defaults to http://localhost:8000
npm install
npx playwright install chromium    # once — for UI E2E
npm run dev
```

Or from the repo root: `make frontend-install` then `make frontend-dev`.

## Flow

1. Connect warehouse (demo defaults prefilled) or open a saved source
2. Schema embed runs automatically when needed
3. Chat (type or **mic**) → answer + SQL + table + chart (when chartable)
4. Optional **Play** in the insight panel reads the latest summary aloud
5. History sidebar loads past sessions; Switch warehouse returns to the picker

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
