"""Sink Pipecat metrics we still persist as trace events.

The legacy runtime `usage.stt` / `usage.tts` trace path was removed; audio
duration and model-cost comparison come from the turn-based STT evaluation
pipeline instead of runtime trace_events. `usage.llm` is recorded here from
Pipecat's `LLMUsageMetricsData`, which `AdkLLMService` emits per turn.
"""

from collections.abc import Awaitable, Callable
from typing import Any

from pipecat.frames.frames import (
    Frame,
    MetricsFrame,
)
from pipecat.metrics.metrics import (
    LLMUsageMetricsData,
    TTFBMetricsData,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

from pipeline.custom_processors.metrics.pricing import compute_cost

TraceRecorder = Callable[[str, dict[str, Any]], Awaitable[None]]


class MetricsSink(FrameProcessor):
    """Tail sink: persist non-usage metrics from Pipecat."""

    def __init__(
        self,
        *,
        record_trace: TraceRecorder,
    ) -> None:
        super().__init__()
        self._record_trace = record_trace

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)

        if isinstance(frame, MetricsFrame):
            for item in frame.data:
                await self._handle_metric(item)

        await self.push_frame(frame, direction)

    async def _handle_metric(self, item: Any) -> None:
        if isinstance(item, TTFBMetricsData):
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
        elif isinstance(item, LLMUsageMetricsData):
            if item.value.total_tokens <= 0:
                return
            usage_payload: dict[str, Any] = {
                "model": item.model,
                "prompt_tokens": item.value.prompt_tokens,
                "completion_tokens": item.value.completion_tokens,
                "total_tokens": item.value.total_tokens,
            }
            usage_payload["cost_usd"] = float(compute_cost("usage.llm", usage_payload))
            await self._record_trace("usage.llm", usage_payload)
