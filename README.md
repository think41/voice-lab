# VoiceLab

VoiceLab is a React and FastAPI workspace for configuring, persisting, and testing voice agents powered by [Pipecat ADK](https://github.com/recruit41/pipecat-adk).

The interface is inspired by ElevenLabs and includes an agent builder, JSON configuration editor, test-call panel, run traces, reports, and provider settings. The runnable single-agent configuration is created in the UI and persisted in Postgres.

## Tech Stack

- React 19, TypeScript, Vite, Tailwind CSS
- Python 3.12, FastAPI
- SQLAlchemy async, Alembic, Postgres 16
- Google ADK with `pipecat-adk`
- Browser WebSocket and microphone APIs

## Repository Structure

```text
voice-lab/
|-- client/                  # React application
|   |-- src/components/      # Builder, test-call, runs, reports, and UI components
|   |-- src/views/           # Application views
|   |-- src/lib/             # API client, WebSocket helpers, and shared types
|   `-- index.html           # Minimal Vite mount shell only
|-- server/
|   |-- app/api/routes/      # FastAPI HTTP and WebSocket routes
|   |-- app/models/          # SQLAlchemy models
|   |-- app/repositories/    # Database access
|   |-- app/services/        # Pipecat ADK runtime and session services
|   |-- app/migrations/      # Alembic migrations
|   `-- tests/               # Backend tests
`-- docker-compose.yml       # Local Postgres service
```

## Prerequisites

Install:

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- Node.js 20+ and npm
- Docker with Docker Compose
- Git

## Run Locally

### 1. Start Postgres

From the repository root:

```bash
docker compose up -d postgres
docker compose ps
```

The project database runs on host port `5433` to avoid conflicts with a local Postgres installation on `5432`:

```text
postgresql://voicelab:voicelab@localhost:5433/voicelab
```

### 2. Configure the backend

```bash
cd server
cp .env.example .env
uv sync
```

Edit `server/.env` and add provider credentials:

```dotenv
DATABASE_URL=postgresql+asyncpg://voicelab:voicelab@localhost:5433/voicelab
ADK_DATABASE_URL=postgresql+asyncpg://voicelab:voicelab@localhost:5433/voicelab

GEMINI_API_KEY=your-gemini-key

STT_PROVIDER=deepgram
STT_API_KEY=your-stt-provider-key

TTS_PROVIDER=elevenlabs
TTS_API_KEY=your-tts-provider-key
ELEVENLABS_VOICE_ID_RACHEL=21m00Tcm4TlvDq8ikWAM

CORS_ORIGINS=http://localhost:5173,http://localhost:5174
```

`DATABASE_URL` stores VoiceLab agent configurations, run summaries, and trace events. `ADK_DATABASE_URL` stores Google ADK conversation sessions. Both can use the same Postgres database.

### 3. Apply database migrations

From `server/`:

```bash
uv run alembic upgrade head
```

Expected output includes:

```text
Running upgrade -> 0001_create_core_tables, create core tables
```

### 4. Start FastAPI

```bash
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Backend URLs:

- API: `http://localhost:8000`
- Health check: `http://localhost:8000/health`
- OpenAPI documentation: `http://localhost:8000/docs`

### 5. Start React

Open a second terminal:

```bash
cd client
npm install
npm run dev
```

Open the URL printed by Vite, normally `http://localhost:5173`.

If port `8000` is occupied, start FastAPI on another port and point Vite to it:

```bash
# Backend terminal
uv run uvicorn app.main:app --reload --port 8001

# Frontend terminal
VITE_API_TARGET=http://127.0.0.1:8001 npm run dev
```

## Using VoiceLab

1. Open the Builder.
2. Create or select an agent.
3. Configure the model, instruction, STT, TTS, voice, temperature, first message, and tools.
4. Optionally edit the same configuration through the JSON tab.
5. Select **Save config** to persist the agent in Postgres.
6. Select **Test call** and grant browser microphone permission.
7. Review session and trace information under **Test Runs**.

## Development Checks

Backend:

```bash
cd server
uv run ruff check .
uv run pytest -q
```

Frontend:

```bash
cd client
npm run build
```

## Database Commands

Apply migrations:

```bash
cd server
uv run alembic upgrade head
```

Create a migration after changing SQLAlchemy models:

```bash
uv run alembic revision --autogenerate -m "describe the change"
```

Roll back one migration:

```bash
uv run alembic downgrade -1
```

Stop Postgres:

```bash
docker compose down
```

Delete the local database volume too:

```bash
docker compose down -v
```

## Troubleshooting

### Port 5433 is already in use

Change the host-side port in `docker-compose.yml`, then update `DATABASE_URL` and `ADK_DATABASE_URL` in `server/.env` to match.

### Database password authentication failed

Make sure the URLs use the Compose credentials:

```text
user: voicelab
password: voicelab
database: voicelab
host port: 5433
```

If an old volume was created with different credentials, reset it:

```bash
docker compose down -v
docker compose up -d postgres
uv run alembic upgrade head
```

### Frontend cannot reach FastAPI

Confirm FastAPI is healthy:

```bash
curl http://localhost:8000/health
```

If FastAPI is using another port, set `VITE_API_TARGET` when starting the client and include the frontend origin in `CORS_ORIGINS`.

## Current Status

- The reference HTML design has been converted into React components.
- Agent configuration, persistence APIs, Postgres models, migrations, and ADK session-service wiring are implemented.
- `pipecat-adk` is installed directly from its GitHub repository.
- The test-call WebSocket creates sessions, validates runtime configuration, synthesizes the saved first message with ElevenLabs, and sends browser-playable audio.
- Complete microphone audio streaming, STT-driven user turns, continuous TTS responses, and deployment execution remain follow-up work.
