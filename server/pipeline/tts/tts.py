from typing import Any

from pipecat.services.deepgram.tts import DeepgramTTSService
from pipecat.services.elevenlabs.tts import ElevenLabsTTSService
from pipecat_adk import VqlTTSMixin

from pipeline.utils.tracing import ProviderRequestTraceMixin, TraceRecorder


class AdkDeepgramTTSService(ProviderRequestTraceMixin, VqlTTSMixin, DeepgramTTSService):
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


class AdkElevenLabsTTSService(ProviderRequestTraceMixin, VqlTTSMixin, ElevenLabsTTSService):
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
