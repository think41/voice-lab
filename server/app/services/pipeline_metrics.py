"""Sinks that turn Pipecat MetricsFrame + input audio bytes into trace_events.

Provider-agnostic: every LLM/TTS service in Pipecat that supports metrics
emits `LLMUsageMetricsData` / `TTSUsageMetricsData` through `MetricsFrame`.
STT services don't emit usage frames, so we account for audio seconds by
summing `InputAudioRawFrame` bytes fed into the pipeline.

Two processors coordinate through a shared `SttUsageAccumulator`.

TODO(Phase 1 eval): `usage.stt` remains the legacy run-summary source while the
turn-based `metrics.jsonl` path is being verified. Remove this STT byte-counter
path only after the new evaluation workflow has been cross-checked on real runs.

Two processors coordinate through a shared `SttUsageAccumulator`:
  - `AudioInputCounter` sits between transport.input and STT, counting bytes.
  - `MetricsSink` sits at the tail, consuming MetricsFrames and flushing the
    accumulated STT audio duration on EndFrame/CancelFrame.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from pipecat.frames.frames import (
    CancelFrame,
    EndFrame,
    Frame,
    InputAudioRawFrame,
    MetricsFrame,
)
from pipecat.metrics.metrics import (
    LLMUsageMetricsData,
    TTFBMetricsData,
    TTSUsageMetricsData,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

TraceRecorder = Callable[[str, dict[str, Any]], Awaitable[None]]

_BYTES_PER_SAMPLE = 2  # 16-bit PCM


@dataclass
class SttUsageAccumulator:
    """Shared state between AudioInputCounter (head) and MetricsSink (tail)."""

    bytes_seen: int = 0
    flushed: bool = False


class AudioInputCounter(FrameProcessor):
    """Passive counter of InputAudioRawFrame bytes going downstream to STT."""

    def __init__(self, accumulator: SttUsageAccumulator) -> None:
        super().__init__()
        self._accumulator = accumulator

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        if isinstance(frame, InputAudioRawFrame):
            self._accumulator.bytes_seen += len(frame.audio)
        await self.push_frame(frame, direction)


class MetricsSink(FrameProcessor):
    """Tail sink: consume MetricsFrame, flush STT accumulator on session end."""

    def __init__(
        self,
        *,
        record_trace: TraceRecorder,
        stt_accumulator: SttUsageAccumulator,
        llm_model: str,
        stt_provider: str,
        stt_model: str,
        stt_sample_rate: int,
        tts_provider: str,
        tts_model: str,
    ) -> None:
        super().__init__()
        self._record_trace = record_trace
        self._stt_accumulator = stt_accumulator
        self._llm_model = llm_model
        self._stt_provider = stt_provider
        self._stt_model = stt_model
        self._stt_sample_rate = stt_sample_rate
        self._tts_provider = tts_provider
        self._tts_model = tts_model

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)

        if isinstance(frame, MetricsFrame):
            for item in frame.data:
                await self._handle_metric(item)
        elif isinstance(frame, (EndFrame, CancelFrame)):
            await self._flush_stt()

        await self.push_frame(frame, direction)

    async def _handle_metric(self, item: Any) -> None:
        if isinstance(item, LLMUsageMetricsData):
            usage = item.value
            # Skip empty frames (some services emit a zero'd frame on connect).
            if usage.total_tokens == 0 and usage.prompt_tokens == 0:
                return
            await self._record_trace(
                "usage.llm",
                {
                    "prompt_tokens": usage.prompt_tokens,
                    "completion_tokens": usage.completion_tokens,
                    "total_tokens": usage.total_tokens,
                    "cache_read_input_tokens": usage.cache_read_input_tokens,
                    "reasoning_tokens": usage.reasoning_tokens,
                    "model": item.model or self._llm_model,
                    "processor": item.processor,
                },
            )
        elif isinstance(item, TTSUsageMetricsData):
            if not item.value:
                return
            await self._record_trace(
                "usage.tts",
                {
                    "characters": item.value,
                    "provider": self._tts_provider,
                    "model": self._tts_model,
                    "processor": item.processor,
                },
            )
        elif isinstance(item, TTFBMetricsData):
            if item.value <= 0:
                return
            await self._record_trace(
                "latency.ttfb",
                {
                    "processor": item.processor,
                    "model": item.model,
                    "seconds": float(item.value),
                },
            )

    async def _flush_stt(self) -> None:
        if self._stt_accumulator.flushed:
            return
        self._stt_accumulator.flushed = True
        if self._stt_accumulator.bytes_seen == 0 or self._stt_sample_rate <= 0:
            return
        samples = self._stt_accumulator.bytes_seen / _BYTES_PER_SAMPLE
        seconds = samples / self._stt_sample_rate
        await self._record_trace(
            "usage.stt",
            {
                "audio_seconds": round(seconds, 3),
                "sample_rate": self._stt_sample_rate,
                "provider": self._stt_provider,
                "model": self._stt_model,
            },
        )
