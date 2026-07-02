import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any
from uuid import uuid4

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
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.serializers.base_serializer import FrameSerializer
from pipecat.services.deepgram.stt import DeepgramSTTService
from pipecat.services.deepgram.tts import DeepgramTTSService
from pipecat.transports.websocket.fastapi import FastAPIWebsocketParams, FastAPIWebsocketTransport
from pipecat_adk import AdkLLMService, SessionParams, VqlTTSMixin
from pipecat_adk.frames import (
    VqlLLMFullResponseEndFrame,
    VqlLLMFullResponseStartFrame,
    VqlLLMTextFrame,
)

from app.core.config import get_settings
from app.schemas.agent import AgentConfig
from app.services.adk_session_service import create_adk_session_service, ensure_adk_session
from app.services.pipecat_adk_runtime import PipecatAdkRuntime
from app.services.pipeline_metrics import (
    AudioInputCounter,
    MetricsSink,
    SttUsageAccumulator,
)

logger = logging.getLogger("uvicorn.error")
TraceRecorder = Callable[[str, dict[str, Any]], Awaitable[None]]
EventSender = Callable[[dict[str, Any]], Awaitable[None]]


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


class AdkDeepgramTTSService(VqlTTSMixin, DeepgramTTSService):
    pass


class UserTranscriptBridge(FrameProcessor):
    def __init__(self, record_trace: TraceRecorder, send_event: EventSender) -> None:
        super().__init__()
        self._record_trace = record_trace
        self._send_event = send_event
        self._stt_request_id_captured = False

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)

        is_transcript = isinstance(frame, (TranscriptionFrame, InterimTranscriptionFrame))
        if is_transcript and not self._stt_request_id_captured:
            request_id = _extract_deepgram_request_id(getattr(frame, "result", None))
            if request_id:
                self._stt_request_id_captured = True
                await self._record_trace(
                    "provider.request_id",
                    {"provider": "deepgram", "kind": "stt", "request_id": request_id},
                )

        if isinstance(frame, InterimTranscriptionFrame) and frame.text.strip():
            await self._send_event({"type": "transcript.partial", "text": frame.text})
        elif isinstance(frame, TranscriptionFrame) and frame.text.strip():
            await self._record_trace("transcript.final", {"role": "user", "text": frame.text})
            await self._send_event({"type": "transcript.final", "text": frame.text})
            await self._send_event({"type": "agent.thinking"})

        await self.push_frame(frame, direction)


def _extract_deepgram_ws_request_id(tts_service: Any) -> str | None:
    """Read `dg-request-id` from the Deepgram TTS websocket handshake response."""
    ws = getattr(tts_service, "_websocket", None)
    if ws is None:
        return None
    response = getattr(ws, "response", None)
    headers = getattr(response, "headers", None) if response is not None else None
    if headers is None:
        return None
    try:
        return headers.get("dg-request-id") or headers.get("Dg-Request-Id")
    except AttributeError:
        return None


def _extract_deepgram_request_id(result: Any) -> str | None:
    if result is None:
        return None
    metadata = getattr(result, "metadata", None)
    if metadata is None and isinstance(result, dict):
        metadata = result.get("metadata")
    if metadata is None:
        return None
    request_id = getattr(metadata, "request_id", None)
    if request_id is None and isinstance(metadata, dict):
        request_id = metadata.get("request_id")
    return str(request_id) if request_id else None


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
        if not settings.stt_api_key:
            raise RuntimeError("STT_API_KEY is required for streaming Deepgram STT")
        tts_api_key = settings.stt_api_key or settings.tts_api_key
        if not tts_api_key:
            raise RuntimeError("STT_API_KEY or TTS_API_KEY is required for streaming Deepgram TTS")

        helper = PipecatAdkRuntime()
        app = helper.build_adk_app(config)
        session_service = create_adk_session_service()
        await ensure_adk_session(
            session_service, app_name=app.name, user_id=user_id, session_id=session_id
        )
        voice = helper._deepgram_voice_model(config.tts_voice)

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
        )
        context = llm.create_context_aggregator()
        stt = DeepgramSTTService(
            api_key=settings.stt_api_key,
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
        async def normalize_tts_text(text: str, _aggregation_type: Any) -> str:
            return helper._normalize_for_speech(text)

        tts = AdkDeepgramTTSService(
            api_key=tts_api_key,
            voice=voice,
            sample_rate=24000,
            encoding="linear16",
            text_transforms=[("*", normalize_tts_text)],
        )

        @tts.event_handler("on_connected")
        async def _capture_tts_request_id(_service) -> None:
            request_id = _extract_deepgram_ws_request_id(tts)
            if request_id:
                await record_trace(
                    "provider.request_id",
                    {"provider": "deepgram", "kind": "tts", "request_id": request_id},
                )

        async def send_event(payload: dict[str, Any]) -> None:
            await websocket.send_json(payload)

        user_trace_bridge = UserTranscriptBridge(record_trace, send_event)
        assistant_trace_bridge = AssistantTraceBridge(record_trace, send_event, helper)
        playback_bridge = PlaybackTraceBridge(record_trace, send_event)
        stt_accumulator = SttUsageAccumulator()
        audio_input_counter = AudioInputCounter(stt_accumulator)
        metrics_sink = MetricsSink(
            record_trace=record_trace,
            stt_accumulator=stt_accumulator,
            llm_model=config.model,
            stt_provider=config.stt_provider,
            stt_model=config.stt_model,
            stt_sample_rate=sample_rate,
            tts_provider=config.tts_provider,
            tts_model=voice,
        )
        pipeline = Pipeline(
            [
                transport.input(),
                audio_input_counter,
                stt,
                user_trace_bridge,
                context.user(),
                llm,
                assistant_trace_bridge,
                tts,
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
                enable_usage_metrics=True,
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

        await runner.run(task)
        logger.info("pipecat streaming test-call ended run_id=%s", run_id)

