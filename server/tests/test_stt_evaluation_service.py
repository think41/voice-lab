import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services.stt_evaluation_service import SttEvaluationSession


def _settings(tmp_path):
    return SimpleNamespace(
        stt_evaluation_recordings_dir=str(tmp_path),
    )


@pytest.mark.asyncio
async def test_evaluation_session_records_turn_audio_and_summary(tmp_path) -> None:
    traces: list[tuple[str, dict[str, object]]] = []
    session = SttEvaluationSession(
        settings=_settings(tmp_path),
        session_id="session-1",
        run_id="run-1",
        record_trace=lambda event_type, payload: _append_trace(traces, event_type, payload),
    )

    await session.handle_user_turn_audio(b"\x00\x01" * 16000, 16000, 1)
    await session.finalize()

    metrics = _read_metrics(tmp_path / "session-1" / "metrics.jsonl")
    assert [entry["type"] for entry in metrics] == ["turn.audio", "session.summary"]
    assert metrics[0]["all_model_costs_usd"]
    assert traces[0][0] == "evaluation.stt.turn_captured"
    assert traces[1] == (
        "evaluation.stt.session_summary",
        {"session_stt_duration_sec": pytest.approx(1.0)},
    )


@pytest.mark.asyncio
async def test_evaluation_session_tracks_multiple_turns_and_tts_summary(tmp_path) -> None:
    session = SttEvaluationSession(
        settings=_settings(tmp_path),
        session_id="session-2",
        run_id="run-2",
        record_trace=_noop_trace,
    )

    await session.handle_user_turn_audio(b"\x00\x01" * 16000, 16000, 1)
    await session.handle_user_turn_audio(b"\x00\x01" * 8000, 16000, 1)
    await session.finalize(tts_sent_characters=42)

    metrics = _read_metrics(tmp_path / "session-2" / "metrics.jsonl")
    summary = metrics[-1]
    assert session.session_duration_sec == pytest.approx(1.5)
    assert summary["session_stt_duration_sec"] == pytest.approx(1.5)
    assert summary["session_model_costs_usd"]
    assert summary["session_tts_sent_characters"] == 42
    assert summary["session_tts_model_costs_usd"]


async def _append_trace(
    traces: list[tuple[str, dict[str, object]]],
    event_type: str,
    payload: dict[str, object],
) -> None:
    traces.append((event_type, payload))


async def _noop_trace(_event_type: str, _payload: dict[str, object]) -> None:
    return None


def _read_metrics(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
