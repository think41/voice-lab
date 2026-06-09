from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import AgentRecord
from app.schemas.agent import AgentCreate, AgentUpdate


class AgentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list(self) -> list[AgentRecord]:
        result = await self.session.execute(select(AgentRecord).order_by(AgentRecord.created_at))
        return list(result.scalars())

    async def get(self, agent_id: str) -> AgentRecord | None:
        return await self.session.get(AgentRecord, agent_id)

    async def create(self, payload: AgentCreate) -> AgentRecord:
        record = AgentRecord(name=payload.name, config=payload.config.model_dump())
        self.session.add(record)
        await self.session.commit()
        await self.session.refresh(record)
        return record

    async def update(self, record: AgentRecord, payload: AgentUpdate) -> AgentRecord:
        if payload.name is not None:
            record.name = payload.name
        if payload.config is not None:
            record.config = payload.config.model_dump()
        await self.session.commit()
        await self.session.refresh(record)
        return record
