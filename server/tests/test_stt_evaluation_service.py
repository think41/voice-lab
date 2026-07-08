import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services.stt_evaluation_service import ProviderEvaluationResult, SttEvaluationSession


class FakeSttEvaluationSession(SttEvaluationSession):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.provider_calls: list[tuple[str, str, str]] = []

    async def _evaluate_provider(
        self, provider: str, *, model: str, saved
    ) -> ProviderEvaluationResult:
        self.provider_calls.append((provider, model, saved.turn))
        return ProviderEvaluationResult(
            provider=provider,
            model=model,
            request_id=f"{provider}-req",
            duration_sec=saved.duration_sec,
            latency_ms=123.4,
            cost_usd=0.001,
            cost_source="computed",
            transcript=f"{provider} transcript",
            status="ok",
        )


def _settings(tmp_path):
    return SimpleNamespace(
        stt_evaluation_recordings_dir=str(tmp_path),
        stt_evaluation_deepgram_model="nova-2",
        stt_evaluation_elevenlabs_model="scribe_v1",
        stt_evaluation_sarvam_model="saarika:v2.5",
        stt_evaluation_sarvam_url="https://api.sarvam.ai/speech-to-text",
        deepgram_api_key=None,
        stt_api_key=None,
        elevenlabs_api_key=None,
        sarvam_api_key=None,
    )


@pytest.mark.asyncio
async def test_evaluation_session_records_turn_audio_without_provider_calls(tmp_path) -> None:
    traces: list[tuple[str, dict[str, object]]] = []
    session = FakeSttEvaluationSession(
        settings=_settings(tmp_path),
        session_id="session-1",
        run_id="run-1",
        evaluate_mode=False,
        record_trace=lambda event_type, payload: _append_trace(traces, event_type, payload),
    )

    await session.handle_user_turn_audio(b"\x00\x01" * 16000, 16000, 1)
    await session.finalize()

    assert session.provider_calls == []
    metrics = _read_metrics(tmp_path / "session-1" / "metrics.jsonl")
    assert [entry["type"] for entry in metrics] == ["turn.audio", "session.summary"]
    assert traces[0][0] == "evaluation.stt.turn_captured"
    assert traces[1][0] == "evaluation.stt.session_summary"


@pytest.mark.asyncio
async def test_evaluation_session_runs_all_three_providers_when_enabled(tmp_path) -> None:
    traces: list[tuple[str, dict[str, object]]] = []
    session = FakeSttEvaluationSession(
        settings=_settings(tmp_path),
        session_id="session-2",
        run_id="run-2",
        evaluate_mode=True,
        record_trace=lambda event_type, payload: _append_trace(traces, event_type, payload),
    )

    await session.handle_user_turn_audio(b"\x00\x01" * 16000, 16000, 1)
    await session.finalize()

    assert session.provider_calls == [
        ("deepgram", "nova-2", "T1"),
        ("elevenlabs", "scribe_v1", "T1"),
        ("sarvam", "saarika:v2.5", "T1"),
    ]
    metrics = _read_metrics(tmp_path / "session-2" / "metrics.jsonl")
    assert [entry["type"] for entry in metrics] == [
        "turn.audio",
        "provider_eval",
        "provider_eval",
        "provider_eval",
        "session.summary",
    ]
    provider_entries = [entry for entry in metrics if entry["type"] == "provider_eval"]
    assert {entry["provider"] for entry in provider_entries} == {
        "deepgram",
        "elevenlabs",
        "sarvam",
    }
    summary = metrics[-1]
    assert summary["provider_session_metrics"] == {
        "deepgram": {
            "call_count": 1,
            "success_count": 1,
            "error_count": 0,
            "latency_avg_ms": 123.4,
            "latency_median_ms": 123.4,
            "latency_p95_ms": 123.4,
        },
        "elevenlabs": {
            "call_count": 1,
            "success_count": 1,
            "error_count": 0,
            "latency_avg_ms": 123.4,
            "latency_median_ms": 123.4,
            "latency_p95_ms": 123.4,
        },
        "sarvam": {
            "call_count": 1,
            "success_count": 1,
            "error_count": 0,
            "latency_avg_ms": 123.4,
            "latency_median_ms": 123.4,
            "latency_p95_ms": 123.4,
        },
    }


async def _append_trace(
    traces: list[tuple[str, dict[str, object]]],
    event_type: str,
    payload: dict[str, object],
) -> None:
    traces.append((event_type, payload))


def _read_metrics(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
