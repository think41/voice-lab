from collections.abc import Awaitable, Callable
from typing import Any

from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.audio.audio_buffer_processor import AudioBufferProcessor
from pipecat.processors.frame_processor import FrameProcessor
from pipecat.services.deepgram.stt import DeepgramSTTService
from pipecat.services.elevenlabs.stt import CommitStrategy

from app.agents.schemas import DEFAULT_TTS_MODEL_BY_PROVIDER, AgentConfig
from pipeline.llm.adk_runtime import PipecatAdkRuntime
from pipeline.stt.stt import (
    InstrumentedDeepgramSTTService,
    InstrumentedElevenLabsSTTService,
)
from pipeline.tts.tts import AdkDeepgramTTSService, AdkElevenLabsTTSService
from pipeline.utils.tracing import TraceRecorder


def deepgram_api_key(settings) -> str | None:
    return settings.deepgram_api_key


def elevenlabs_api_key(settings) -> str | None:
    return settings.elevenlabs_api_key


def build_stt_service(
    *,
    settings,
    config: AgentConfig,
    sample_rate: int,
    record_trace: TraceRecorder,
    run_id: str,
):
    if config.stt_provider == "deepgram":
        api_key = deepgram_api_key(settings)
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
        api_key = elevenlabs_api_key(settings)
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


def build_tts_service(
    *,
    settings,
    config: AgentConfig,
    helper: PipecatAdkRuntime,
    record_trace: TraceRecorder,
    run_id: str,
    normalize_tts_text: Callable[[str, Any], Awaitable[str]],
):
    if config.tts_provider == "deepgram":
        api_key = deepgram_api_key(settings)
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
        api_key = elevenlabs_api_key(settings)
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


def build_pipeline_task(
    *,
    transport,
    stt,
    tts,
    llm,
    context,
    user_trace_bridge: FrameProcessor,
    assistant_trace_bridge: FrameProcessor,
    playback_bridge: FrameProcessor,
    tts_latency_bridge: FrameProcessor,
    audio_buffer: AudioBufferProcessor,
    metrics_sink: FrameProcessor,
    sample_rate: int,
) -> PipelineTask:
    pipeline = Pipeline(
        [
            transport.input(),
            stt,
            user_trace_bridge,
            context.user(),
            llm,
            assistant_trace_bridge,
            tts,
            tts_latency_bridge,
            audio_buffer,
            transport.output(),
            playback_bridge,
            context.assistant(),
            metrics_sink,
        ]
    )
    return PipelineTask(
        pipeline,
        params=PipelineParams(
            audio_in_sample_rate=sample_rate,
            audio_out_sample_rate=24000,
            enable_metrics=True,
            enable_usage_metrics=True,
        ),
    )
