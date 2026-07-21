import time
from collections.abc import AsyncGenerator
from typing import Any

from pipecat.frames.frames import Frame
from pipecat.services.deepgram.tts import DeepgramTTSService
from pipecat.services.elevenlabs.tts import ElevenLabsTTSService
from pipecat_adk import VqlTTSMixin

from pipeline.utils.tracing import ProviderRequestTraceMixin, TraceRecorder


class TtsUsageMeterMixin:
    """Meter characters actually sent to the TTS provider.

    `run_tts` receives the final prepared text (post text-transforms) and
    immediately sends it to the provider (`Speak` message for Deepgram,
    context text for ElevenLabs). Providers bill on characters sent —
    including text later cleared/closed by an interruption — so this counts
    the billed quantity. Transcript-derived counts undercount whenever the
    user interrupts, and Pipecat's built-in `TTSUsageMetricsData` metric is
    never emitted by the Deepgram websocket service and is dropped on
    interruption, so we count at the send seam ourselves (same approach as
    `SttUsageMeterMixin`).

    Also tracks per-invocation TTS latency: text handed to provider → first
    audio frame observed downstream. `TtsLatencyBridge` drives the stop hook.
    """

    _sent_characters: int = 0
    _pending_run_tts_start_time: float | None = None

    async def run_tts(self, text: str, context_id: str) -> AsyncGenerator[Frame | None, None]:
        self._sent_characters += len(text)
        if self._pending_run_tts_start_time is None:
            self._pending_run_tts_start_time = time.perf_counter()
        async for frame in super().run_tts(text, context_id):
            yield frame

    @property
    def sent_characters(self) -> int:
        return self._sent_characters

    def note_first_audio(self) -> float | None:
        start = self._pending_run_tts_start_time
        if start is None:
            return None
        latency_ms = (time.perf_counter() - start) * 1000.0
        self._pending_run_tts_start_time = None
        samples = getattr(self, "_latency_samples_store", None)
        if samples is None:
            samples = []
            self._latency_samples_store = samples
        samples.append(latency_ms)
        return latency_ms

    @property
    def latency_samples(self) -> list[float]:
        return list(getattr(self, "_latency_samples_store", []) or [])


class AdkDeepgramTTSService(
    TtsUsageMeterMixin, ProviderRequestTraceMixin, VqlTTSMixin, DeepgramTTSService
):
    def __init__(
        self,
        *,
        record_trace: TraceRecorder,
        provider_model: str,
        provider_voice: str,
        run_tag: str,
        **kwargs: Any,
    ) -> None:
        ProviderRequestTraceMixin.__init__(
            self,
            record_trace=record_trace,
            component="tts",
            provider="deepgram",
            transport="websocket",
            provider_model=provider_model,
            run_tag=run_tag,
            voice=provider_voice,
        )
        DeepgramTTSService.__init__(self, **kwargs)

    async def _connect_websocket(self):
        await super()._connect_websocket()
        websocket = getattr(self, "_websocket", None)
        response_headers = websocket.response.headers if websocket and websocket.response else {}
        await self._record_provider_request_from_headers(response_headers, "dg-request-id")


class AdkElevenLabsTTSService(
    TtsUsageMeterMixin, ProviderRequestTraceMixin, VqlTTSMixin, ElevenLabsTTSService
):
    def __init__(
        self,
        *,
        record_trace: TraceRecorder,
        provider_model: str,
        provider_voice: str,
        run_tag: str,
        **kwargs: Any,
    ) -> None:
        ProviderRequestTraceMixin.__init__(
            self,
            record_trace=record_trace,
            component="tts",
            provider="elevenlabs",
            transport="websocket",
            provider_model=provider_model,
            run_tag=run_tag,
            voice=provider_voice,
        )
        ElevenLabsTTSService.__init__(self, **kwargs)

    async def _connect_websocket(self):
        await super()._connect_websocket()
        websocket = getattr(self, "_websocket", None)
        response_headers = websocket.response.headers if websocket and websocket.response else {}
        await self._record_provider_request_from_headers(
            response_headers,
            "x-request-id",
            "request-id",
            "xi-request-id",
        )
