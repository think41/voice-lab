from collections.abc import Awaitable, Callable
from typing import Any

TraceRecorder = Callable[[str, dict[str, Any]], Awaitable[None]]
EventSender = Callable[[dict[str, Any]], Awaitable[None]]
PROVIDER_REQUEST_EVENT = {"stt": "stt.provider_request", "tts": "tts.provider_request"}


class ProviderRequestTraceMixin:
    def __init__(
        self,
        *,
        record_trace: TraceRecorder,
        component: str,
        provider: str,
        transport: str,
        provider_model: str,
        run_tag: str | None = None,
        voice: str | None = None,
    ) -> None:
        self._record_trace = record_trace
        self._provider_request_component = component
        self._provider_name = provider
        self._provider_transport = transport
        self._provider_model = provider_model
        self._provider_run_tag = run_tag
        self._provider_voice = voice
        self._provider_request_recorded = False

    async def _record_provider_request(self, provider_request_id: str | None) -> None:
        if self._provider_request_recorded or not provider_request_id:
            return
        self._provider_request_recorded = True
        payload: dict[str, Any] = {
            "provider": self._provider_name,
            "provider_request_id": provider_request_id,
            "provider_object_type": "request",
            "transport": self._provider_transport,
            "model": self._provider_model,
        }
        if self._provider_run_tag:
            payload["run_tag"] = self._provider_run_tag
        if self._provider_voice:
            payload["voice"] = self._provider_voice
        await self._record_trace(PROVIDER_REQUEST_EVENT[self._provider_request_component], payload)

    async def _record_provider_request_from_headers(
        self, headers: Any, *candidates: str
    ) -> None:
        if headers is None:
            return
        header_map = {str(key).lower(): value for key, value in headers.items()}
        for candidate in candidates:
            provider_request_id = header_map.get(candidate.lower())
            if provider_request_id:
                await self._record_provider_request(str(provider_request_id))
                return

    async def _record_provider_request_from_mapping(
        self, payload: dict[str, Any] | None, *candidates: str
    ) -> None:
        if payload is None:
            return
        for candidate in candidates:
            provider_request_id = payload.get(candidate)
            if isinstance(provider_request_id, str) and provider_request_id.strip():
                await self._record_provider_request(provider_request_id)
                return
