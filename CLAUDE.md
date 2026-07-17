# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

`AGENTS.md` at the repo root has an extensive, current inventory of important paths, tables, providers, env vars, and a debug checklist. Read it before non-trivial changes rather than re-deriving that info here.

## Commands

Postgres (Docker, host port 5433):

```bash
docker compose up -d postgres
```

Backend (`server/`, uses `uv`):

```bash
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
uv run ruff check .
uv run pytest -q
uv run pytest tests/path/to/test_file.py::test_name   # single test
uv run alembic revision --autogenerate -m "describe"  # after model changes
uv run alembic downgrade -1
```

Frontend (`client/`):

```bash
npm install
npm run dev            # Vite dev server, default http://localhost:5173
npm run build          # type-check + production build (main correctness gate — no separate lint/test script)
VITE_API_TARGET=http://127.0.0.1:8001 npm run dev   # point Vite at a non-default backend port
```

There is no frontend test suite; `npm run build` (which runs `tsc`) is the correctness check.

## Architecture

Single-agent voice/text testing app. One agent configuration at a time is authored in the UI, persisted in Postgres, and exercised via either a text POST endpoint or a voice WebSocket.

**Voice path (real-time):**
Browser mic → FastAPI WebSocket (`server/app/session/router.py`) → `server/pipeline/runner.py` → Deepgram STT → Google ADK + Gemini (`server/pipeline/llm/adk_runtime.py`) → Deepgram TTS → browser audio.

**Text path:** Text POST → same ADK/Gemini runtime → text response.

**Persistence, two logical databases sharing one Postgres instance:**
- `DATABASE_URL` — VoiceLab tables: `agents` (UI config JSON), `runs` (test session rows), `trace_events` (per-turn events: `session.started`, `transcript.final`, `agent.text`, `audio.output`, `runtime.error`). Never store base64 audio in `trace_events` — text and metadata only.
- `ADK_DATABASE_URL` — Google ADK's own conversation session storage. Both URLs typically point at the same DB.

Every voice or text session creates a `runs` row and appends `trace_events`; the Runs view (`client/src/views/RunsView.tsx` → `/api/runs`) reads back the stored transcript rather than replaying live state.

**Backend layering:** `server/app/` holds one folder per feature (`agents/`, `runs/`, `session/`, `audio_evaluations/`, `health/`), each with `router.py` (HTTP + WS) → `service.py` (DB access) → `models.py` (SQLAlchemy async) plus `schemas.py` (Pydantic). The Pipecat voice machinery lives in the sibling top-level package `server/pipeline/` (`runner.py`, `pipeline.py`, `llm/`, `stt/`, `tts/`, `custom_processors/`, `utils/`). Config in `app/config.py`, async engine in `app/db.py`.

**Frontend state:** `client/src/App.tsx` owns view routing and agent/run loading; API calls go through `client/src/lib/api.ts`; shared types in `client/src/lib/types.ts`. Builder UI (`components/builder/`) and test-call panel (`components/test-call/`) both read/write the same agent config shape defined in `data/defaults.ts`.

## Provider / model gotchas

- Default LLM: `gemini-3.5-flash`. Gemini 2.x models (`gemini-2.5-flash`, `gemini-2.5-pro`, `gemini-2.0-flash`) were deprecated by Google — the API now returns 404 "no longer available to new users". Check `agents.config->>'model'` on old saved rows and expect the pydantic validator to normalize them to the current default.
- ADK agent names must be valid Python identifiers; numeric names like `41` are normalized to `agent_41` at runtime.
- Deepgram TTS currently prefers `STT_API_KEY`, with `TTS_API_KEY` as fallback.
- When debugging keys, print only presence / length / suffix — never the full value.
