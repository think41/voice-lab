from pipecat.frames.frames import (
    BotStartedSpeakingFrame,
    BotStoppedSpeakingFrame,
    Frame,
    InterimTranscriptionFrame,
    TranscriptionFrame,
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
    def __init__(self, record_trace: TraceRecorder, send_event: EventSender) -> None:
        super().__init__()
        self._record_trace = record_trace
        self._send_event = send_event

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)

        if isinstance(frame, InterimTranscriptionFrame) and frame.text.strip():
            await self._send_event({"type": "transcript.partial", "text": frame.text})
        elif isinstance(frame, TranscriptionFrame) and frame.text.strip():
            await self._record_trace("transcript.final", {"role": "user", "text": frame.text})
            await self._send_event({"type": "transcript.final", "text": frame.text})
            await self._send_event({"type": "agent.thinking"})

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
