import json
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import get_db_session
from app.repositories.run_repository import RunRepository
from app.services.stt_evaluation_pricing import compute_all_model_costs
from app.services.stt_evaluation_store import resolve_recordings_root
from app.services.tts_evaluation_pricing import (
    compute_all_model_costs as compute_all_tts_model_costs,
)

router = APIRouter(prefix="/audio-evaluations", tags=["audio-evaluations"])
SessionDep = Annotated[AsyncSession, Depends(get_db_session)]


class LiveLatencyRead(BaseModel):
    provider: str
    model: str
    count: int
    median_ms: float
    p95_ms: float


class SessionConfigRead(BaseModel):
    stt_provider: str | None = None
    stt_model: str | None = None
    llm_model: str | None = None
    tts_provider: str | None = None
    tts_model: str | None = None
    tts_voice: str | None = None


class AudioEvaluationRead(BaseModel):
    session_id: str
    run_id: str
    adk_session_id: str
    created_at: str
    turn_count: int
    session_stt_duration_sec: float
    streamed_seconds: float
    stt_cost_usd: float | None = None
    session_model_costs_usd: dict[str, dict[str, float]]
    file_paths: list[str]
    session_tts_sent_characters: int | None = None
    session_tts_model_costs_usd: dict[str, dict[str, float]] = Field(default_factory=dict)
    session_stt_latency_ms: LiveLatencyRead | None = None
    session_tts_latency_ms: LiveLatencyRead | None = None
    session_config: SessionConfigRead | None = None


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
        usage = _extract_usage_stt(run.trace_events)
        session_config = _extract_session_config(run.trace_events)
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
                session_tts_model_costs_usd=_resolve_tts_model_costs(payload),
                session_stt_latency_ms=payload["session_stt_latency_ms"],
                session_tts_latency_ms=payload["session_tts_latency_ms"],
                session_config=session_config,
            )
        )
    return records


def _resolve_tts_model_costs(payload: dict[str, Any]) -> dict[str, dict[str, float]]:
    characters = payload.get("session_tts_sent_characters")
    if characters is not None:
        return compute_all_tts_model_costs(int(characters))
    return payload.get("session_tts_model_costs_usd") or {}


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
        "session_tts_sent_characters": (
            int(session_summary["session_tts_sent_characters"])
            if session_summary.get("session_tts_sent_characters") is not None
            else None
        ),
        "session_tts_model_costs_usd": session_summary.get("session_tts_model_costs_usd") or {},
        "session_stt_latency_ms": session_summary.get("session_stt_latency_ms"),
        "session_tts_latency_ms": session_summary.get("session_tts_latency_ms"),
    }


def _extract_session_config(trace_events: list[Any]) -> SessionConfigRead | None:
    for event in trace_events:
        if getattr(event, "event_type", None) != "session.started":
            continue
        payload = getattr(event, "payload", {}) or {}
        return SessionConfigRead(
            stt_provider=payload.get("stt_provider"),
            stt_model=payload.get("stt_model"),
            llm_model=payload.get("llm_model"),
            tts_provider=payload.get("tts_provider"),
            tts_model=payload.get("tts_model"),
            tts_voice=payload.get("tts_voice"),
        )
    return None


def _extract_usage_stt(trace_events: list[Any]) -> dict[str, float | None]:
    for event in reversed(trace_events):
        if getattr(event, "event_type", None) != "usage.stt":
            continue
        payload = getattr(event, "payload", {}) or {}
        return {
            "streamed_seconds": float(payload.get("streamed_seconds") or 0.0),
            "cost_usd": _to_float(payload.get("cost_usd")),
        }
    return {"streamed_seconds": 0.0, "cost_usd": None}


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
