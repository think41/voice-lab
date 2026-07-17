import json
import logging
from collections.abc import AsyncGenerator, Awaitable, Callable
from typing import Any
from uuid import uuid4

from deepgram.listen.v1.types import ListenV1Metadata, ListenV1Results
from fastapi import WebSocket
from pipecat.frames.frames import (
    BotStartedSpeakingFrame,
    BotStoppedSpeakingFrame,
    CancelFrame,
    EndFrame,
    Frame,
    InputAudioRawFrame,
    InterimTranscriptionFrame,
    OutputAudioRawFrame,
    OutputTransportMessageFrame,
    TranscriptionFrame,
)
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.audio.audio_buffer_processor import AudioBufferProcessor
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.serializers.base_serializer import FrameSerializer
from pipecat.services.deepgram.stt import DeepgramSTTService
from pipecat.services.deepgram.tts import DeepgramTTSService
from pipecat.services.elevenlabs.stt import CommitStrategy, ElevenLabsRealtimeSTTService
from pipecat.services.elevenlabs.tts import ElevenLabsTTSService
from pipecat.services.settings import LLMSettings
from pipecat.transports.websocket.fastapi import FastAPIWebsocketParams, FastAPIWebsocketTransport
from pipecat_adk import AdkLLMService, SessionParams, VqlTTSMixin
from pipecat_adk.frames import (
    VqlLLMFullResponseEndFrame,
    VqlLLMFullResponseStartFrame,
    VqlLLMTextFrame,
)

from app.core.config import get_settings
from app.schemas.agent import DEFAULT_TTS_MODEL_BY_PROVIDER, AgentConfig
from app.services.adk_session_service import create_adk_session_service, ensure_adk_session
from app.services.pipecat_adk_runtime import PipecatAdkRuntime
from app.services.pipeline_metrics import (
    MetricsSink,
)
from app.services.pricing import compute_cost
from app.services.stt_evaluation_service import SttEvaluationSession

logger = logging.getLogger("uvicorn.error")
TraceRecorder = Callable[[str, dict[str, Any]], Awaitable[None]]
EventSender = Callable[[dict[str, Any]], Awaitable[None]]
_PROVIDER_REQUEST_EVENT = {"stt": "stt.provider_request", "tts": "tts.provider_request"}


class RawPcmWebsocketSerializer(FrameSerializer):
    def __init__(self, *, sample_rate: int) -> None:
        super().__init__()
        self.sample_rate = sample_rate

    async def serialize(self, frame: Frame) -> str | bytes | None:
        if isinstance(frame, OutputAudioRawFrame):
            return frame.audio
        if isinstance(frame, OutputTransportMessageFrame):
            return json.dumps(frame.message)
        if isinstance(frame, (EndFrame, CancelFrame)):
            return json.dumps({"type": "session.closed"})
        return None

    async def deserialize(self, data: str | bytes) -> Frame | None:
        if isinstance(data, bytes):
            return InputAudioRawFrame(audio=data, sample_rate=self.sample_rate, num_channels=1)
        try:
            message = json.loads(data)
        except json.JSONDecodeError:
            return None
        if message.get("type") == "stop":
            return EndFrame(reason="client stop")
        return None


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
        await self._record_trace(_PROVIDER_REQUEST_EVENT[self._provider_request_component], payload)

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


class SttUsageMeterMixin:
    """Meter raw audio bytes actually sent to the STT provider.

    `STTService.process_audio_frame` applies the mute/reconnect/empty-frame
    guards and only then calls `run_stt`, so every byte counted here is audio
    the provider bills for (silence included). VAD turn audio undercounts.
    """

    _streamed_audio_bytes: int = 0
    _provider_reported_audio_seconds: float = 0.0

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
    """

    _sent_characters: int = 0

    async def run_tts(self, text: str, context_id: str) -> AsyncGenerator[Frame | None, None]:
        self._sent_characters += len(text)
        async for frame in super().run_tts(text, context_id):
            yield frame

    @property
    def sent_characters(self) -> int:
        return self._sent_characters


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


class UserTranscriptBridge(FrameProcessor):
    def __init__(self, record_trace: TraceRecorder, send_event: EventSender) -> None:
        super().__init__()
        self._record_trace = record_trace
        self._send_event = send_event

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)

        if isinstance(frame, InterimTranscriptionFrame) and frame.text.strip():
            await self._send_event({"type": "transcript.partial", "text": frame.text})
        elif isinstance(frame, TranscriptionFrame) and frame.text.strip():
            await self._record_trace("transcript.final", {"role": "user", "text": frame.text})
            await self._send_event({"type": "transcript.final", "text": frame.text})
            await self._send_event({"type": "agent.thinking"})

        await self.push_frame(frame, direction)


class AssistantTraceBridge(FrameProcessor):
    def __init__(
        self,
        record_trace: TraceRecorder,
        send_event: EventSender,
        helper: PipecatAdkRuntime,
    ) -> None:
        super().__init__()
        self._record_trace = record_trace
        self._send_event = send_event
        self._helper = helper
        self._assistant_text_parts: list[str] = []

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)

        if isinstance(frame, VqlLLMFullResponseStartFrame):
            self._assistant_text_parts = []
        elif isinstance(frame, VqlLLMTextFrame):
            if frame.text:
                self._assistant_text_parts.append(frame.text)
            text = self._helper.clean_model_text(frame.text)
            if text:
                await self._send_event({"type": "agent.text.delta", "text": text})
        elif isinstance(frame, VqlLLMFullResponseEndFrame):
            text = self._helper.clean_model_text("".join(self._assistant_text_parts))
            if text:
                await self._record_trace("agent.text", {"role": "assistant", "text": text})
            self._assistant_text_parts = []

        await self.push_frame(frame, direction)


class PlaybackTraceBridge(FrameProcessor):
    def __init__(self, record_trace: TraceRecorder, send_event: EventSender) -> None:
        super().__init__()
        self._record_trace = record_trace
        self._send_event = send_event

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)

        if isinstance(frame, BotStartedSpeakingFrame):
            await self._record_trace("audio.output.started", {"role": "assistant"})
            await self._send_event({"type": "audio.output.started"})
        elif isinstance(frame, BotStoppedSpeakingFrame):
            await self._record_trace("audio.output.stopped", {"role": "assistant"})
            await self._send_event({"type": "audio.output.stopped"})

        await self.push_frame(frame, direction)


class PipecatStreamingRuntime:
    def _deepgram_api_key(self, settings) -> str | None:
        return settings.deepgram_api_key or settings.stt_api_key or settings.tts_api_key

    def _elevenlabs_api_key(self, settings) -> str | None:
        return settings.elevenlabs_api_key

    def _build_stt_service(
        self,
        *,
        settings,
        config: AgentConfig,
        sample_rate: int,
        record_trace: TraceRecorder,
        run_id: str,
    ):
        if config.stt_provider == "deepgram":
            api_key = self._deepgram_api_key(settings)
            if not api_key:
                raise RuntimeError("DEEPGRAM_API_KEY is required for Deepgram STT")
            return InstrumentedDeepgramSTTService(
                record_trace=record_trace,
                provider_model=config.stt_model,
                run_tag=run_id,
                api_key=api_key,
                tag=run_id,
                sample_rate=sample_rate,
                settings=DeepgramSTTService.Settings(
                    model=config.stt_model,
                    endpointing=300,
                    interim_results=True,
                    punctuate=True,
                    smart_format=True,
                    utterance_end_ms="1000",
                ),
            )
        if config.stt_provider == "elevenlabs":
            api_key = self._elevenlabs_api_key(settings)
            if not api_key:
                raise RuntimeError("ELEVENLABS_API_KEY is required for ElevenLabs STT")
            return InstrumentedElevenLabsSTTService(
                record_trace=record_trace,
                provider_model=config.stt_model,
                run_tag=run_id,
                api_key=api_key,
                sample_rate=sample_rate,
                model=config.stt_model,
                commit_strategy=CommitStrategy.VAD,
                include_timestamps=False,
                enable_logging=True,
            )
        raise RuntimeError(f"Unsupported STT provider: {config.stt_provider}")

    def _build_tts_service(
        self,
        *,
        settings,
        config: AgentConfig,
        helper: PipecatAdkRuntime,
        record_trace: TraceRecorder,
        run_id: str,
        normalize_tts_text: Callable[[str, Any], Awaitable[str]],
    ):
        if config.tts_provider == "deepgram":
            api_key = self._deepgram_api_key(settings)
            if not api_key:
                raise RuntimeError("DEEPGRAM_API_KEY is required for Deepgram TTS")
            voice = helper._deepgram_voice_model(config.tts_voice)
            return (
                AdkDeepgramTTSService(
                    record_trace=record_trace,
                    provider_model=voice,
                    provider_voice=voice,
                    run_tag=run_id,
                    api_key=api_key,
                    voice=voice,
                    sample_rate=24000,
                    encoding="linear16",
                    text_transforms=[("*", normalize_tts_text)],
                ),
                voice,
            )
        if config.tts_provider == "elevenlabs":
            api_key = self._elevenlabs_api_key(settings)
            if not api_key:
                raise RuntimeError("ELEVENLABS_API_KEY is required for ElevenLabs TTS")
            model = DEFAULT_TTS_MODEL_BY_PROVIDER["elevenlabs"]
            return (
                AdkElevenLabsTTSService(
                    record_trace=record_trace,
                    provider_model=model,
                    provider_voice=config.tts_voice,
                    run_tag=run_id,
                    api_key=api_key,
                    voice_id=config.tts_voice,
                    model=model,
                    sample_rate=24000,
                    enable_logging=True,
                    text_transforms=[("*", normalize_tts_text)],
                ),
                model,
            )
        raise RuntimeError(f"Unsupported TTS provider: {config.tts_provider}")

    async def run_websocket(
        self,
        *,
        websocket: WebSocket,
        config: AgentConfig,
        run_id: str,
        session_id: str,
        record_trace: TraceRecorder,
        user_id: str = "local-user",
        sample_rate: int = 48000,
    ) -> None:
        settings = get_settings()
        if not settings.gemini_api_key:
            raise RuntimeError("GEMINI_API_KEY is required to run a streaming voice test call")

        helper = PipecatAdkRuntime()
        app = helper.build_adk_app(config)
        session_service = create_adk_session_service()
        await ensure_adk_session(
            session_service, app_name=app.name, user_id=user_id, session_id=session_id
        )

        transport = FastAPIWebsocketTransport(
            websocket=websocket,
            params=FastAPIWebsocketParams(
                audio_in_enabled=True,
                audio_in_sample_rate=sample_rate,
                audio_out_enabled=True,
                audio_out_sample_rate=24000,
                serializer=RawPcmWebsocketSerializer(sample_rate=sample_rate),
                session_timeout=None,
            ),
        )
        llm = AdkLLMService(
            app=app,
            session_service=session_service,
            session_params=SessionParams(
                app_name=app.name, user_id=user_id, session_id=session_id
            ),
            settings=LLMSettings(
                model=config.model,
                system_instruction=config.instruction,
                temperature=config.temperature,
                max_tokens=None,
                top_p=None,
                top_k=None,
                frequency_penalty=None,
                presence_penalty=None,
                seed=None,
                filter_incomplete_user_turns=False,
                user_turn_completion_config=None,
            ),
        )
        context = llm.create_context_aggregator()
        stt = self._build_stt_service(
            settings=settings,
            config=config,
            sample_rate=sample_rate,
            record_trace=record_trace,
            run_id=run_id,
        )

        async def normalize_tts_text(text: str, _aggregation_type: Any) -> str:
            return helper._normalize_for_speech(text)

        tts, metrics_tts_model = self._build_tts_service(
            settings=settings,
            config=config,
            helper=helper,
            record_trace=record_trace,
            run_id=run_id,
            normalize_tts_text=normalize_tts_text,
        )

        async def send_event(payload: dict[str, Any]) -> None:
            await websocket.send_json(payload)

        user_trace_bridge = UserTranscriptBridge(record_trace, send_event)
        assistant_trace_bridge = AssistantTraceBridge(record_trace, send_event, helper)
        playback_bridge = PlaybackTraceBridge(record_trace, send_event)
        stt_evaluation = SttEvaluationSession(
            settings=settings,
            session_id=session_id,
            run_id=run_id,
            record_trace=record_trace,
        )
        audio_buffer = AudioBufferProcessor(
            sample_rate=sample_rate,
            num_channels=1,
            enable_turn_audio=True,
        )

        @audio_buffer.event_handler("on_user_turn_audio_data")
        async def on_user_turn_audio_data(
            _processor, audio: bytes, turn_sample_rate: int, num_channels: int
        ) -> None:
            await stt_evaluation.handle_user_turn_audio(
                bytes(audio),
                turn_sample_rate,
                num_channels,
            )

        metrics_sink = MetricsSink(
            record_trace=record_trace,
        )
        pipeline = Pipeline(
            [
                transport.input(),
                stt,
                user_trace_bridge,
                context.user(),
                llm,
                assistant_trace_bridge,
                tts,
                audio_buffer,
                transport.output(),
                playback_bridge,
                context.assistant(),
                metrics_sink,
            ]
        )
        task = PipelineTask(
            pipeline,
            params=PipelineParams(
                audio_in_sample_rate=sample_rate,
                audio_out_sample_rate=24000,
                enable_metrics=True,
                enable_usage_metrics=False,
            ),
        )
        runner = PipelineRunner(handle_sigint=False)

        @transport.event_handler("on_client_disconnected")
        async def on_client_disconnected(_transport, _websocket):
            await task.cancel()

        @transport.event_handler("on_session_timeout")
        async def on_session_timeout(_transport, _websocket):
            await task.cancel()

        await record_trace(
            "session.started",
            {
                "mode": "pipecat_streaming",
                "stt_provider": config.stt_provider,
                "stt_model": config.stt_model,
                "tts_provider": config.tts_provider,
                "tts_voice": config.tts_voice,
            },
        )
        logger.info("pipecat streaming test-call started run_id=%s", run_id)

        if config.first_message:
            turn_id = f"first-message-{uuid4()}"
            invocation_id = f"voice-{uuid4()}"
            await task.queue_frame(
                VqlLLMFullResponseStartFrame(turn_id=turn_id, invocation_id=invocation_id)
            )
            await task.queue_frame(
                VqlLLMTextFrame(
                    text=config.first_message,
                    turn_id=turn_id,
                    invocation_id=invocation_id,
                )
            )
            await task.queue_frame(
                VqlLLMFullResponseEndFrame(turn_id=turn_id, invocation_id=invocation_id)
            )

        await audio_buffer.start_recording()
        try:
            await runner.run(task)
        finally:
            try:
                stt_usage_payload = {
                    "provider": config.stt_provider,
                    "model": config.stt_model,
                    "streamed_seconds": round(stt.streamed_audio_seconds, 3),
                    "speech_seconds": stt_evaluation.session_duration_sec,
                    "provider_reported_seconds": stt.provider_reported_audio_seconds,
                }
                stt_usage_payload["cost_usd"] = float(compute_cost("usage.stt", stt_usage_payload))
                await record_trace(
                    "usage.stt",
                    stt_usage_payload,
                )
                await record_trace(
                    "usage.tts",
                    {
                        "provider": config.tts_provider,
                        "model": metrics_tts_model,
                        "voice": config.tts_voice,
                        "sent_characters": tts.sent_characters,
                    },
                )
            finally:
                await stt_evaluation.finalize(tts_sent_characters=tts.sent_characters)
        logger.info("pipecat streaming test-call ended run_id=%s", run_id)
