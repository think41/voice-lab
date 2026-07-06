import re
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db_session
from app.repositories.run_repository import RunRepository
from app.schemas.run import ProviderTraceRead, RunProviderSummary, RunRead, TraceEventRead, UsageSummary
from app.services.pricing import session_totals

router = APIRouter(prefix="/runs", tags=["runs"])
SessionDep = Annotated[AsyncSession, Depends(get_db_session)]

# pipecat-adk writes `<system>[HEARD] invocation_id="..." Candidate only heard: "..."</system>`
# into ADK session history on interruption. If any of that text leaks into a
# trace payload it would surface as noise in the analytics view. Strip defensively.
_HEARD_TAG_PATTERN = re.compile(
    r"<system>\s*\[HEARD\][^<]*</system>", re.IGNORECASE | re.DOTALL
)
_HEARD_INLINE_PATTERN = re.compile(
    r'\[HEARD\]\s*invocation_id="[^"]*"\s*Candidate only heard:\s*"[^"]*"',
    re.IGNORECASE | re.DOTALL,
)


def _scrub_heard(value: Any) -> Any:
    if isinstance(value, str):
        cleaned = _HEARD_TAG_PATTERN.sub("", value)
        cleaned = _HEARD_INLINE_PATTERN.sub("", cleaned)
        return cleaned.strip() if cleaned != value else value
    if isinstance(value, dict):
        return {k: _scrub_heard(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_scrub_heard(v) for v in value]
    return value


def _provider_summary(trace_events: list[Any]) -> RunProviderSummary:
    session_payload = _session_started_payload(trace_events)
    default_transport = "websocket" if session_payload.get("mode") == "pipecat_streaming" else ""

    stt = ProviderTraceRead(
        provider=str(session_payload.get("stt_provider") or ""),
        model=str(session_payload.get("stt_model") or ""),
        transport=default_transport,
    )
    tts = ProviderTraceRead(
        provider=str(session_payload.get("tts_provider") or ""),
        model=str(session_payload.get("tts_model") or session_payload.get("tts_voice") or ""),
        transport=default_transport,
        voice=_string_or_none(session_payload.get("tts_voice")),
    )

    for event in trace_events:
        payload = event.payload or {}
        if event.event_type == "stt.provider_request":
            stt.provider = str(payload.get("provider") or stt.provider)
            stt.model = str(payload.get("model") or stt.model)
            stt.transport = str(payload.get("transport") or stt.transport)
            stt.voice = _string_or_none(payload.get("voice")) or stt.voice
            stt.provider_request_id = _string_or_none(payload.get("provider_request_id"))
            stt.provider_lookup_available = bool(stt.provider_request_id)
            stt.unavailable_reason = None if stt.provider_lookup_available else stt.unavailable_reason
        elif event.event_type == "tts.provider_request":
            tts.provider = str(payload.get("provider") or tts.provider)
            tts.model = str(payload.get("model") or tts.model)
            tts.transport = str(payload.get("transport") or tts.transport)
            tts.voice = _string_or_none(payload.get("voice")) or tts.voice
            tts.provider_request_id = _string_or_none(payload.get("provider_request_id"))
            tts.provider_lookup_available = bool(tts.provider_request_id)
            tts.unavailable_reason = None if tts.provider_lookup_available else tts.unavailable_reason
        elif event.event_type == "usage.tts":
            tts.model = str(payload.get("model") or tts.model)
        elif event.event_type == "usage.stt":
            stt.model = str(payload.get("model") or stt.model)
        elif event.event_type == "provider.usage" and payload.get("provider") == "deepgram":
            kind = str(payload.get("kind") or "")
            target = stt if kind == "stt" else tts if kind == "tts" else None
            if target is None:
                continue
            target.provider_cost_usd = _float_or_none(payload.get("usd"))
            target.method = _string_or_none(payload.get("method"))
            target.tier = _string_or_none(payload.get("tier"))
            target.deployment = _string_or_none(payload.get("deployment"))
            target.provider_models = [
                str(model_id)
                for model_id in (payload.get("models") or [])
                if isinstance(model_id, str) and model_id.strip()
            ]
            target.features = [
                str(feature)
                for feature in (payload.get("features") or [])
                if isinstance(feature, str) and feature.strip()
            ]

    if not stt.provider_lookup_available:
        stt.unavailable_reason = _provider_unavailable_reason(component="stt", provider=stt.provider, transport=stt.transport)
    if not tts.provider_lookup_available:
        tts.unavailable_reason = _provider_unavailable_reason(component="tts", provider=tts.provider, transport=tts.transport)

    return RunProviderSummary(stt=stt, tts=tts)


def _provider_unavailable_reason(*, component: str, provider: str, transport: str) -> str | None:
    provider = provider.lower()
    transport = transport.lower()
    if component == "tts" and provider == "elevenlabs" and transport == "websocket":
        return "ElevenLabs TTS over websocket does not expose a provider request id"
    if not provider:
        return None
    return "Provider request id unavailable for this provider path"


def _string_or_none(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value
    return None


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _session_started_payload(trace_events: list[Any]) -> dict[str, Any]:
    for event in trace_events:
        if event.event_type == "session.started" and isinstance(event.payload, dict):
            return event.payload
    return {}


@router.get("", response_model=list[RunRead])
async def list_runs(session: SessionDep) -> list[RunRead]:
    records = await RunRepository(session).list()
    return [
        RunRead(
            id=record.id,
            agent_id=record.agent_id,
            adk_session_id=record.adk_session_id,
            status=record.status,
            summary=record.summary,
            created_at=record.created_at,
            trace_events=[
                TraceEventRead(
                    id=event.id,
                    sequence=event.sequence,
                    event_type=event.event_type,
                    payload=_scrub_heard(event.payload),
                    created_at=event.created_at,
                )
                for event in record.trace_events
            ],
            usage_summary=UsageSummary.model_validate(session_totals(record.trace_events)),
            provider_summary=_provider_summary(record.trace_events),
        )
        for record in records
    ]
