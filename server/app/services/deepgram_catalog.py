"""Fetch Deepgram's TTS voice + STT model catalog live from `/v1/models`.

Deepgram ignores unknown query params (verified against `?language=hi`), so we
fetch the full catalog once and filter in Python. Result is cached in-memory
for 6h; on any HTTP/network failure we fall back to a bundled JSON so the FE
dropdowns never break.

Filter: English-only, streaming-capable STT (nova-2/nova-3), aura/aura-2 TTS.
"""

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
_FALLBACK_PATH = Path(__file__).parent / "_deepgram_fallback.json"

_cache: dict[str, Any] | None = None
_cache_expires_at: float = 0.0
_lock = asyncio.Lock()


async def get_catalog() -> dict[str, list[dict[str, Any]]]:
    """Return `{"tts": [...], "stt": [...]}`. Cached; falls back to bundled JSON."""
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
            logger.warning("deepgram catalog fetch failed, using fallback: %s", exc)
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
    api_key = settings.stt_api_key or settings.tts_api_key
    if not api_key:
        raise RuntimeError("no Deepgram API key configured (STT_API_KEY/TTS_API_KEY)")

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(
            _MODELS_URL, headers={"Authorization": f"Token {api_key}"}
        )
        response.raise_for_status()
        raw = response.json()

    return {
        "tts": _normalize_tts(raw.get("tts", [])),
        "stt": _normalize_stt(raw.get("stt", [])),
    }


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
            "canonical_name": canonical,
            "label": label,
            "architecture": entry.get("architecture"),
            "languages": entry.get("languages", []),
            "accent": metadata.get("accent"),
            "age": metadata.get("age"),
            "sample": metadata.get("sample"),
            "image": metadata.get("image"),
            "tags": metadata.get("tags") or [],
        }
    return sorted(seen.values(), key=lambda v: (v["architecture"] != "aura-2", v["label"]))


def _normalize_stt(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for entry in entries:
        if not entry.get("streaming"):
            continue
        if entry.get("architecture") not in {"nova-2", "nova-3"}:
            continue
        if not _has_english(entry.get("languages", [])):
            continue
        canonical = entry.get("canonical_name")
        if not canonical:
            continue
        existing = merged.get(canonical)
        if existing:
            langs = set(existing["languages"]) | set(entry.get("languages", []))
            existing["languages"] = sorted(langs)
        else:
            merged[canonical] = {
                "canonical_name": canonical,
                "label": _titleize(canonical),
                "architecture": entry.get("architecture"),
                "languages": sorted(set(entry.get("languages", []))),
                "multilingual": bool(entry.get("multilingual")),
            }
    return sorted(
        merged.values(), key=lambda v: (v["architecture"] != "nova-3", v["label"])
    )


def _titleize(name: str) -> str:
    return " ".join(part.capitalize() for part in name.replace("_", "-").split("-"))


def _load_fallback() -> dict[str, list[dict[str, Any]]]:
    with _FALLBACK_PATH.open("r", encoding="utf-8") as fp:
        return json.load(fp)
