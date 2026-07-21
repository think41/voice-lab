from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.audio_evaluations.schemas import AudioEvaluationRead
from app.audio_evaluations.service import (
    extract_session_config,
    extract_usage_stt,
    load_metrics_summary,
    resolve_tts_model_costs,
)
from app.config import get_settings
from app.db import get_db_session
from app.runs.service import RunRepository
from pipeline.stt.stt_evaluation_pricing import compute_all_model_costs
from pipeline.stt.stt_evaluation_store import resolve_recordings_root

router = APIRouter(prefix="/audio-evaluations", tags=["audio-evaluations"])
SessionDep = Annotated[AsyncSession, Depends(get_db_session)]


@router.get("/agent/{agent_id}", response_model=list[AudioEvaluationRead])
async def list_audio_evaluations(agent_id: str, session: SessionDep) -> list[AudioEvaluationRead]:
    settings = get_settings()
    recordings_root = resolve_recordings_root(settings.stt_evaluation_recordings_dir)
    runs = await RunRepository(session).list_by_agent(agent_id)

    records: list[AudioEvaluationRead] = []
    for run in runs:
        metrics_path = recordings_root / run.adk_session_id / "metrics.jsonl"
        if not metrics_path.exists():
            continue
        payload = load_metrics_summary(metrics_path)
        if payload is None:
            continue
        usage = extract_usage_stt(run.trace_events)
        session_config = extract_session_config(run.trace_events)
        records.append(
            AudioEvaluationRead(
                session_id=run.adk_session_id,
                run_id=run.id,
                adk_session_id=run.adk_session_id,
                created_at=run.created_at.isoformat(),
                turn_count=payload["turn_count"],
                session_stt_duration_sec=usage["streamed_seconds"]
                or payload["session_stt_duration_sec"],
                streamed_seconds=usage["streamed_seconds"],
                stt_cost_usd=usage["cost_usd"],
                session_model_costs_usd=compute_all_model_costs(
                    usage["streamed_seconds"] or payload["session_stt_duration_sec"]
                ),
                file_paths=payload["file_paths"],
                session_tts_sent_characters=payload["session_tts_sent_characters"],
                session_tts_model_costs_usd=resolve_tts_model_costs(payload),
                session_stt_latency_ms=payload["session_stt_latency_ms"],
                session_tts_latency_ms=payload["session_tts_latency_ms"],
                session_config=session_config,
            )
        )
    return records
