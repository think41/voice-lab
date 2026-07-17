"""Return curated Deepgram TTS voices, optionally enriched from `/v1/models`."""

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

_MODELS_URL = "https://api.deepgram.com/v1/models"
_CACHE_TTL_SECONDS = 6 * 60 * 60
_CURATED_CATALOG = json.loads(
    (Path(__file__).parent / "_deepgram_fallback.json").read_text(encoding="utf-8")
)

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
        catalog = await _fetch_and_normalize()
        _cache = catalog
        _cache_expires_at = time.monotonic() + _CACHE_TTL_SECONDS
        return catalog


def invalidate_cache() -> None:
    global _cache, _cache_expires_at
    _cache = None
    _cache_expires_at = 0.0


async def _fetch_and_normalize() -> dict[str, list[dict[str, Any]]]:
    settings = get_settings()
    api_key = settings.deepgram_api_key
    if not api_key:
        return _CURATED_CATALOG

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(_MODELS_URL, headers={"Authorization": f"Token {api_key}"})
            response.raise_for_status()
            raw = response.json()
    except Exception as exc:
        logger.warning("deepgram catalog enrichment failed, returning curated voices: %s", exc)
        return _CURATED_CATALOG

    return {"tts": _merge_curated_tts(_normalize_tts(raw.get("tts", [])))}


def _has_english(languages: list[str]) -> bool:
    return any(lang.startswith("en") for lang in languages or [])


def _normalize_tts(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: dict[str, dict[str, Any]] = {}
    for entry in entries:
        if entry.get("architecture") not in {"aura", "aura-2"}:
            continue
        if not _has_english(entry.get("languages", [])):
            continue
        canonical = entry.get("canonical_name")
        if not canonical or canonical in seen:
            continue
        metadata = entry.get("metadata") or {}
        label = metadata.get("display_name") or _titleize(entry.get("name") or canonical)
        seen[canonical] = {
            "voice_id": canonical,
            "label": label,
            "provider": "deepgram",
            "sample": metadata.get("sample"),
            "accent": metadata.get("accent"),
        }
    return sorted(seen.values(), key=lambda value: value["label"])


def _merge_curated_tts(live_entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    live_by_voice_id = {
        str(entry["voice_id"]): entry
        for entry in live_entries
        if isinstance(entry.get("voice_id"), str) and entry["voice_id"]
    }
    merged: list[dict[str, Any]] = []
    for curated in _CURATED_CATALOG.get("tts", []):
        voice_id = curated.get("voice_id")
        if not isinstance(voice_id, str) or not voice_id:
            continue
        live = live_by_voice_id.get(voice_id, {})
        merged.append(
            {
                "voice_id": voice_id,
                "label": live.get("label") or curated.get("label") or voice_id,
                "provider": "deepgram",
                "sample": live.get("sample") or curated.get("sample"),
                "accent": live.get("accent") or curated.get("accent"),
            }
        )
    return merged


def _titleize(name: str) -> str:
    return " ".join(part.capitalize() for part in name.replace("_", "-").split("-"))
