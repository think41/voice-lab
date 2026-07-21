import re
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db_session
from app.runs.schemas import RunRead, TraceEventRead
from app.runs.service import RunRepository
from pipeline.custom_processors.metrics.pricing import session_totals

router = APIRouter(prefix="/runs", tags=["runs"])
SessionDep = Annotated[AsyncSession, Depends(get_db_session)]

# pipecat-adk writes `<system>[HEARD] invocation_id="..." Candidate only heard: "..."</system>`
# into ADK session history on interruption. If any of that text leaks into a
# trace payload it would surface as noise in the analytics view. Strip defensively.
_HEARD_TAG_PATTERN = re.compile(
    r"<system>\s*\[HEARD\][^<]*</system>", re.IGNORECASE | re.DOTALL
)
_HEARD_INLINE_PATTERN = re.compile(
    r'\[HEARD\]\s*invocation_id="[^"]*"\s*Candidate only heard:\s*"[^"]*"',
    re.IGNORECASE | re.DOTALL,
)


def _scrub_heard(value: Any) -> Any:
    if isinstance(value, str):
        cleaned = _HEARD_TAG_PATTERN.sub("", value)
        cleaned = _HEARD_INLINE_PATTERN.sub("", cleaned)
        return cleaned.strip() if cleaned != value else value
    if isinstance(value, dict):
        return {k: _scrub_heard(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_scrub_heard(v) for v in value]
    return value

@router.get("", response_model=list[RunRead])
async def list_runs(session: SessionDep) -> list[RunRead]:
    records = await RunRepository(session).list()
    return [
        RunRead(
            id=record.id,
            agent_id=record.agent_id,
            adk_session_id=record.adk_session_id,
            status=record.status,
            summary=record.summary,
            usage=session_totals(record.trace_events),
            created_at=record.created_at,
            trace_events=[
                TraceEventRead(
                    id=event.id,
                    sequence=event.sequence,
                    event_type=event.event_type,
                    payload=_scrub_heard(event.payload),
                    created_at=event.created_at,
                )
                for event in record.trace_events
            ],
        )
        for record in records
    ]
