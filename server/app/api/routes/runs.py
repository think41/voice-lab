from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db_session
from app.repositories.run_repository import RunRepository
from app.schemas.run import RunRead, TraceEventRead

router = APIRouter(prefix="/runs", tags=["runs"])


@router.get("", response_model=list[RunRead])
async def list_runs(session: AsyncSession = Depends(get_db_session)) -> list[RunRead]:
    records = await RunRepository(session).list()
    return [
        RunRead(
            id=record.id,
            agent_id=record.agent_id,
            adk_session_id=record.adk_session_id,
            status=record.status,
            summary=record.summary,
            created_at=record.created_at,
            trace_events=[
                TraceEventRead(
                    id=event.id,
                    sequence=event.sequence,
                    event_type=event.event_type,
                    payload=event.payload,
                    created_at=event.created_at,
                )
                for event in record.trace_events
            ],
        )
        for record in records
    ]
