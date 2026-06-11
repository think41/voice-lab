from google.adk.sessions import DatabaseSessionService

from app.core.config import get_settings


def create_adk_session_service() -> DatabaseSessionService:
    settings = get_settings()
    return DatabaseSessionService(db_url=settings.adk_database_url)
