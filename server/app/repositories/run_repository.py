from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.run import RunRecord
from app.models.trace_event import TraceEventRecord


class RunRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list(self) -> list[RunRecord]:
        result = await self.session.execute(
            select(RunRecord)
            .options(selectinload(RunRecord.trace_events))
            .order_by(RunRecord.created_at.desc())
        )
        return list(result.scalars())

    async def create(self, agent_id: str, adk_session_id: str) -> RunRecord:
        record = RunRecord(agent_id=agent_id, adk_session_id=adk_session_id)
        self.session.add(record)
        await self.session.commit()
        await self.session.refresh(record)
        return record

    async def append_trace(
        self, run_id: str, sequence: int, event_type: str, payload: dict
    ) -> None:
        self.session.add(
            TraceEventRecord(
                run_id=run_id,
                sequence=sequence,
                event_type=event_type,
                payload=payload,
            )
        )
        await self.session.commit()
