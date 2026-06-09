# VoiceLab

VoiceLab is a React and FastAPI application for designing and testing voice agents powered by Pipecat ADK.

The first implementation target is an ElevenLabs-inspired workspace where a user configures a single voice agent in the UI, saves that configuration, and runs a browser-microphone test call against a FastAPI backend.

## Planned Stack

- React, TypeScript, Vite, Tailwind CSS
- Python 3.12, FastAPI
- Postgres for application data and ADK session storage
- `pipecat-adk` from `https://github.com/recruit41/pipecat-adk`

## Notes

- All visible UI is implemented in React.
- `client/index.html` is only the Vite mount shell.
- The reference HTML mockup is used only as a design and interaction reference.
