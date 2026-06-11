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
    TTSStartedFrame,
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
from pipecat_adk.frames import VqlLLMTextFrame

from app.core.config import get_settings
from app.schemas.agent import AgentConfig
from app.services.adk_session_service import create_adk_session_service
from app.services.pipecat_adk_runtime import PipecatAdkRuntime

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


class StreamingTraceBridge(FrameProcessor):
    def __init__(self, record_trace: TraceRecorder) -> None:
        super().__init__()
        self._record_trace = record_trace
        self._assistant_text_parts: list[str] = []

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)

        if isinstance(frame, InterimTranscriptionFrame):
            await self.push_frame(
                OutputTransportMessageFrame({"type": "transcript.partial", "text": frame.text}),
                direction,
            )
        elif isinstance(frame, TranscriptionFrame):
            await self._record_trace("transcript.final", {"role": "user", "text": frame.text})
            await self.push_frame(
                OutputTransportMessageFrame({"type": "transcript.final", "text": frame.text}),
                direction,
            )
            await self.push_frame(
                OutputTransportMessageFrame({"type": "agent.thinking"}), direction
            )
            self._assistant_text_parts = []
        elif isinstance(frame, VqlLLMTextFrame):
            self._assistant_text_parts.append(frame.text)
            await self.push_frame(
                OutputTransportMessageFrame({"type": "agent.text.delta", "text": frame.text}),
                direction,
            )
        elif isinstance(frame, TTSStartedFrame):
            text = "".join(self._assistant_text_parts).strip()
            if text:
                await self._record_trace("agent.text", {"role": "assistant", "text": text})

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

        await self._ensure_adk_session(session_id=session_id, user_id=user_id)
        helper = PipecatAdkRuntime()
        app = helper.build_adk_app(config)
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
        session_service = create_adk_session_service()
        llm = AdkLLMService(
            app=app,
            session_service=session_service,
            session_params=SessionParams(
                app_name="voicelab", user_id=user_id, session_id=session_id
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
        tts = AdkDeepgramTTSService(
            api_key=tts_api_key,
            voice=voice,
            sample_rate=24000,
            encoding="linear16",
        )
        async def send_event(payload: dict[str, Any]) -> None:
            await websocket.send_json(payload)

        trace_bridge = StreamingTraceBridge(record_trace)
        playback_bridge = PlaybackTraceBridge(record_trace, send_event)
        pipeline = Pipeline(
            [
                transport.input(),
                stt,
                context.user(),
                llm,
                trace_bridge,
                tts,
                transport.output(),
                playback_bridge,
                context.assistant(),
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
            await task.queue_frame(
                VqlLLMTextFrame(
                    text=config.first_message,
                    turn_id=f"first-message-{uuid4()}",
                    invocation_id=f"voice-{uuid4()}",
                )
            )

        await runner.run(task)
        logger.info("pipecat streaming test-call ended run_id=%s", run_id)

    async def _ensure_adk_session(self, *, session_id: str, user_id: str) -> None:
        session_service = create_adk_session_service()
        existing = await session_service.get_session(
            app_name="voicelab", user_id=user_id, session_id=session_id
        )
        if existing is None:
            await session_service.create_session(
                app_name="voicelab", user_id=user_id, session_id=session_id
            )
