import json
from pathlib import Path
from typing import Any


def load_metrics_summary(metrics_path: Path) -> dict[str, Any] | None:
    turn_count = 0
    file_paths: list[str] = []
    session_summary: dict[str, Any] | None = None
    with metrics_path.open("r", encoding="utf-8") as metrics_file:
        for line in metrics_file:
            if not line.strip():
                continue
            item = json.loads(line)
            if item.get("type") == "turn.audio":
                turn_count += 1
                file_path = item.get("file_path")
                if isinstance(file_path, str) and file_path:
                    file_paths.append(file_path)
            elif item.get("type") == "session.summary":
                session_summary = item

    if session_summary is None:
        return None

    return {
        "turn_count": turn_count,
        "file_paths": file_paths,
        "session_stt_duration_sec": float(session_summary.get("session_stt_duration_sec") or 0.0),
        "session_model_costs_usd": session_summary.get("session_model_costs_usd") or {},
        "provider_session_metrics": session_summary.get("provider_session_metrics") or {},
        "evaluate_mode": bool(session_summary.get("evaluate_mode", False)),
    }
