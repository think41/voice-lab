import json
from pathlib import Path
from typing import Any

from app.audio_evaluations.schemas import SessionConfigRead
from pipeline.custom_processors.metrics.pricing import session_totals
from pipeline.tts.tts_evaluation_pricing import (
    compute_all_model_costs as compute_all_tts_model_costs,
)


def load_metrics_summary(metrics_path: Path) -> dict[str, Any] | None:
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


def resolve_tts_model_costs(payload: dict[str, Any]) -> dict[str, dict[str, float]]:
    characters = payload.get("session_tts_sent_characters")
    if characters is not None:
        return compute_all_tts_model_costs(int(characters))
    return payload.get("session_tts_model_costs_usd") or {}


def extract_session_config(trace_events: list[Any]) -> SessionConfigRead | None:
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


def extract_usage_llm(trace_events: list[Any]) -> dict[str, Any]:
    totals = session_totals(trace_events)["llm"]
    return {
        "prompt_tokens": int(totals["prompt_tokens"]),
        "completion_tokens": int(totals["completion_tokens"]),
        "total_tokens": int(totals["total_tokens"]),
        "cost_usd": float(totals["cost_usd"]),
    }


def extract_usage_stt(trace_events: list[Any]) -> dict[str, float | None]:
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
