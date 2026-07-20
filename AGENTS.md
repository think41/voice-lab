# VoiceLab Agent Instructions

## Project Summary

VoiceLab is a React + FastAPI application for building, saving, and testing single voice agents. The UI is inspired by ElevenLabs. Agent configuration is created in the UI, stored in Postgres, and tested through voice or text sessions.

The app currently supports:
- Agent builder UI
- JSON config editor
- Text chat testing
- Voice testing through browser mic
- Deepgram STT
- Deepgram TTS
- Gemini via Google ADK
- Postgres persistence for agents, runs, trace events, and ADK sessions
- Recent runs view with stored session transcript events

## Tech Stack

Frontend:
- React 19
- TypeScript
- Vite
- Tailwind CSS
- lucide-react icons

Backend:
- Python 3.12
- FastAPI
- SQLAlchemy async
- Alembic
- Postgres 16
- Google ADK
- pipecat-adk from `recruit41/pipecat-adk`
- Deepgram STT/TTS

## Important Paths

Frontend:
- `client/src/App.tsx` - main app state, view routing, agent/run loading
- `client/src/data/defaults.ts` - default agent config
- `client/src/data/providerOptions.ts` - provider/model dropdown options
- `client/src/components/builder/AgentInspector.tsx` - model/STT/TTS config UI
- `client/src/components/test-call/TestCallPanel.tsx` - voice/text testing panel
- `client/src/views/RunsView.tsx` - recent runs view
- `client/src/components/runs/TraceTable.tsx` - stored transcript/trace display
- `client/src/lib/api.ts` - frontend API calls
- `client/src/lib/types.ts` - shared frontend types

Backend:
- `server/app/main.py` - FastAPI app setup
- `server/app/api/routes/agents.py` - agent CRUD APIs
- `server/app/api/routes/runs.py` - recent runs API
- `server/app/api/routes/test_call.py` - voice/text test session APIs and WebSocket
- `server/app/core/config.py` - env config
- `server/app/core/db.py` - async SQLAlchemy setup
- `server/app/models/agent.py` - agents table
- `server/app/models/run.py` - runs table
- `server/app/models/trace_event.py` - trace_events table
- `server/app/repositories/agent_repository.py` - agent persistence
- `server/app/repositories/run_repository.py` - run/trace persistence
- `server/app/services/pipecat_adk_runtime.py` - ADK + Gemini + Deepgram TTS runtime
- `server/app/services/pipecat_streaming_runtime.py` - Pipecat streaming runtime experiment
- `server/app/services/adk_session_service.py` - Google ADK session service
- `server/app/migrations/versions/0001_create_core_tables.py` - initial DB schema

## Database

Postgres runs through Docker Compose on host port `5433`.

Connection:

```text
postgresql://voicelab:voicelab@localhost:5433/voicelab
```

Tables:
- `agents` - saved UI agent configs
- `runs` - test sessions
- `trace_events` - stored session events/transcripts
- ADK also stores its own session data through `ADK_DATABASE_URL`

Trace event examples:
- `session.started`
- `transcript.final`
- `agent.text`
- `audio.output`
- `runtime.error`

Useful SQL:

```sql
select id, name, config->>'model' as model from agents order by created_at desc;

select id, agent_id, status, created_at from runs order by created_at desc;

select event_type, payload, created_at
from trace_events
where run_id = '<run-id>'
order by sequence;
```

## Current Provider Defaults

Current intended defaults:
- LLM: `gemini-3.5-flash`
- STT provider: `deepgram`
- STT model: `nova-2`
- TTS provider: `deepgram`
- TTS voice/model: `aura-asteria-en`

Environment variables:

```dotenv
DATABASE_URL=postgresql+asyncpg://voicelab:voicelab@localhost:5433/voicelab
ADK_DATABASE_URL=postgresql+asyncpg://voicelab:voicelab@localhost:5433/voicelab

GEMINI_API_KEY=
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
GROQ_API_KEY=
STT_PROVIDER=deepgram
STT_API_KEY=
TTS_PROVIDER=deepgram
TTS_API_KEY=

CORS_ORIGINS=http://localhost:5173,http://localhost:5174
```

Deepgram TTS currently prefers `STT_API_KEY`; `TTS_API_KEY` is optional fallback.

## Local Commands

Start Postgres:

```bash
docker compose up -d postgres
```

Backend setup:

```bash
cd server
uv sync
cp .env.example .env
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Frontend setup:

```bash
cd client
npm install
npm run dev
```

Backend checks:

```bash
cd server
uv run ruff check .
uv run pytest -q
```

Frontend check:

```bash
cd client
npm run build
```

## Current Behavior

Voice test flow:

```text
Browser mic -> FastAPI WebSocket -> Deepgram STT -> ADK/Gemini -> Deepgram TTS -> browser audio
```

Text test flow:

```text
Text input -> FastAPI POST endpoint -> ADK/Gemini -> text response
```

Both voice and text sessions create `runs` rows and persist conversation events in `trace_events`.

Recent runs:
- Reads from `/api/runs`
- Shows stored conversation and raw trace events
- Refreshes after test sessions update

## Known Issues And Notes

- Gemini 2.x IDs (`gemini-2.5-flash`, `gemini-2.5-pro`, `gemini-2.5-flash-lite`, `gemini-2.0-flash`) are deprecated: Google's API returns `404 NOT_FOUND` "This model is no longer available to new users." Use `gemini-3.5-flash` (default), `gemini-3.1-pro`, or `gemini-3.1-flash-lite` instead. Old saved rows are normalized to the default by the pydantic validator on read.
- ADK agent names must be valid Python identifiers. Numeric names like `41` are normalized to `agent_41`.
- Existing saved DB rows can preserve old model values. If behavior looks wrong, inspect `agents.config->>'model'`.
- Do not store base64 audio in `trace_events`; store text and metadata only.
- Do not leak `.env` secrets. When inspecting keys, only print whether set, length, or suffix.
- If the UI does not show a run immediately, check DB first. The run may be persisted but the frontend may need refresh.
- LLM provider is selected per-agent via the model ID: bare `gemini-*` IDs run natively; `openai/...`, `anthropic/...`, and `groq/...` IDs run through ADK's LiteLLM wrapper and require `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` / `GROQ_API_KEY` respectively. Note: Groq (console.groq.com) is the fast inference host serving open models — not xAI's Grok. Supported IDs live in `SUPPORTED_MODELS_BY_PROVIDER` (`server/app/schemas/agent.py`); unknown IDs are normalized to the default model by the pydantic validator, same as before.
- The frontend model dropdown (`client/src/data/providerOptions.ts` → `modelOptions`) must stay in sync with `SUPPORTED_MODELS_BY_PROVIDER` on the server when adding models.

## Development Rules For Agents

- Prefer existing patterns and files over adding new abstractions.
- Keep changes scoped.
- Do not reset or delete user changes unless explicitly asked.
- Use `rg` for search.
- Use `apply_patch` for edits when the sandbox allows it.
- If `apply_patch` or read commands fail with `bwrap: loopback: Failed RTM_NEWADDR`, use scoped escalated commands and keep changes minimal.
- Run backend and frontend checks after code changes.
- Commit changes in small, clear commits when implementation is complete.

## Typical Debug Checklist

If Gemini fails:
1. Check saved agent model in DB.
2. Confirm `server/.env` has the expected `GEMINI_API_KEY`.
3. Test the exact model/key directly if needed.
4. Check whether the error is quota `429`, high demand `503`, or ADK validation.

If voice does not answer:
1. Confirm `transcript.final` appears.
2. Confirm ADK turn starts in backend logs.
3. Confirm `agent.text` is emitted.
4. Confirm Deepgram TTS returns `audio.output`.

If recent runs look empty:
1. Query `runs`.
2. Query `trace_events`.
3. Refresh the frontend.
4. Confirm `/api/runs` returns traces.

## Important Current Design Choice

The app is still a single-agent system. The UI may show tools or future sub-agent concepts, but V1 runs only the selected root agent config.
