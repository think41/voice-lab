from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db_session
from app.repositories.agent_repository import AgentRepository
from app.repositories.run_repository import RunRepository
from app.schemas.agent import AgentConfig
from app.services.pipecat_adk_runtime import PipecatAdkRuntime

router = APIRouter(prefix="/test-call", tags=["test-call"])
SessionDep = Annotated[AsyncSession, Depends(get_db_session)]


class TestSessionCreate(BaseModel):
    agent_id: str
    user_id: str = "local-user"


class TestSessionRead(BaseModel):
    run_id: str
    adk_session_id: str
    websocket_url: str


@router.post("/session", response_model=TestSessionRead, status_code=201)
async def create_test_session(
    payload: TestSessionCreate, session: SessionDep
) -> TestSessionRead:
    agent = await AgentRepository(session).get(payload.agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")

    adk_session_id = f"test-{uuid4()}"
    run = await RunRepository(session).create(agent_id=agent.id, adk_session_id=adk_session_id)
    return TestSessionRead(
        run_id=run.id,
        adk_session_id=adk_session_id,
        websocket_url=f"/api/test-call/ws/{run.id}",
    )


@router.websocket("/ws/{run_id}")
async def test_call_socket(websocket: WebSocket, run_id: str, session: SessionDep) -> None:
    await websocket.accept()
    runtime = PipecatAdkRuntime()
    await websocket.send_json({"type": "session.ready", "run_id": run_id})
    try:
        while True:
            message = await websocket.receive_json()
            if message.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
            elif message.get("type") == "start":
                await runtime.validate_environment()
                await websocket.send_json({"type": "runtime.ready"})
                run = await RunRepository(session).get(run_id)
                if run is None:
                    raise RuntimeError("Test run not found")
                event = await runtime.synthesize_first_message(
                    AgentConfig.model_validate(run.agent.config)
                )
                await websocket.send_json({"type": event.type, **event.payload})
            else:
                await websocket.send_json({"type": "event.echo", "payload": message})
    except WebSocketDisconnect:
        return
    except Exception as exc:
        await websocket.send_json({"type": "runtime.error", "message": str(exc)})
        await websocket.close()
