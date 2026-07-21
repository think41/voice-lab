import json

from pipecat.frames.frames import (
    CancelFrame,
    EndFrame,
    Frame,
    InputAudioRawFrame,
    OutputAudioRawFrame,
    OutputTransportMessageFrame,
)
from pipecat.serializers.base_serializer import FrameSerializer


class RawPcmWebsocketSerializer(FrameSerializer):
    def __init__(self, *, sample_rate: int) -> None:
        super().__init__()
        self.sample_rate = sample_rate

    async def serialize(self, frame: Frame) -> str | bytes | None:
        if isinstance(frame, OutputAudioRawFrame):
            return frame.audio
        if isinstance(frame, OutputTransportMessageFrame):
            return json.dumps(frame.message)
        if isinstance(frame, (EndFrame, CancelFrame)):
            return json.dumps({"type": "session.closed"})
        return None

    async def deserialize(self, data: str | bytes) -> Frame | None:
        if isinstance(data, bytes):
            return InputAudioRawFrame(audio=data, sample_rate=self.sample_rate, num_channels=1)
        try:
            message = json.loads(data)
        except json.JSONDecodeError:
            return None
        if message.get("type") == "stop":
            return EndFrame(reason="client stop")
        return None
