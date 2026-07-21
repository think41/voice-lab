import logging
from typing import Any
from uuid import uuid4

from fastapi import WebSocket
from pipecat.pipeline.runner import PipelineRunner
from pipecat.processors.audio.audio_buffer_processor import AudioBufferProcessor
from pipecat.services.settings import LLMSettings
from pipecat.transports.websocket.fastapi import (
    FastAPIWebsocketParams,
    FastAPIWebsocketTransport,
)
from pipecat_adk import AdkLLMService, SessionParams
from pipecat_adk.frames import (
    VqlLLMFullResponseEndFrame,
    VqlLLMFullResponseStartFrame,
    VqlLLMTextFrame,
)

from app.agents.schemas import AgentConfig
from app.config import get_settings
from pipeline.custom_processors.bridges import (
    AssistantTraceBridge,
    PlaybackTraceBridge,
    TtsLatencyBridge,
    UserTranscriptBridge,
)
from pipeline.custom_processors.metrics.pricing import compute_cost
from pipeline.custom_processors.metrics.sink import MetricsSink
from pipeline.llm.adk_runtime import PipecatAdkRuntime, require_llm_api_key
from pipeline.llm.adk_session_service import create_adk_session_service, ensure_adk_session
from pipeline.pipeline import build_pipeline_task, build_stt_service, build_tts_service
from pipeline.stt.stt_evaluation_service import SttEvaluationSession
from pipeline.utils.serializers import RawPcmWebsocketSerializer
from pipeline.utils.tracing import TraceRecorder

logger = logging.getLogger("uvicorn.error")


def _summarize_latency(
    *, provider: str, model: str, samples: list[float]
) -> dict[str, Any] | None:
    if not samples:
        return None
    ordered = sorted(samples)
    n = len(ordered)
    median_ms = ordered[n // 2] if n % 2 == 1 else (ordered[n // 2 - 1] + ordered[n // 2]) / 2.0
    # Nearest-rank p95: index = ceil(0.95 * n) - 1, clamped to valid range.
    p95_index = max(0, min(n - 1, -(-95 * n // 100) - 1))
    p95_ms = ordered[p95_index]
    return {
        "provider": provider,
        "model": model,
        "count": n,
        "median_ms": round(median_ms, 1),
        "p95_ms": round(p95_ms, 1),
    }


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
        require_llm_api_key(config)

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
        stt = build_stt_service(
            settings=settings,
            config=config,
            sample_rate=sample_rate,
            record_trace=record_trace,
            run_id=run_id,
        )

        async def normalize_tts_text(text: str, _aggregation_type: Any) -> str:
            return helper._normalize_for_speech(text)

        tts, metrics_tts_model = build_tts_service(
            settings=settings,
            config=config,
            helper=helper,
            record_trace=record_trace,
            run_id=run_id,
            normalize_tts_text=normalize_tts_text,
        )

        async def send_event(payload: dict[str, Any]) -> None:
            await websocket.send_json(payload)

        user_trace_bridge = UserTranscriptBridge(
            record_trace,
            send_event,
            stt_service=stt,
            stt_provider=config.stt_provider,
            stt_model=config.stt_model,
        )
        assistant_trace_bridge = AssistantTraceBridge(record_trace, send_event, helper)
        playback_bridge = PlaybackTraceBridge(record_trace, send_event)
        tts_latency_bridge = TtsLatencyBridge(
            record_trace,
            tts_service=tts,
            tts_provider=config.tts_provider,
            tts_model=metrics_tts_model,
        )
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
        task = build_pipeline_task(
            transport=transport,
            stt=stt,
            tts=tts,
            llm=llm,
            context=context,
            user_trace_bridge=user_trace_bridge,
            assistant_trace_bridge=assistant_trace_bridge,
            playback_bridge=playback_bridge,
            tts_latency_bridge=tts_latency_bridge,
            audio_buffer=audio_buffer,
            metrics_sink=metrics_sink,
            sample_rate=sample_rate,
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
                "tts_model": metrics_tts_model,
                "llm_model": config.model,
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
                await stt_evaluation.finalize(
                    tts_sent_characters=tts.sent_characters,
                    stt_latency=_summarize_latency(
                        provider=config.stt_provider,
                        model=config.stt_model,
                        samples=stt.latency_samples,
                    ),
                    tts_latency=_summarize_latency(
                        provider=config.tts_provider,
                        model=metrics_tts_model,
                        samples=tts.latency_samples,
                    ),
                )
        logger.info("pipecat streaming test-call ended run_id=%s", run_id)
