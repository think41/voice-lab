import logging
import re

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import agents, audio_evaluations, health, runs, test_call
from app.core.config import get_settings


class _RedactAuthFilter(logging.Filter):
    _pattern = re.compile(r"(Authorization['\"]?\s*:\s*['\"]?Token\s+)([^'\",}\s]+)")

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = self._pattern.sub(r"\1[REDACTED]", record.msg)
        if record.args:
            record.args = tuple(
                self._pattern.sub(r"\1[REDACTED]", arg) if isinstance(arg, str) else arg
                for arg in record.args
            )
        return True


def _install_log_redaction() -> None:
    auth_filter = _RedactAuthFilter()
    for logger_name in ("uvicorn.error", "pipecat", "deepgram"):
        logging.getLogger(logger_name).addFilter(auth_filter)


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="VoiceLab API", version="0.1.0")
    _install_log_redaction()

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    app.include_router(agents.router, prefix="/api")
    app.include_router(audio_evaluations.router, prefix="/api")
    app.include_router(runs.router, prefix="/api")
    app.include_router(test_call.router, prefix="/api")
    return app


app = create_app()
