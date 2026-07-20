import json
import wave

import pytest

from pipeline.stt.stt_evaluation_store import SttEvaluationStore


@pytest.mark.asyncio
async def test_store_writes_turn_audio_and_metrics(tmp_path) -> None:
    store = SttEvaluationStore(str(tmp_path))
    audio = b"\x00\x01" * 16000

    saved = await store.save_user_turn_audio(
        session_id="session-1",
        turn="T1",
        audio=audio,
        duration_sec=1.0,
        sample_rate=16000,
        num_channels=1,
    )
    await store.append_metrics(
        "session-1",
        {"type": "turn.audio", "turn": "T1", "duration_sec": 1.0},
    )

    with wave.open(saved.file_path, "rb") as wav_file:
        assert wav_file.getframerate() == 16000
        assert wav_file.getnchannels() == 1
        assert wav_file.readframes(wav_file.getnframes()) == audio

    metrics_path = tmp_path / "session-1" / "metrics.jsonl"
    lines = metrics_path.read_text(encoding="utf-8").strip().splitlines()
    assert [json.loads(line) for line in lines] == [
        {"type": "turn.audio", "turn": "T1", "duration_sec": 1.0}
    ]
