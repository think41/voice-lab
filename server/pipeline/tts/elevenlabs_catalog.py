"""Return curated ElevenLabs TTS voices without live catalog fetches."""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any

_CACHE_TTL_SECONDS = 6 * 60 * 60
_CURATED_CATALOG = json.loads(
    (Path(__file__).parent / "_elevenlabs_fallback.json").read_text(encoding="utf-8")
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
        _cache = _CURATED_CATALOG
        _cache_expires_at = time.monotonic() + _CACHE_TTL_SECONDS
        return _cache


def invalidate_cache() -> None:
    global _cache, _cache_expires_at
    _cache = None
    _cache_expires_at = 0.0
