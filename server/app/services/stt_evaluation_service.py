from __future__ import annotations

import asyncio
import logging
import statistics
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from app.core.config import Settings
from app.services.stt_evaluation_pricing import (
    PRODUCTION_MODEL_BY_PROVIDER,
    compute_all_model_costs,
    compute_duration_seconds,
    compute_model_cost,
    compute_session_model_costs,
    pricing_model_name,
)
from app.services.stt_evaluation_store import SavedTurnAudio, SttEvaluationStore
from app.services.tts_evaluation_pricing import (
    compute_all_model_costs as compute_all_tts_model_costs,
)

logger = logging.getLogger("uvicorn.error")
TraceRecorder = Callable[[str, dict[str, object]], Awaitable[None]]


@dataclass(frozen=True)
class ProviderEvaluationResult:
    provider: str
    model: str
    request_id: str | None
    duration_sec: float
    latency_ms: float
    cost_usd: float
    cost_source: str
    transcript: str | None
    status: str
    error: str | None = None
    status_code: int | None = None
    response_text: str | None = None


class SttEvaluationSession:
    def __init__(
        self,
        *,
        settings: Settings,
        session_id: str,
        run_id: str,
        evaluate_mode: bool,
        record_trace: TraceRecorder,
    ) -> None:
        self._settings = settings
        self._session_id = session_id
        self._run_id = run_id
        self._evaluate_mode = evaluate_mode
        self._record_trace = record_trace
        self._store = SttEvaluationStore(settings.stt_evaluation_recordings_dir)
        self._turn_index = 0
        self._session_duration_sec = 0.0
        self._lock = asyncio.Lock()
        self._background_tasks: set[asyncio.Task[None]] = set()
        self._provider_results_by_name: dict[str, list[ProviderEvaluationResult]] = {}

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
        all_model_costs = compute_all_model_costs(duration_sec)

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
                "all_model_costs_usd": all_model_costs,
                "evaluate_mode": self._evaluate_mode,
            },
        )
        await self._record_trace(
            "evaluation.stt.turn_captured",
            {
                "turn": turn,
                "speaker": "user",
                "file_path": saved.file_path,
                "duration_sec": duration_sec,
                "evaluate_mode": self._evaluate_mode,
            },
        )

        if not self._evaluate_mode:
            return

        deepgram_result = await self._evaluate_provider(
            "deepgram",
            model=self._settings.stt_evaluation_deepgram_model
            or PRODUCTION_MODEL_BY_PROVIDER["deepgram"],
            saved=saved,
        )
        await self._record_provider_result(turn, deepgram_result, all_model_costs)

        for provider, model in (
            (
                "elevenlabs",
                self._settings.stt_evaluation_elevenlabs_model
                or PRODUCTION_MODEL_BY_PROVIDER["elevenlabs"],
            ),
            (
                "sarvam",
                self._settings.stt_evaluation_sarvam_model
                or PRODUCTION_MODEL_BY_PROVIDER["sarvam"],
            ),
        ):
            task = asyncio.create_task(
                self._run_background_provider(
                    turn=turn,
                    provider=provider,
                    model=model,
                    saved=saved,
                    all_model_costs=all_model_costs,
                )
            )
            self._background_tasks.add(task)
            task.add_done_callback(self._background_tasks.discard)

    async def finalize(self, *, tts_sent_characters: int | None = None) -> None:
        if self._background_tasks:
            await asyncio.gather(*self._background_tasks, return_exceptions=True)

        summary: dict[str, Any] = {
            "type": "session.summary",
            "session_id": self._session_id,
            "run_id": self._run_id,
            "session_stt_duration_sec": round(self._session_duration_sec, 3),
            "session_model_costs_usd": compute_session_model_costs(self._session_duration_sec),
            "provider_session_metrics": self._provider_session_metrics(),
            "evaluate_mode": self._evaluate_mode,
        }
        if tts_sent_characters is not None:
            summary["session_tts_sent_characters"] = int(tts_sent_characters)
            summary["session_tts_model_costs_usd"] = compute_all_tts_model_costs(
                int(tts_sent_characters)
            )
        await self._store.append_metrics(self._session_id, summary)
        await self._record_trace(
            "evaluation.stt.session_summary",
            {
                "session_stt_duration_sec": round(self._session_duration_sec, 3),
                "provider_session_metrics": self._provider_session_metrics(),
                "evaluate_mode": self._evaluate_mode,
            },
        )

    async def _run_background_provider(
        self,
        *,
        turn: str,
        provider: str,
        model: str,
        saved: SavedTurnAudio,
        all_model_costs: dict[str, dict[str, float]],
    ) -> None:
        result = await self._evaluate_provider(provider, model=model, saved=saved)
        await self._record_provider_result(turn, result, all_model_costs)

    async def _record_provider_result(
        self,
        turn: str,
        result: ProviderEvaluationResult,
        all_model_costs: dict[str, dict[str, float]],
    ) -> None:
        payload = {
            "type": "provider_eval",
            "session_id": self._session_id,
            "run_id": self._run_id,
            "turn": turn,
            "speaker": "user",
            "provider": result.provider,
            "model": result.model,
            "pricing_model": pricing_model_name(provider=result.provider, model=result.model),
            "request_id": result.request_id,
            "duration_sec": result.duration_sec,
            "latency_ms": result.latency_ms,
            "cost_usd": result.cost_usd,
            "cost_source": result.cost_source,
            "transcript": result.transcript,
            "status": result.status,
            "error": result.error,
            "status_code": result.status_code,
            "response_text": result.response_text,
            "all_model_costs_usd": all_model_costs,
        }
        self._provider_results_by_name.setdefault(result.provider, []).append(result)
        await self._store.append_metrics(self._session_id, payload)
        await self._record_trace("evaluation.stt.provider_result", payload)

    def _provider_session_metrics(self) -> dict[str, dict[str, object]]:
        metrics: dict[str, dict[str, object]] = {}
        for provider, results in self._provider_results_by_name.items():
            latencies = [result.latency_ms for result in results if result.latency_ms > 0]
            success_count = sum(1 for result in results if result.status == "ok")
            error_count = sum(1 for result in results if result.status != "ok")
            metrics[provider] = {
                "call_count": len(results),
                "success_count": success_count,
                "error_count": error_count,
                "latency_avg_ms": _avg(latencies),
                "latency_median_ms": _median(latencies),
                "latency_p95_ms": _p95(latencies),
            }
        return metrics

    async def _evaluate_provider(
        self, provider: str, *, model: str, saved: SavedTurnAudio
    ) -> ProviderEvaluationResult:
        try:
            if provider == "deepgram":
                return await self._evaluate_deepgram(model=model, saved=saved)
            if provider == "elevenlabs":
                return await self._evaluate_elevenlabs(model=model, saved=saved)
            if provider == "sarvam":
                return await self._evaluate_sarvam(model=model, saved=saved)
            raise RuntimeError(f"Unsupported STT evaluation provider: {provider}")
        except httpx.HTTPStatusError as exc:
            latency_ms = getattr(exc, "_stt_eval_latency_ms", 0.0)
            response_text = _truncate_text(exc.response.text)
            logger.warning(
                "stt evaluation failed session_id=%s turn=%s provider=%s status=%s latency_ms=%s body=%s",
                self._session_id,
                saved.turn,
                provider,
                exc.response.status_code,
                latency_ms,
                response_text,
            )
            return ProviderEvaluationResult(
                provider=provider,
                model=model,
                request_id=None,
                duration_sec=saved.duration_sec,
                latency_ms=latency_ms,
                cost_usd=compute_model_cost(saved.duration_sec, provider=provider, model=model),
                cost_source="computed",
                transcript=None,
                status="error",
                error=str(exc),
                status_code=exc.response.status_code,
                response_text=response_text,
            )
        except Exception as exc:
            latency_ms = getattr(exc, "_stt_eval_latency_ms", 0.0)
            response_text = _truncate_text(getattr(exc, "response_text", None))
            logger.warning(
                "stt evaluation failed session_id=%s turn=%s provider=%s latency_ms=%s: %s",
                self._session_id,
                saved.turn,
                provider,
                latency_ms,
                exc,
            )
            return ProviderEvaluationResult(
                provider=provider,
                model=model,
                request_id=None,
                duration_sec=saved.duration_sec,
                latency_ms=latency_ms,
                cost_usd=compute_model_cost(saved.duration_sec, provider=provider, model=model),
                cost_source="computed",
                transcript=None,
                status="error",
                error=str(exc),
                response_text=response_text,
            )

    async def _evaluate_deepgram(
        self, *, model: str, saved: SavedTurnAudio
    ) -> ProviderEvaluationResult:
        api_key = self._settings.deepgram_api_key or self._settings.stt_api_key
        if not api_key:
            raise RuntimeError("Deepgram STT evaluation requires DEEPGRAM_API_KEY or STT_API_KEY")

        audio_bytes = await asyncio.to_thread(Path(saved.file_path).read_bytes)
        start = time.monotonic()
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://api.deepgram.com/v1/listen",
                params={
                    "model": model,
                    "smart_format": "true",
                    "punctuate": "true",
                },
                headers={
                    "Authorization": f"Token {api_key}",
                    "Content-Type": "audio/wav",
                },
                content=audio_bytes,
            )
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                exc._stt_eval_latency_ms = round((time.monotonic() - start) * 1000.0, 1)
                raise
            body = response.json()
        latency_ms = round((time.monotonic() - start) * 1000.0, 1)
        transcript = (
            (((body.get("results") or {}).get("channels") or [{}])[0].get("alternatives") or [{}])[0]
            .get("transcript")
        )
        request_id = ((body.get("metadata") or {}).get("request_id")) or response.headers.get(
            "dg-request-id"
        )
        return ProviderEvaluationResult(
            provider="deepgram",
            model=model,
            request_id=request_id,
            duration_sec=saved.duration_sec,
            latency_ms=latency_ms,
            cost_usd=compute_model_cost(saved.duration_sec, provider="deepgram", model=model),
            cost_source="computed",
            transcript=transcript,
            status="ok",
        )

    async def _evaluate_elevenlabs(
        self, *, model: str, saved: SavedTurnAudio
    ) -> ProviderEvaluationResult:
        api_key = self._settings.elevenlabs_api_key
        if not api_key:
            raise RuntimeError("ElevenLabs STT evaluation requires ELEVENLABS_API_KEY")

        start = time.monotonic()
        async with httpx.AsyncClient(timeout=30.0) as client:
            with Path(saved.file_path).open("rb") as audio_file:
                response = await client.post(
                    "https://api.elevenlabs.io/v1/speech-to-text",
                    headers={"xi-api-key": api_key},
                    data={"model_id": model},
                    files={"file": ("audio.wav", audio_file, "audio/wav")},
                )
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                exc._stt_eval_latency_ms = round((time.monotonic() - start) * 1000.0, 1)
                raise
            body = response.json()
        latency_ms = round((time.monotonic() - start) * 1000.0, 1)
        request_id = (
            response.headers.get("request-id")
            or response.headers.get("x-request-id")
            or response.headers.get("xi-request-id")
        )
        transcript = body.get("text") or body.get("transcript")
        return ProviderEvaluationResult(
            provider="elevenlabs",
            model=model,
            request_id=request_id,
            duration_sec=saved.duration_sec,
            latency_ms=latency_ms,
            cost_usd=compute_model_cost(saved.duration_sec, provider="elevenlabs", model=model),
            cost_source="computed",
            transcript=transcript,
            status="ok",
        )

    async def _evaluate_sarvam(
        self, *, model: str, saved: SavedTurnAudio
    ) -> ProviderEvaluationResult:
        api_key = self._settings.sarvam_api_key
        if not api_key:
            raise RuntimeError("Sarvam STT evaluation requires SARVAM_API_KEY")

        start = time.monotonic()
        async with httpx.AsyncClient(timeout=30.0) as client:
            with Path(saved.file_path).open("rb") as audio_file:
                response = await client.post(
                    self._settings.stt_evaluation_sarvam_url,
                    headers={"api-subscription-key": api_key},
                    data={"model": model},
                    files={"file": ("audio.wav", audio_file, "audio/wav")},
                )
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                exc._stt_eval_latency_ms = round((time.monotonic() - start) * 1000.0, 1)
                raise
            body = response.json()
        latency_ms = round((time.monotonic() - start) * 1000.0, 1)
        request_id = body.get("request_id")
        transcript = (
            body.get("transcript")
            or body.get("text")
            or ((body.get("data") or {}).get("transcript"))
        )
        return ProviderEvaluationResult(
            provider="sarvam",
            model=model,
            request_id=request_id,
            duration_sec=saved.duration_sec,
            latency_ms=latency_ms,
            cost_usd=compute_model_cost(saved.duration_sec, provider="sarvam", model=model),
            cost_source="computed",
            transcript=transcript,
            status="ok",
        )


def _truncate_text(value: Any, limit: int = 1000) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if len(text) <= limit:
        return text
    return f"{text[:limit]}..."


def _median(values: list[float]) -> float:
    if not values:
        return 0.0
    return round(float(statistics.median(values)), 1)


def _avg(values: list[float]) -> float:
    if not values:
        return 0.0
    return round(sum(values) / len(values), 1)


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int(round(0.95 * (len(ordered) - 1)))))
    return round(ordered[index], 1)
