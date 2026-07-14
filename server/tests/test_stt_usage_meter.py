from collections.abc import AsyncGenerator

import pytest
from pipecat.frames.frames import Frame

from app.services.pipecat_streaming_runtime import SttUsageMeterMixin


class _FakeSTTService:
    def __init__(self, sample_rate: int) -> None:
        self._sample_rate = sample_rate
        self.received: list[bytes] = []

    @property
    def sample_rate(self) -> int:
        return self._sample_rate

    async def run_stt(self, audio: bytes) -> AsyncGenerator[Frame | None, None]:
        self.received.append(audio)
        yield None


class _MeteredService(SttUsageMeterMixin, _FakeSTTService):
    pass


async def _drain(gen: AsyncGenerator) -> None:
    async for _ in gen:
        pass


@pytest.mark.asyncio
async def test_streamed_seconds_counts_all_forwarded_audio() -> None:
    service = _MeteredService(sample_rate=16000)
    # 16-bit mono at 16 kHz: 32000 bytes per second.
    await _drain(service.run_stt(b"\x00" * 32000))
    await _drain(service.run_stt(b"\x00" * 16000))
    assert service.streamed_audio_seconds == pytest.approx(1.5)
    assert service.received == [b"\x00" * 32000, b"\x00" * 16000]


@pytest.mark.asyncio
async def test_streamed_seconds_zero_without_audio_or_sample_rate() -> None:
    service = _MeteredService(sample_rate=16000)
    assert service.streamed_audio_seconds == 0.0

    unstarted = _MeteredService(sample_rate=0)
    await _drain(unstarted.run_stt(b"\x00" * 3200))
    assert unstarted.streamed_audio_seconds == 0.0


@pytest.mark.asyncio
async def test_meter_state_is_per_instance() -> None:
    first = _MeteredService(sample_rate=16000)
    second = _MeteredService(sample_rate=16000)
    await _drain(first.run_stt(b"\x00" * 32000))
    assert second.streamed_audio_seconds == 0.0


def test_provider_reported_seconds_defaults_to_none() -> None:
    service = _MeteredService(sample_rate=16000)
    assert service.provider_reported_audio_seconds is None
    service._provider_reported_audio_seconds += 2.5
    assert service.provider_reported_audio_seconds == pytest.approx(2.5)
