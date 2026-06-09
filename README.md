# VoiceLab

VoiceLab is a React and FastAPI application for designing and testing voice agents powered by Pipecat ADK.

The first implementation target is an ElevenLabs-inspired workspace where a user configures a single voice agent in the UI, saves that configuration, and runs a browser-microphone test call against a FastAPI backend.

## Stack

- React, TypeScript, Vite, Tailwind CSS
- Python 3.12, FastAPI
- Postgres for application data and ADK session storage
- `pipecat-adk` from `https://github.com/recruit41/pipecat-adk`

## Repository Layout

```text
client/   React-only VoiceLab UI. index.html is only the Vite mount shell.
server/   FastAPI API, Postgres models/migrations, and Pipecat ADK runtime adapter.
```

## Development

Start Postgres:

```bash
docker compose up -d postgres
```

Backend:

```bash
cd server
uv sync
cp .env.example .env
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```

Frontend:

```bash
cd client
npm install
npm run dev
```

If the backend is running on a non-default port, start Vite with:

```bash
VITE_API_TARGET=http://127.0.0.1:8001 npm run dev
```

Open the URL printed by Vite, usually `http://localhost:5173`.

## Notes

- All visible UI is implemented in React.
- `client/index.html` contains only `<div id="root"></div>` and the Vite module script.
- The reference HTML mockup is used only as a design and interaction reference.
- Test calls execute the latest saved UI-configured single root agent.
