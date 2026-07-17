from typing import Any

from deepgram.listen.v1.types import ListenV1Metadata, ListenV1Results
from pipecat.services.deepgram.stt import DeepgramSTTService
from pipecat.services.elevenlabs.stt import ElevenLabsRealtimeSTTService

from pipeline.utils.tracing import ProviderRequestTraceMixin, TraceRecorder


class InstrumentedDeepgramSTTService(ProviderRequestTraceMixin, DeepgramSTTService):
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
        elif isinstance(message, ListenV1Results):
            metadata = getattr(message, "metadata", None)
            await self._record_provider_request(getattr(metadata, "request_id", None))
        await super()._on_message(message)


class InstrumentedElevenLabsSTTService(ProviderRequestTraceMixin, ElevenLabsRealtimeSTTService):
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
