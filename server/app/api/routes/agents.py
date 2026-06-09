from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db_session
from app.repositories.agent_repository import AgentRepository
from app.schemas.agent import AgentCreate, AgentRead, AgentUpdate

router = APIRouter(prefix="/agents", tags=["agents"])


def serialize_agent(record) -> AgentRead:
    return AgentRead(id=record.id, name=record.name, config=record.config)



@router.get("", response_model=list[AgentRead])
async def list_agents(session: AsyncSession = Depends(get_db_session)) -> list[AgentRead]:
    records = await AgentRepository(session).list()
    return [serialize_agent(record) for record in records]


@router.post("", response_model=AgentRead, status_code=201)
async def create_agent(
    payload: AgentCreate, session: AsyncSession = Depends(get_db_session)
) -> AgentRead:
    record = await AgentRepository(session).create(payload)
    return serialize_agent(record)


@router.get("/{agent_id}", response_model=AgentRead)
async def get_agent(agent_id: str, session: AsyncSession = Depends(get_db_session)) -> AgentRead:
    record = await AgentRepository(session).get(agent_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    return serialize_agent(record)


@router.put("/{agent_id}", response_model=AgentRead)
async def update_agent(
    agent_id: str, payload: AgentUpdate, session: AsyncSession = Depends(get_db_session)
) -> AgentRead:
    repository = AgentRepository(session)
    record = await repository.get(agent_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    return serialize_agent(await repository.update(record, payload))
