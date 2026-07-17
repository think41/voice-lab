from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.audio_evaluations.schemas import AudioEvaluationRead
from app.audio_evaluations.service import load_metrics_summary
from app.config import get_settings
from app.db import get_db_session
from app.runs.service import RunRepository
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
        records.append(
            AudioEvaluationRead(
                session_id=run.adk_session_id,
                run_id=run.id,
                adk_session_id=run.adk_session_id,
                created_at=run.created_at.isoformat(),
                turn_count=payload["turn_count"],
                session_stt_duration_sec=payload["session_stt_duration_sec"],
                session_model_costs_usd=payload["session_model_costs_usd"],
                provider_session_metrics=payload["provider_session_metrics"],
                file_paths=payload["file_paths"],
                evaluate_mode=payload["evaluate_mode"],
            )
        )
    return records
