import asyncio

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.run import RunRecord
from app.models.trace_event import TraceEventRecord

# Per-run locks serialize sequence-generation across concurrent handlers.
# Voice-lab runs single-worker; this is sufficient. Multi-worker would need
# a DB-side sequence or advisory lock.
_run_locks: dict[str, asyncio.Lock] = {}


def _lock_for(run_id: str) -> asyncio.Lock:
    lock = _run_locks.get(run_id)
    if lock is None:
        lock = asyncio.Lock()
        _run_locks[run_id] = lock
    return lock


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

    async def list_by_agent(self, agent_id: str) -> list[RunRecord]:
        result = await self.session.execute(
            select(RunRecord)
            .where(RunRecord.agent_id == agent_id)
            .order_by(RunRecord.created_at.desc())
        )
        return list(result.scalars())

    async def get(self, run_id: str) -> RunRecord | None:
        result = await self.session.execute(
            select(RunRecord).options(selectinload(RunRecord.agent)).where(RunRecord.id == run_id)
        )
        return result.scalar_one_or_none()

    async def create(
        self, agent_id: str, adk_session_id: str, summary: dict | None = None
    ) -> RunRecord:
        record = RunRecord(
            agent_id=agent_id,
            adk_session_id=adk_session_id,
            summary=summary or {},
        )
        self.session.add(record)
        await self.session.commit()
        await self.session.refresh(record)
        return record

    async def append_trace(
        self, run_id: str, event_type: str, payload: dict
    ) -> int:
        """Atomically read max(sequence), increment, insert. Returns the assigned sequence."""
        async with _lock_for(run_id):
            current = await self._max_trace_sequence(run_id)
            sequence = current + 1
            self.session.add(
                TraceEventRecord(
                    run_id=run_id,
                    sequence=sequence,
                    event_type=event_type,
                    payload=payload,
                )
            )
            await self.session.commit()
            return sequence

    async def _max_trace_sequence(self, run_id: str) -> int:
        result = await self.session.execute(
            select(func.max(TraceEventRecord.sequence)).where(TraceEventRecord.run_id == run_id)
        )
        return result.scalar_one_or_none() or 0
