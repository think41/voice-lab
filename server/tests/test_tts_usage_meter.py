from collections.abc import AsyncGenerator

import pytest
from pipecat.frames.frames import Frame

from app.services.pipecat_streaming_runtime import TtsUsageMeterMixin


class _FakeTTSService:
    def __init__(self) -> None:
        self.received: list[str] = []

    async def run_tts(self, text: str, context_id: str) -> AsyncGenerator[Frame | None, None]:
        self.received.append(text)
        yield None


class _MeteredService(TtsUsageMeterMixin, _FakeTTSService):
    pass


async def _drain(gen: AsyncGenerator) -> None:
    async for _ in gen:
        pass


@pytest.mark.asyncio
async def test_sent_characters_counts_all_text_sent_to_provider() -> None:
    service = _MeteredService()
    await _drain(service.run_tts("Hello there.", "ctx-1"))
    await _drain(service.run_tts("How can I help?", "ctx-1"))
    assert service.sent_characters == len("Hello there.") + len("How can I help?")
    assert service.received == ["Hello there.", "How can I help?"]


@pytest.mark.asyncio
async def test_sent_characters_counted_even_when_generator_not_drained() -> None:
    # Characters are billed once sent; an interruption that abandons the
    # generator must not un-count text that already left for the provider.
    service = _MeteredService()
    gen = service.run_tts("This sentence gets interrupted mid-playback.", "ctx-1")
    await gen.__anext__()
    await gen.aclose()
    assert service.sent_characters == len("This sentence gets interrupted mid-playback.")


@pytest.mark.asyncio
async def test_meter_state_is_per_instance() -> None:
    first = _MeteredService()
    second = _MeteredService()
    await _drain(first.run_tts("only counted on first", "ctx-1"))
    assert second.sent_characters == 0


def test_sent_characters_defaults_to_zero() -> None:
    assert _MeteredService().sent_characters == 0
