import logging
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
logger = logging.getLogger("uvicorn.error")


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
    logger.info(
        "test-call session created run_id=%s agent_id=%s agent_name=%s",
        run.id,
        agent.id,
        agent.name,
    )
    return TestSessionRead(
        run_id=run.id,
        adk_session_id=adk_session_id,
        websocket_url=f"/api/test-call/ws/{run.id}",
    )


@router.websocket("/ws/{run_id}")
async def test_call_socket(websocket: WebSocket, run_id: str, session: SessionDep) -> None:
    await websocket.accept()
    logger.info("test-call websocket accepted run_id=%s", run_id)
    runtime = PipecatAdkRuntime()
    await websocket.send_json({"type": "session.ready", "run_id": run_id})
    try:
        while True:
            message = await websocket.receive_json()
            logger.info(
                "test-call websocket message run_id=%s type=%s",
                run_id,
                message.get("type"),
            )
            if message.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
            elif message.get("type") == "start":
                await runtime.validate_environment()
                await websocket.send_json({"type": "runtime.ready"})
                run = await RunRepository(session).get(run_id)
                if run is None:
                    raise RuntimeError("Test run not found")
                config = AgentConfig.model_validate(run.agent.config)
                logger.info(
                    "test-call speaking first message run_id=%s agent_id=%s voice=%s chars=%d",
                    run_id,
                    run.agent_id,
                    config.tts_voice,
                    len(config.first_message),
                )
                event = await runtime.synthesize_first_message(config)
                await websocket.send_json({"type": event.type, **event.payload})
                logger.info("test-call first message sent run_id=%s type=%s", run_id, event.type)
            else:
                await websocket.send_json({"type": "event.echo", "payload": message})
    except WebSocketDisconnect:
        logger.info("test-call websocket disconnected run_id=%s", run_id)
        return
    except Exception as exc:
        logger.exception("test-call websocket failed run_id=%s", run_id)
        await websocket.send_json({"type": "runtime.error", "message": str(exc)})
        await websocket.close()
