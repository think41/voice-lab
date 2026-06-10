import asyncio
import json
import logging
import time
from typing import Annotated, Any
from urllib.parse import urlencode
from uuid import uuid4

import websockets
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from websockets.asyncio.client import ClientConnection

from app.core.config import get_settings
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
async def create_test_session(payload: TestSessionCreate, session: SessionDep) -> TestSessionRead:
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

    trace_count = len(run.trace_events)

    async def record_trace(event_type: str, trace_payload: dict[str, Any]) -> None:
        nonlocal trace_count
        trace_count += 1
        await run_repository.append_trace(
            run_id=run_id,
            sequence=trace_count,
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
        )
    except RuntimeError as exc:
        await record_trace("runtime.error", {"message": str(exc), "source": "text_chat"})
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    await record_trace("agent.text", {"role": "assistant", "text": assistant_text, "mode": "text"})
    return TextTurnRead(run_id=run_id, user_text=message, assistant_text=assistant_text)


@router.websocket("/ws/{run_id}")
async def test_call_socket(websocket: WebSocket, run_id: str, session: SessionDep) -> None:
    await websocket.accept()
    logger.info("test-call websocket accepted run_id=%s", run_id)

    runtime = PipecatAdkRuntime()
    send_lock = asyncio.Lock()
    deepgram_ws: ClientConnection | None = None
    deepgram_task: asyncio.Task[None] | None = None
    config: AgentConfig | None = None
    adk_session_id: str | None = None
    user_id = "local-user"
    last_final_transcript = ""
    last_final_transcript_at = 0.0
    trace_sequence = 0

    async def send_json(payload: dict[str, Any]) -> None:
        async with send_lock:
            await websocket.send_json(payload)

    async def record_trace(event_type: str, payload: dict[str, Any]) -> None:
        nonlocal trace_sequence
        trace_sequence += 1
        await RunRepository(session).append_trace(
            run_id=run_id,
            sequence=trace_sequence,
            event_type=event_type,
            payload=payload,
        )

    async def handle_final_transcript(transcript: str) -> None:
        nonlocal last_final_transcript, last_final_transcript_at
        if config is None or adk_session_id is None:
            logger.warning("test-call transcript ignored before runtime start run_id=%s", run_id)
            return
        transcript = transcript.strip()
        now = time.monotonic()
        if transcript == last_final_transcript and now - last_final_transcript_at < 5:
            logger.info(
                "test-call duplicate transcript ignored run_id=%s text=%s", run_id, transcript
            )
            return
        last_final_transcript = transcript
        last_final_transcript_at = now
        logger.info(
            "test-call final transcript run_id=%s chars=%d text=%s",
            run_id,
            len(transcript),
            transcript,
        )
        await record_trace("transcript.final", {"role": "user", "text": transcript})
        await send_json({"type": "transcript.final", "text": transcript})
        response_text = await runtime.generate_agent_response(
            config=config,
            session_id=adk_session_id,
            user_text=transcript,
            user_id=user_id,
        )
        await record_trace("agent.text", {"role": "assistant", "text": response_text})
        await send_json({"type": "agent.text", "text": response_text})
        audio_event = await runtime.synthesize_text(config, response_text)
        await record_trace(
            "audio.output",
            {
                "role": "assistant",
                "text": response_text,
                "mime_type": audio_event.payload.get("mime_type"),
            },
        )
        await send_json({"type": audio_event.type, **audio_event.payload})
        logger.info(
            "test-call response audio sent run_id=%s response_chars=%d", run_id, len(response_text)
        )

    async def listen_to_deepgram(connection: ClientConnection) -> None:
        final_segments: list[str] = []
        latest_partial = ""
        finalize_task: asyncio.Task[None] | None = None

        async def flush_transcript() -> None:
            nonlocal latest_partial
            utterance = " ".join(final_segments).strip() or latest_partial.strip()
            final_segments.clear()
            latest_partial = ""
            if utterance:
                await handle_final_transcript(utterance)

        def schedule_partial_flush() -> None:
            nonlocal finalize_task

            async def delayed_flush() -> None:
                await asyncio.sleep(1.1)
                await flush_transcript()

            if finalize_task is not None and not finalize_task.done():
                finalize_task.cancel()
            finalize_task = asyncio.create_task(delayed_flush())

        try:
            async for raw in connection:
                data = json.loads(raw)
                event_type = data.get("type")
                if event_type == "UtteranceEnd":
                    if finalize_task is not None and not finalize_task.done():
                        finalize_task.cancel()
                    await flush_transcript()
                    continue
                if event_type and event_type != "Results":
                    logger.debug("deepgram event run_id=%s type=%s", run_id, event_type)
                    continue

                alternatives = data.get("channel", {}).get("alternatives", [])
                transcript = (alternatives[0].get("transcript") if alternatives else "") or ""
                transcript = transcript.strip()
                if not transcript:
                    continue
                if data.get("is_final"):
                    final_segments.append(transcript)
                    latest_partial = ""
                    schedule_partial_flush()
                elif transcript != latest_partial:
                    latest_partial = transcript
                    await send_json({"type": "transcript.partial", "text": transcript})
                    schedule_partial_flush()
                if data.get("speech_final"):
                    if finalize_task is not None and not finalize_task.done():
                        finalize_task.cancel()
                    await flush_transcript()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("deepgram listener failed run_id=%s", run_id)
            await record_trace("runtime.error", {"message": str(exc), "source": "deepgram"})
            await send_json({"type": "runtime.error", "message": str(exc)})
        finally:
            if finalize_task is not None and not finalize_task.done():
                finalize_task.cancel()

    try:
        await send_json({"type": "session.ready", "run_id": run_id})
        while True:
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                raise WebSocketDisconnect

            text_message = message.get("text")
            audio_bytes = message.get("bytes")
            if text_message is not None:
                payload = json.loads(text_message)
                message_type = payload.get("type")
                logger.info("test-call websocket message run_id=%s type=%s", run_id, message_type)

                if message_type == "ping":
                    await send_json({"type": "pong"})
                    continue
                if message_type == "stop":
                    logger.info("test-call stop requested run_id=%s", run_id)
                    break
                if message_type != "start":
                    await send_json({"type": "event.echo", "payload": payload})
                    continue

                await runtime.validate_environment()
                run = await RunRepository(session).get(run_id)
                if run is None:
                    raise RuntimeError("Test run not found")
                config = AgentConfig.model_validate(run.agent.config)
                adk_session_id = run.adk_session_id
                sample_rate = int(payload.get("sample_rate") or 48000)
                deepgram_ws = await _open_deepgram_stream(config, sample_rate)
                deepgram_task = asyncio.create_task(listen_to_deepgram(deepgram_ws))
                await record_trace(
                    "session.started",
                    {
                        "sample_rate": sample_rate,
                        "stt_provider": config.stt_provider,
                        "stt_model": config.stt_model,
                        "tts_provider": config.tts_provider,
                        "tts_voice": config.tts_voice,
                    },
                )
                await send_json({"type": "runtime.ready", "sample_rate": sample_rate})
                logger.info(
                    "test-call started run_id=%s agent_id=%s stt=%s/%s sample_rate=%d tts=%s/%s",
                    run_id,
                    run.agent_id,
                    config.stt_provider,
                    config.stt_model,
                    sample_rate,
                    config.tts_provider,
                    config.tts_voice,
                )
                first_event = await runtime.synthesize_first_message(config)
                await record_trace(
                    "audio.output",
                    {
                        "role": "assistant",
                        "text": config.first_message,
                        "mime_type": first_event.payload.get("mime_type"),
                    },
                )
                await send_json({"type": first_event.type, **first_event.payload})
                logger.info(
                    "test-call first message sent run_id=%s type=%s", run_id, first_event.type
                )
                continue

            if audio_bytes is not None:
                if deepgram_ws is None:
                    logger.debug(
                        "test-call audio ignored before deepgram ready run_id=%s bytes=%d",
                        run_id,
                        len(audio_bytes),
                    )
                    continue
                await deepgram_ws.send(audio_bytes)
                logger.debug(
                    "test-call audio forwarded run_id=%s bytes=%d", run_id, len(audio_bytes)
                )
    except WebSocketDisconnect:
        logger.info("test-call websocket disconnected run_id=%s", run_id)
    except Exception as exc:
        logger.exception("test-call websocket failed run_id=%s", run_id)
        await record_trace("runtime.error", {"message": str(exc), "source": "websocket"})
        await send_json({"type": "runtime.error", "message": str(exc)})
        await websocket.close()
    finally:
        if deepgram_ws is not None:
            await deepgram_ws.close()
        if deepgram_task is not None:
            deepgram_task.cancel()
            try:
                await deepgram_task
            except asyncio.CancelledError:
                pass
        logger.info("test-call websocket closed run_id=%s", run_id)


async def _open_deepgram_stream(config: AgentConfig, sample_rate: int) -> ClientConnection:
    settings = get_settings()
    if config.stt_provider != "deepgram":
        raise RuntimeError(f"Unsupported STT provider: {config.stt_provider}")
    if not settings.stt_api_key:
        raise RuntimeError("STT_API_KEY is required to transcribe microphone audio")

    query = urlencode(
        {
            "model": config.stt_model,
            "encoding": "linear16",
            "sample_rate": str(sample_rate),
            "channels": "1",
            "interim_results": "true",
            "punctuate": "true",
            "smart_format": "true",
            "endpointing": "300",
            "utterance_end_ms": "1000",
        }
    )
    logger.info("deepgram stream opening model=%s sample_rate=%d", config.stt_model, sample_rate)
    return await websockets.connect(
        f"wss://api.deepgram.com/v1/listen?{query}",
        additional_headers={"Authorization": f"Token {settings.stt_api_key}"},
    )
