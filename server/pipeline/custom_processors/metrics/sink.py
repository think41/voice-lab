"""Sink Pipecat metrics we still persist as trace events.

The legacy runtime `usage.llm` / `usage.stt` / `usage.tts` trace path has been
removed. Audio duration and model-cost comparison now come from the turn-based
STT evaluation pipeline instead of runtime trace_events.
"""

from collections.abc import Awaitable, Callable
from typing import Any

from pipecat.frames.frames import (
    Frame,
    MetricsFrame,
)
from pipecat.metrics.metrics import (
    TTFBMetricsData,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

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
