import pytest
from pipecat.frames.frames import MetricsFrame
from pipecat.metrics.metrics import (
    TTFBMetricsData,
)
from pipecat.processors.frame_processor import FrameDirection

from pipeline.custom_processors.metrics.sink import MetricsSink


class _StubRecorder:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    async def __call__(self, event_type: str, payload: dict) -> None:
        self.calls.append((event_type, payload))


def _build(recorder: _StubRecorder) -> MetricsSink:
    return MetricsSink(record_trace=recorder)


@pytest.mark.asyncio
async def test_metrics_sink_records_ttfb() -> None:
    recorder = _StubRecorder()
    sink = _build(recorder)
    frame = MetricsFrame(
        data=[
            TTFBMetricsData(processor="AdkLLMService", model=None, value=0.42),
        ]
    )
    await sink.process_frame(frame, FrameDirection.DOWNSTREAM)
    kinds = {t for t, _ in recorder.calls}
    assert kinds == {"latency.ttfb"}
    ttfb_payload = next(p for t, p in recorder.calls if t == "latency.ttfb")
    assert ttfb_payload["seconds"] == pytest.approx(0.42)
