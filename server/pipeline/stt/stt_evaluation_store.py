from __future__ import annotations

import asyncio
import json
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class SavedTurnAudio:
    session_id: str
    turn: str
    speaker: str
    file_path: str
    duration_sec: float
    sample_rate: int
    num_channels: int


class SttEvaluationStore:
    def __init__(self, recordings_dir: str) -> None:
        self._recordings_root = resolve_recordings_root(recordings_dir)
        self._locks: dict[str, asyncio.Lock] = {}

    async def save_user_turn_audio(
        self,
        *,
        session_id: str,
        turn: str,
        audio: bytes,
        duration_sec: float,
        sample_rate: int,
        num_channels: int,
    ) -> SavedTurnAudio:
        session_dir = self._session_dir(session_id)
        await asyncio.to_thread(session_dir.mkdir, parents=True, exist_ok=True)
        file_path = session_dir / f"{turn}_user.wav"
        await asyncio.to_thread(
            self._write_wav,
            file_path,
            audio,
            sample_rate,
            num_channels,
        )
        return SavedTurnAudio(
            session_id=session_id,
            turn=turn,
            speaker="user",
            file_path=str(file_path),
            duration_sec=duration_sec,
            sample_rate=sample_rate,
            num_channels=num_channels,
        )

    async def append_metrics(self, session_id: str, payload: dict[str, Any]) -> None:
        session_dir = self._session_dir(session_id)
        await asyncio.to_thread(session_dir.mkdir, parents=True, exist_ok=True)
        metrics_path = session_dir / "metrics.jsonl"
        line = json.dumps(payload, ensure_ascii=True) + "\n"
        async with self._lock_for(session_id):
            await asyncio.to_thread(self._append_line, metrics_path, line)

    def _session_dir(self, session_id: str) -> Path:
        safe_session_id = session_id.replace("/", "_")
        return self._recordings_root / safe_session_id

    def _lock_for(self, session_id: str) -> asyncio.Lock:
        lock = self._locks.get(session_id)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[session_id] = lock
        return lock

    @staticmethod
    def _write_wav(path: Path, audio: bytes, sample_rate: int, num_channels: int) -> None:
        with wave.open(str(path), "wb") as wav_file:
            wav_file.setnchannels(num_channels)
            wav_file.setsampwidth(2)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(audio)

    @staticmethod
    def _append_line(path: Path, line: str) -> None:
        with path.open("a", encoding="utf-8") as metrics_file:
            metrics_file.write(line)



def resolve_recordings_root(recordings_dir: str) -> Path:
    path = Path(recordings_dir)
    if path.is_absolute():
        return path
    # parents[4] == the repo root (voice-lab/), one level above server/
    project_root = Path(__file__).resolve().parents[4]
    return project_root / path
