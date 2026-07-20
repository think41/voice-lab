from typing import Any

from pipecat.frames.frames import (
    BotStartedSpeakingFrame,
    BotStoppedSpeakingFrame,
    Frame,
    InterimTranscriptionFrame,
    OutputAudioRawFrame,
    TranscriptionFrame,
    UserStartedSpeakingFrame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat_adk.frames import (
    VqlLLMFullResponseEndFrame,
    VqlLLMFullResponseStartFrame,
    VqlLLMTextFrame,
)

from pipeline.llm.adk_runtime import PipecatAdkRuntime
from pipeline.utils.tracing import EventSender, TraceRecorder


class UserTranscriptBridge(FrameProcessor):
    def __init__(
        self,
        record_trace: TraceRecorder,
        send_event: EventSender,
        stt_service: Any,
        stt_provider: str,
        stt_model: str,
    ) -> None:
        super().__init__()
        self._record_trace = record_trace
        self._send_event = send_event
        self._stt = stt_service
        self._stt_provider = stt_provider
        self._stt_model = stt_model
        self._turn_index = 0

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)

        if isinstance(frame, UserStartedSpeakingFrame):
            self._stt.note_utterance_start()
        elif isinstance(frame, InterimTranscriptionFrame) and frame.text.strip():
            await self._send_event({"type": "transcript.partial", "text": frame.text})
        elif isinstance(frame, TranscriptionFrame) and frame.text.strip():
            latency_ms = self._stt.note_transcript_final()
            self._turn_index += 1
            if latency_ms is not None:
                await self._record_trace(
                    "latency.stt.turn",
                    {
                        "provider": self._stt_provider,
                        "model": self._stt_model,
                        "latency_ms": round(latency_ms, 1),
                        "turn_index": self._turn_index,
                    },
                )
            await self._record_trace("transcript.final", {"role": "user", "text": frame.text})
            await self._send_event({"type": "transcript.final", "text": frame.text})
            await self._send_event({"type": "agent.thinking"})

        await self.push_frame(frame, direction)


class TtsLatencyBridge(FrameProcessor):
    """Placed immediately after the TTS service. When a `run_tts` invocation
    is pending a start timestamp on the TTS service, closes it out on the
    first audio frame observed downstream and emits `latency.tts.turn`.
    """

    def __init__(
        self,
        record_trace: TraceRecorder,
        tts_service: Any,
        tts_provider: str,
        tts_model: str,
    ) -> None:
        super().__init__()
        self._record_trace = record_trace
        self._tts = tts_service
        self._tts_provider = tts_provider
        self._tts_model = tts_model
        self._invocation_index = 0

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)

        if isinstance(frame, OutputAudioRawFrame):
            latency_ms = self._tts.note_first_audio()
            if latency_ms is not None:
                self._invocation_index += 1
                await self._record_trace(
                    "latency.tts.turn",
                    {
                        "provider": self._tts_provider,
                        "model": self._tts_model,
                        "latency_ms": round(latency_ms, 1),
                        "turn_index": self._invocation_index,
                    },
                )

        await self.push_frame(frame, direction)


class AssistantTraceBridge(FrameProcessor):
    def __init__(
        self,
        record_trace: TraceRecorder,
        send_event: EventSender,
        helper: PipecatAdkRuntime,
    ) -> None:
        super().__init__()
        self._record_trace = record_trace
        self._send_event = send_event
        self._helper = helper
        self._assistant_text_parts: list[str] = []

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)

        if isinstance(frame, VqlLLMFullResponseStartFrame):
            self._assistant_text_parts = []
        elif isinstance(frame, VqlLLMTextFrame):
            if frame.text:
                self._assistant_text_parts.append(frame.text)
            text = self._helper.clean_model_text(frame.text)
            if text:
                await self._send_event({"type": "agent.text.delta", "text": text})
        elif isinstance(frame, VqlLLMFullResponseEndFrame):
            text = self._helper.clean_model_text("".join(self._assistant_text_parts))
            if text:
                await self._record_trace("agent.text", {"role": "assistant", "text": text})
            self._assistant_text_parts = []

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
