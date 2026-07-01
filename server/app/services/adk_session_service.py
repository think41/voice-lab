import logging

from google.adk.sessions import DatabaseSessionService

from app.core.config import get_settings

logger = logging.getLogger("uvicorn.error")


def create_adk_session_service() -> DatabaseSessionService:
    settings = get_settings()
    return DatabaseSessionService(db_url=settings.adk_database_url)


async def ensure_adk_session(
    session_service: DatabaseSessionService,
    *,
    app_name: str,
    user_id: str,
    session_id: str,
) -> None:
    """Get-or-create an ADK session. Idempotent across the text and streaming paths."""
    existing = await session_service.get_session(
        app_name=app_name, user_id=user_id, session_id=session_id
    )
    if existing is None:
        await session_service.create_session(
            app_name=app_name, user_id=user_id, session_id=session_id
        )
        logger.info(
            "adk session created app=%s user_id=%s session_id=%s",
            app_name,
            user_id,
            session_id,
        )
