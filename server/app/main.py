from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.agents.router import router as agents_router
from app.audio_evaluations.router import router as audio_evaluations_router
from app.config import get_settings
from app.health.router import router as health_router
from app.runs.router import router as runs_router
from app.session.router import router as session_router


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="VoiceLab API", version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health_router)
    app.include_router(agents_router, prefix="/api")
    app.include_router(audio_evaluations_router, prefix="/api")
    app.include_router(runs_router, prefix="/api")
    app.include_router(session_router, prefix="/api")
    return app


app = create_app()
