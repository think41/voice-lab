"""Reconcile stored Deepgram request ids with Deepgram's management API."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx
from sqlalchemy import select

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.models.trace_event import TraceEventRecord
from app.repositories.run_repository import RunRepository

logger = logging.getLogger("uvicorn.error")

_REQUEST_URL = "https://api.deepgram.com/v1/projects/{project_id}/requests/{request_id}"
_DEFAULT_DELAY_SECONDS = 30.0


async def schedule_reconciliation(
    run_id: str, delay_seconds: float = _DEFAULT_DELAY_SECONDS
) -> None:
    try:
        await asyncio.sleep(delay_seconds)
        await reconcile_run(run_id)
    except Exception:
        logger.exception("deepgram reconciliation failed run_id=%s", run_id)


async def reconcile_run(run_id: str) -> int:
    settings = get_settings()
    management_key = settings.deepgram_management_api_key
    project_id = settings.deepgram_project_id
    if not management_key or not project_id:
        logger.info(
            "deepgram reconciliation skipped run_id=%s (management key or project id missing)",
            run_id,
        )
        return 0

    async with SessionLocal() as session:
        captured, already_reconciled = await _load_state(session, run_id)
        pending = [(request_id, kind) for request_id, kind in captured if request_id not in already_reconciled]
        if not pending:
            return 0

        repo = RunRepository(session)
        async with httpx.AsyncClient(timeout=15.0) as client:
            written = 0
            for request_id, kind in pending:
                try:
                    detail = await _fetch_request(client, project_id, management_key, request_id)
                except Exception as exc:
                    logger.warning(
                        "deepgram reconciliation fetch failed run_id=%s request_id=%s: %s",
                        run_id,
                        request_id,
                        exc,
                    )
                    continue
                payload = _parse_detail(kind, request_id, detail)
                if payload is None:
                    continue
                await repo.append_trace(run_id=run_id, event_type="provider.usage", payload=payload)
                written += 1
        return written


async def _load_state(session, run_id: str) -> tuple[list[tuple[str, str]], set[str]]:
    result = await session.execute(
        select(TraceEventRecord.event_type, TraceEventRecord.payload).where(
            TraceEventRecord.run_id == run_id,
            TraceEventRecord.event_type.in_(
                ["stt.provider_request", "tts.provider_request", "provider.usage"]
            ),
        )
    )
    captured: list[tuple[str, str]] = []
    reconciled: set[str] = set()
    for event_type, payload in result.all():
        if not isinstance(payload, dict) or payload.get("provider") != "deepgram":
            continue
        if event_type == "provider.usage":
            request_id = payload.get("request_id")
            if request_id:
                reconciled.add(str(request_id))
            continue

        request_id = payload.get("provider_request_id")
        if not request_id:
            continue
        captured.append((str(request_id), _kind_from_event_type(event_type)))
    return captured, reconciled


async def _fetch_request(
    client: httpx.AsyncClient, project_id: str, management_key: str, request_id: str
) -> dict[str, Any]:
    url = _REQUEST_URL.format(project_id=project_id, request_id=request_id)
    response = await client.get(url, headers={"Authorization": f"Token {management_key}"})
    response.raise_for_status()
    return response.json()


def _parse_detail(kind: str, request_id: str, detail: dict[str, Any]) -> dict[str, Any] | None:
    response = detail.get("response") or {}
    details = response.get("details") or {}
    usd = details.get("usd")
    if usd is None:
        return None

    payload: dict[str, Any] = {
        "provider": "deepgram",
        "kind": kind,
        "request_id": request_id,
        "usd": float(usd),
        "method": details.get("method"),
        "deployment": details.get("deployment"),
        "models": details.get("models") or [],
    }

    if kind == "stt":
        payload["duration_s"] = details.get("duration") or details.get("total_audio")
        payload["tier"] = details.get("tier")
        payload["features"] = details.get("features") or []
    elif kind == "tts":
        tts_details = response.get("tts_details") or {}
        segments = tts_details.get("speech_segments") or []
        payload["characters"] = sum(int(segment.get("characters") or 0) for segment in segments)
        if segments:
            payload["tier"] = segments[0].get("tier")

    return payload


def _kind_from_event_type(event_type: str) -> str:
    return "stt" if event_type.startswith("stt.") else "tts"
