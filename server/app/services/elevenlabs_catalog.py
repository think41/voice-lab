"""Fetch ElevenLabs TTS voices live from `/v1/voices`."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Any

import httpx

from app.core.config import get_settings

logger = logging.getLogger("uvicorn.error")

_VOICES_URL = "https://api.elevenlabs.io/v1/voices"
_CACHE_TTL_SECONDS = 6 * 60 * 60
_FALLBACK_PATH = Path(__file__).parent / "_elevenlabs_fallback.json"

_cache: dict[str, Any] | None = None
_cache_expires_at: float = 0.0
_lock = asyncio.Lock()


async def get_catalog() -> dict[str, list[dict[str, Any]]]:
    global _cache, _cache_expires_at
    now = time.monotonic()
    if _cache is not None and now < _cache_expires_at:
        return _cache

    async with _lock:
        if _cache is not None and time.monotonic() < _cache_expires_at:
            return _cache
        try:
            catalog = await _fetch_and_normalize()
        except Exception as exc:
            logger.warning("elevenlabs catalog fetch failed, using fallback: %s", exc)
            catalog = _load_fallback()
        _cache = catalog
        _cache_expires_at = time.monotonic() + _CACHE_TTL_SECONDS
        return catalog


def invalidate_cache() -> None:
    global _cache, _cache_expires_at
    _cache = None
    _cache_expires_at = 0.0


async def _fetch_and_normalize() -> dict[str, list[dict[str, Any]]]:
    settings = get_settings()
    api_key = settings.elevenlabs_api_key
    if not api_key:
        raise RuntimeError("no ElevenLabs API key configured")

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(_VOICES_URL, headers={"xi-api-key": api_key})
        response.raise_for_status()
        raw = response.json()

    voices = raw.get("voices", raw if isinstance(raw, list) else [])
    _log_voice_shape(voices)
    return {"tts": _normalize_tts(voices)}


def _normalize_tts(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for entry in entries:
        voice_id = entry.get("voice_id")
        if not voice_id:
            continue
        labels = entry.get("labels") or {}
        accent = labels.get("accent") or labels.get("language")
        normalized.append(
            {
                "voice_id": voice_id,
                "label": entry.get("name") or voice_id,
                "provider": "elevenlabs",
                "sample": entry.get("preview_url"),
                "accent": accent,
            }
        )
    return sorted(normalized, key=lambda value: value["label"])


def _log_voice_shape(entries: list[dict[str, Any]]) -> None:
    if not entries:
        logger.info("elevenlabs catalog returned no voices")
        return
    first = entries[0]
    if not isinstance(first, dict):
        logger.info("elevenlabs catalog first voice is not a mapping: %s", type(first).__name__)
        return
    preview_subset = {
        "voice_id": first.get("voice_id"),
        "name": first.get("name"),
        "preview_url": first.get("preview_url"),
        "labels": first.get("labels"),
        "category": first.get("category"),
        "fine_tuning": first.get("fine_tuning"),
        "available_for_tiers": first.get("available_for_tiers"),
    }
    logger.info(
        "elevenlabs catalog first voice keys=%s preview_subset=%s",
        sorted(first.keys()),
        preview_subset,
    )


def _load_fallback() -> dict[str, list[dict[str, Any]]]:
    with _FALLBACK_PATH.open("r", encoding="utf-8") as fp:
        return json.load(fp)
