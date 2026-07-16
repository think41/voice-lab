import json
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import get_db_session
from app.repositories.run_repository import RunRepository
from app.services.stt_evaluation_store import resolve_recordings_root

router = APIRouter(prefix="/audio-evaluations", tags=["audio-evaluations"])
SessionDep = Annotated[AsyncSession, Depends(get_db_session)]


class AudioProviderMetricsRead(BaseModel):
    call_count: int
    success_count: int
    error_count: int
    latency_avg_ms: float
    latency_median_ms: float
    latency_p95_ms: float


class AudioEvaluationRead(BaseModel):
    session_id: str
    run_id: str
    adk_session_id: str
    created_at: str
    turn_count: int
    session_stt_duration_sec: float
    session_model_costs_usd: dict[str, dict[str, float]]
    provider_session_metrics: dict[str, AudioProviderMetricsRead]
    file_paths: list[str]
    evaluate_mode: bool
    session_tts_sent_characters: int | None = None
    session_tts_model_costs_usd: dict[str, dict[str, float]] = Field(default_factory=dict)


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
        payload = _load_metrics_summary(metrics_path)
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
                session_tts_sent_characters=payload["session_tts_sent_characters"],
                session_tts_model_costs_usd=payload["session_tts_model_costs_usd"],
            )
        )
    return records


def _load_metrics_summary(metrics_path: Path) -> dict[str, Any] | None:
    turn_count = 0
    file_paths: list[str] = []
    session_summary: dict[str, Any] | None = None
    with metrics_path.open("r", encoding="utf-8") as metrics_file:
        for line in metrics_file:
            if not line.strip():
                continue
            item = json.loads(line)
            if item.get("type") == "turn.audio":
                turn_count += 1
                file_path = item.get("file_path")
                if isinstance(file_path, str) and file_path:
                    file_paths.append(file_path)
            elif item.get("type") == "session.summary":
                session_summary = item

    if session_summary is None:
        return None

    return {
        "turn_count": turn_count,
        "file_paths": file_paths,
        "session_stt_duration_sec": float(session_summary.get("session_stt_duration_sec") or 0.0),
        "session_model_costs_usd": session_summary.get("session_model_costs_usd") or {},
        "provider_session_metrics": session_summary.get("provider_session_metrics") or {},
        "evaluate_mode": bool(session_summary.get("evaluate_mode", False)),
        "session_tts_sent_characters": (
            int(session_summary["session_tts_sent_characters"])
            if session_summary.get("session_tts_sent_characters") is not None
            else None
        ),
        "session_tts_model_costs_usd": session_summary.get("session_tts_model_costs_usd") or {},
    }
