import time
from collections.abc import AsyncGenerator
from typing import Any

from deepgram.listen.v1.types import ListenV1Metadata, ListenV1Results
from pipecat.frames.frames import Frame
from pipecat.services.deepgram.stt import DeepgramSTTService
from pipecat.services.elevenlabs.stt import ElevenLabsRealtimeSTTService

from pipeline.utils.tracing import ProviderRequestTraceMixin, TraceRecorder


class SttUsageMeterMixin:
    """Meter raw audio bytes actually sent to the STT provider.

    `STTService.process_audio_frame` applies the mute/reconnect/empty-frame
    guards and only then calls `run_stt`, so every byte counted here is audio
    the provider bills for (silence included). VAD turn audio undercounts.

    Also tracks per-turn STT latency: user starts speaking → first final
    transcript. `UserTranscriptBridge` drives the start/stop hooks.
    """

    _streamed_audio_bytes: int = 0
    _provider_reported_audio_seconds: float = 0.0
    _utterance_start_time: float | None = None

    async def run_stt(self, audio: bytes) -> AsyncGenerator[Frame | None, None]:
        self._streamed_audio_bytes += len(audio)
        async for frame in super().run_stt(audio):
            yield frame

    @property
    def streamed_audio_seconds(self) -> float:
        if not self.sample_rate:
            return 0.0
        # 16-bit mono PCM: 2 bytes per sample.
        return self._streamed_audio_bytes / (self.sample_rate * 2)

    @property
    def provider_reported_audio_seconds(self) -> float | None:
        return self._provider_reported_audio_seconds or None

    def note_utterance_start(self) -> None:
        if self._utterance_start_time is None:
            self._utterance_start_time = time.perf_counter()

    def note_transcript_final(self) -> float | None:
        start = self._utterance_start_time
        if start is None:
            return None
        latency_ms = (time.perf_counter() - start) * 1000.0
        self._utterance_start_time = None
        samples = getattr(self, "_latency_samples_store", None)
        if samples is None:
            samples = []
            self._latency_samples_store = samples
        samples.append(latency_ms)
        return latency_ms

    @property
    def latency_samples(self) -> list[float]:
        return list(getattr(self, "_latency_samples_store", []) or [])


class InstrumentedDeepgramSTTService(
    SttUsageMeterMixin, ProviderRequestTraceMixin, DeepgramSTTService
):
    def __init__(
        self, *, record_trace: TraceRecorder, provider_model: str, run_tag: str, **kwargs: Any
    ) -> None:
        ProviderRequestTraceMixin.__init__(
            self,
            record_trace=record_trace,
            component="stt",
            provider="deepgram",
            transport="websocket",
            provider_model=provider_model,
            run_tag=run_tag,
        )
        DeepgramSTTService.__init__(self, **kwargs)

    async def _on_message(self, message: Any) -> None:
        if isinstance(message, ListenV1Metadata):
            await self._record_provider_request(message.request_id)
            # Deepgram reports processed audio duration per connection on
            # close; accumulate across reconnects for meter calibration.
            duration = getattr(message, "duration", None)
            if duration:
                self._provider_reported_audio_seconds += float(duration)
        elif isinstance(message, ListenV1Results):
            metadata = getattr(message, "metadata", None)
            await self._record_provider_request(getattr(metadata, "request_id", None))
        await super()._on_message(message)


class InstrumentedElevenLabsSTTService(
    SttUsageMeterMixin, ProviderRequestTraceMixin, ElevenLabsRealtimeSTTService
):
    def __init__(
        self, *, record_trace: TraceRecorder, provider_model: str, run_tag: str, **kwargs: Any
    ) -> None:
        ProviderRequestTraceMixin.__init__(
            self,
            record_trace=record_trace,
            component="stt",
            provider="elevenlabs",
            transport="websocket",
            provider_model=provider_model,
            run_tag=run_tag,
        )
        ElevenLabsRealtimeSTTService.__init__(self, **kwargs)

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

    async def _process_response(self, data: dict):
        await self._record_provider_request_from_mapping(data, "request_id", "transcript_id")
        await super()._process_response(data)
