from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from app.core.config import Settings
from app.services.stt_evaluation_pricing import (
    compute_all_model_costs,
    compute_duration_seconds,
    compute_session_model_costs,
)
from app.services.stt_evaluation_store import SttEvaluationStore
from app.services.tts_evaluation_pricing import (
    compute_all_model_costs as compute_all_tts_model_costs,
)

TraceRecorder = Callable[[str, dict[str, object]], Awaitable[None]]


class SttEvaluationSession:
    def __init__(
        self,
        *,
        settings: Settings,
        session_id: str,
        run_id: str,
        record_trace: TraceRecorder,
    ) -> None:
        self._session_id = session_id
        self._run_id = run_id
        self._record_trace = record_trace
        self._store = SttEvaluationStore(settings.stt_evaluation_recordings_dir)
        self._turn_index = 0
        self._session_duration_sec = 0.0
        self._lock = asyncio.Lock()

    @property
    def session_duration_sec(self) -> float:
        return round(self._session_duration_sec, 3)

    async def handle_user_turn_audio(
        self, audio: bytes, sample_rate: int, num_channels: int
    ) -> None:
        duration_sec = compute_duration_seconds(
            audio,
            sample_rate=sample_rate,
            num_channels=num_channels,
        )
        if duration_sec <= 0:
            return

        async with self._lock:
            self._turn_index += 1
            turn = f"T{self._turn_index}"
            self._session_duration_sec = round(self._session_duration_sec + duration_sec, 3)

        saved = await self._store.save_user_turn_audio(
            session_id=self._session_id,
            turn=turn,
            audio=audio,
            duration_sec=duration_sec,
            sample_rate=sample_rate,
            num_channels=num_channels,
        )

        await self._store.append_metrics(
            self._session_id,
            {
                "type": "turn.audio",
                "session_id": self._session_id,
                "run_id": self._run_id,
                "turn": turn,
                "speaker": "user",
                "file_path": saved.file_path,
                "duration_sec": duration_sec,
                "sample_rate": sample_rate,
                "num_channels": num_channels,
                "all_model_costs_usd": compute_all_model_costs(duration_sec),
            },
        )
        await self._record_trace(
            "evaluation.stt.turn_captured",
            {
                "turn": turn,
                "speaker": "user",
                "file_path": saved.file_path,
                "duration_sec": duration_sec,
            },
        )

    async def finalize(
        self,
        *,
        tts_sent_characters: int | None = None,
        stt_latency: dict[str, Any] | None = None,
        tts_latency: dict[str, Any] | None = None,
    ) -> None:
        summary: dict[str, Any] = {
            "type": "session.summary",
            "session_id": self._session_id,
            "run_id": self._run_id,
            "session_stt_duration_sec": round(self._session_duration_sec, 3),
            "session_model_costs_usd": compute_session_model_costs(self._session_duration_sec),
        }
        if tts_sent_characters is not None:
            summary["session_tts_sent_characters"] = int(tts_sent_characters)
            summary["session_tts_model_costs_usd"] = compute_all_tts_model_costs(
                int(tts_sent_characters)
            )
        if stt_latency is not None:
            summary["session_stt_latency_ms"] = stt_latency
        if tts_latency is not None:
            summary["session_tts_latency_ms"] = tts_latency
        await self._store.append_metrics(self._session_id, summary)
        await self._record_trace(
            "evaluation.stt.session_summary",
            {
                "session_stt_duration_sec": round(self._session_duration_sec, 3),
            },
        )
