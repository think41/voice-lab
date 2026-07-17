import logging
from typing import Annotated, Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import get_db_session
from app.repositories.agent_repository import AgentRepository
from app.repositories.run_repository import RunRepository
from app.schemas.agent import AgentConfig
from app.services.pipecat_adk_runtime import PipecatAdkRuntime
from app.services.pipecat_streaming_runtime import PipecatStreamingRuntime

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
    first_message: str | None = None


@router.post("/session", response_model=TestSessionRead, status_code=201)
async def create_test_session(payload: TestSessionCreate, session: SessionDep) -> TestSessionRead:
    agent = await AgentRepository(session).get(payload.agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")

    adk_session_id = f"test-{uuid4()}"
    run = await RunRepository(session).create(
        agent_id=agent.id,
        adk_session_id=adk_session_id,
        summary={},
    )
    logger.info(
        "test-call session created run_id=%s agent_id=%s agent_name=%s",
        run.id,
        agent.id,
        agent.name,
    )
    config = AgentConfig.model_validate(agent.config)
    return TestSessionRead(
        run_id=run.id,
        adk_session_id=adk_session_id,
        websocket_url=f"/api/test-call/stream/ws/{run.id}",
        first_message=config.first_message,
    )


class TextTurnCreate(BaseModel):
    message: str
    user_id: str = "local-user"


class TextTurnRead(BaseModel):
    run_id: str
    user_text: str
    assistant_text: str


@router.post("/session/{run_id}/text", response_model=TextTurnRead)
async def create_text_turn(
    run_id: str, payload: TextTurnCreate, session: SessionDep
) -> TextTurnRead:
    message = payload.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="Message is required")

    run_repository = RunRepository(session)
    run = await run_repository.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")

    runtime = PipecatAdkRuntime()
    settings = get_settings()
    if not settings.gemini_api_key:
        raise HTTPException(status_code=400, detail="GEMINI_API_KEY is required for text chat")

    async def record_trace(event_type: str, trace_payload: dict[str, Any]) -> None:
        await run_repository.append_trace(
            run_id=run_id,
            event_type=event_type,
            payload=trace_payload,
        )

    config = AgentConfig.model_validate(run.agent.config)
    await record_trace("transcript.final", {"role": "user", "text": message, "mode": "text"})
    try:
        assistant_text = await runtime.generate_agent_response(
            config=config,
            session_id=run.adk_session_id,
            user_text=message,
            user_id=payload.user_id,
            record_trace=record_trace,
        )
    except RuntimeError as exc:
        await record_trace("runtime.error", {"message": str(exc), "source": "text_chat"})
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    await record_trace("agent.text", {"role": "assistant", "text": assistant_text, "mode": "text"})
    return TextTurnRead(run_id=run_id, user_text=message, assistant_text=assistant_text)


@router.websocket("/stream/ws/{run_id}")
async def test_call_stream_socket(websocket: WebSocket, run_id: str, session: SessionDep) -> None:
    await websocket.accept()
    logger.info("streaming test-call websocket accepted run_id=%s", run_id)

    run_repository = RunRepository(session)

    async def record_trace(event_type: str, payload: dict[str, Any]) -> None:
        try:
            await run_repository.append_trace(
                run_id=run_id,
                event_type=event_type,
                payload=payload,
            )
        except Exception:
            await session.rollback()
            raise

    try:
        run = await run_repository.get(run_id)
        if run is None:
            raise RuntimeError("Test run not found")
        config = AgentConfig.model_validate(run.agent.config)
        await websocket.send_json({"type": "session.ready", "run_id": run_id})
        await websocket.send_json({"type": "runtime.ready", "sample_rate": 48000})
        runtime = PipecatStreamingRuntime()
        await runtime.run_websocket(
            websocket=websocket,
            config=config,
            run_id=run_id,
            session_id=run.adk_session_id,
            record_trace=record_trace,
            sample_rate=48000,
        )
    except WebSocketDisconnect:
        logger.info("streaming test-call websocket disconnected run_id=%s", run_id)
    except Exception as exc:
        logger.exception("streaming test-call websocket failed run_id=%s", run_id)
        await record_trace("runtime.error", {"message": str(exc), "source": "pipecat_stream"})
        try:
            await websocket.send_json({"type": "runtime.error", "message": str(exc)})
        except Exception:
            pass
    finally:
        logger.info("streaming test-call websocket closed run_id=%s", run_id)
