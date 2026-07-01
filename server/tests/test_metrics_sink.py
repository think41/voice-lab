import pytest
from pipecat.frames.frames import EndFrame, InputAudioRawFrame, MetricsFrame
from pipecat.metrics.metrics import (
    LLMTokenUsage,
    LLMUsageMetricsData,
    TTFBMetricsData,
    TTSUsageMetricsData,
)
from pipecat.processors.frame_processor import FrameDirection

from app.services.pipeline_metrics import (
    AudioInputCounter,
    MetricsSink,
    SttUsageAccumulator,
)


class _StubRecorder:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    async def __call__(self, event_type: str, payload: dict) -> None:
        self.calls.append((event_type, payload))


def _build(recorder: _StubRecorder, accumulator: SttUsageAccumulator) -> MetricsSink:
    return MetricsSink(
        record_trace=recorder,
        stt_accumulator=accumulator,
        llm_model="gemini-2.5-flash",
        stt_provider="deepgram",
        stt_model="nova-3",
        stt_sample_rate=48000,
        tts_provider="deepgram",
        tts_model="aura-2",
    )


@pytest.mark.asyncio
async def test_metrics_sink_records_llm_usage() -> None:
    recorder = _StubRecorder()
    accumulator = SttUsageAccumulator()
    sink = _build(recorder, accumulator)
    frame = MetricsFrame(
        data=[
            LLMUsageMetricsData(
                processor="AdkLLMService",
                model=None,
                value=LLMTokenUsage(
                    prompt_tokens=42,
                    completion_tokens=13,
                    total_tokens=55,
                    cache_read_input_tokens=0,
                    reasoning_tokens=0,
                ),
            )
        ]
    )
    await sink.process_frame(frame, FrameDirection.DOWNSTREAM)
    types = [call[0] for call in recorder.calls]
    assert "usage.llm" in types
    payload = next(p for t, p in recorder.calls if t == "usage.llm")
    assert payload["prompt_tokens"] == 42
    assert payload["completion_tokens"] == 13
    assert payload["total_tokens"] == 55
    assert payload["model"] == "gemini-2.5-flash"


@pytest.mark.asyncio
async def test_metrics_sink_skips_zeroed_llm_frame() -> None:
    recorder = _StubRecorder()
    accumulator = SttUsageAccumulator()
    sink = _build(recorder, accumulator)
    frame = MetricsFrame(
        data=[
            LLMUsageMetricsData(
                processor="AdkLLMService",
                model=None,
                value=LLMTokenUsage(
                    prompt_tokens=0, completion_tokens=0, total_tokens=0
                ),
            )
        ]
    )
    await sink.process_frame(frame, FrameDirection.DOWNSTREAM)
    assert all(t != "usage.llm" for t, _ in recorder.calls)


@pytest.mark.asyncio
async def test_metrics_sink_records_tts_and_ttfb() -> None:
    recorder = _StubRecorder()
    accumulator = SttUsageAccumulator()
    sink = _build(recorder, accumulator)
    frame = MetricsFrame(
        data=[
            TTSUsageMetricsData(processor="DeepgramTTSService", model=None, value=100),
            TTFBMetricsData(processor="AdkLLMService", model=None, value=0.42),
        ]
    )
    await sink.process_frame(frame, FrameDirection.DOWNSTREAM)
    kinds = {t for t, _ in recorder.calls}
    assert {"usage.tts", "latency.ttfb"}.issubset(kinds)
    tts_payload = next(p for t, p in recorder.calls if t == "usage.tts")
    assert tts_payload["characters"] == 100
    ttfb_payload = next(p for t, p in recorder.calls if t == "latency.ttfb")
    assert ttfb_payload["seconds"] == pytest.approx(0.42)


@pytest.mark.asyncio
async def test_audio_input_counter_and_stt_flush_on_end_frame() -> None:
    recorder = _StubRecorder()
    accumulator = SttUsageAccumulator()
    counter = AudioInputCounter(accumulator)
    sink = _build(recorder, accumulator)

    # Feed 1s of 48kHz 16-bit mono = 96_000 bytes.
    audio = InputAudioRawFrame(audio=b"\x00" * 96_000, sample_rate=48000, num_channels=1)
    await counter.process_frame(audio, FrameDirection.DOWNSTREAM)
    assert accumulator.bytes_seen == 96_000

    await sink.process_frame(EndFrame(), FrameDirection.DOWNSTREAM)
    stt = next(p for t, p in recorder.calls if t == "usage.stt")
    assert stt["audio_seconds"] == pytest.approx(1.0, abs=0.001)
    assert stt["provider"] == "deepgram"
    assert stt["model"] == "nova-3"

    # Second flush should be a no-op (guarded).
    await sink.process_frame(EndFrame(), FrameDirection.DOWNSTREAM)
    stt_events = [t for t, _ in recorder.calls if t == "usage.stt"]
    assert len(stt_events) == 1
