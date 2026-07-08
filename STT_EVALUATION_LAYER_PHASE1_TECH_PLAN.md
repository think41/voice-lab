# Voice-Lab — STT Evaluation Layer: Phase 1 Tech Plan (Final)

## 1. Goal

Build an evaluation/observability layer for Voice-Lab that measures **cost** and
**latency** of user-turn audio across three STT providers — Deepgram, ElevenLabs,
Sarvam — using the same saved audio for all three, without affecting the live
conversation.

**Explicitly out of scope for Phase 1:** bot-turn audio, TTS evaluation, accuracy/WER,
relevancy scoring. These are later phases (see Roadmap, section 15).

## 2. Scope of this phase

- Capture: **user-turn audio only** (bot-turn audio is not captured at all right now)
- Metrics captured for real API calls: **duration, cost, latency, request_id**
- Cost table shown for **all known models of all three providers** (see section 6.2)
- Providers called for real data: **one model per provider** (production model),
  to control API spend

## 3. Architecture

```text
Live call (Voice-Lab agent, any config)
        |
        v
AudioBufferProcessor (enable_turn_audio=True)
        |
        v
on_user_turn_audio_data fires - once per user turn
        |
        |- Compute duration from raw bytes (Method 1 - in-memory, no file needed)
        |- Save turn audio to disk: recordings/{session_id}/T{n}_user.wav
        |      (needed so we can POST it to each provider's API)
        |
        \- If Evaluate Mode is ON:
                 |- Deepgram   (FOREGROUND - blocking, hard requirement)
                 |- ElevenLabs (BACKGROUND - non-blocking)
                 \- Sarvam     (BACKGROUND - non-blocking)
```

## 4. Duration — computed once, from raw bytes (Method 1)

Duration is computed directly from the raw PCM bytes Pipecat hands us in the callback
(sample count / sample rate) — **not** by reading the saved `.wav` file back. This
avoids a round-trip through a second write/read step where a mistake (wrong sample
rate/channel count at save-time) could silently produce a wrong number.

- Logged per turn
- **Accumulated into a running session total** as the call happens — by the time the
  session ends, whole-session STT duration is already fully known. No extra
  calculation step is needed at session-end; it has been building up the whole time.

The saved `.wav` file is kept only so the provider API calls have real audio bytes to
send — it is not the source of the duration number.

## 5. Storage — files on disk, DB (if used) stores paths only

**Audio is never stored inside Postgres (or any DB) as a blob.** It stays on the
filesystem:

```text
recordings/
\- {session_id}/
    |- T1_user.wav
    |- T2_user.wav
    |- ...
    \- metrics.jsonl
```

If/when a real DB table is added later, it holds a **reference layer only**:

```sql
CREATE TABLE turn_recordings (
    session_id   TEXT NOT NULL,
    turn_id      TEXT NOT NULL,
    speaker      TEXT NOT NULL,
    file_path    TEXT NOT NULL,
    duration_sec FLOAT NOT NULL,
    created_at   TIMESTAMP DEFAULT now(),
    PRIMARY KEY (session_id, turn_id, speaker)
);
```

Reasons: audio blobs bloat DB size/backups, can't be streamed/scrubbed directly from a
row, and provider API calls need raw bytes from disk anyway — no benefit to routing
audio through the DB itself.

Phase 1 uses `metrics.jsonl` (path + metadata) as this reference layer — no DB required
yet.

## 6. Cost

### 6.1 Confirmed directly from all three providers: no live "pricing API" exists

We checked this directly with each provider's docs/support:
- **Deepgram**: no endpoint returns real-time pricing per model. Only a *post-request*
  usage lookup exists (see 6.3).
- **ElevenLabs**: no endpoint returns dollar-cost-per-character in real time. Only usage/
  subscription consumption data exists (character count vs plan limit) — not a per-
  request cost.
- **Sarvam**: usage is visible only via a dashboard (`dashboard.sarvam.ai/usage`), no
  API.

**Conclusion: this is an industry-wide pattern, not a gap specific to one provider.**
Every provider expects the caller to know their published rate and compute cost
locally. Our rate table is therefore a **static config we maintain ourselves**, not
something fetched per session or per call.

### 6.2 Cost table — shown for ALL models of all three providers (free to compute)

Since `cost = duration x rate`, and duration doesn't depend on which model is being
priced, **the same single duration value can price every model of every provider with
zero extra API calls** — pure arithmetic, no additional cost or latency incurred.

```python
RATE_PER_MINUTE_USD = {
    "deepgram": {
        "nova-3-monolingual": 0.0048,
        "nova-3-multilingual": 0.0058,
        "nova-2": 0.0043,
    },
    "elevenlabs": {
        "scribe-v1": 0.0055,
        "scribe-v2-realtime": 0.0065,
    },
    "sarvam": {
        "saarika-v1": 0.0055,
        "saarika-v2": 0.0060,
    },
}

def compute_all_model_costs(duration_sec: float) -> dict:
    duration_min = duration_sec / 60.0
    return {
        provider: {model: round(duration_min * rate, 6) for model, rate in models.items()}
        for provider, models in RATE_PER_MINUTE_USD.items()
    }
```

**Important boundary:** this only gives estimated cost across all models. Real
**latency**, **transcript**, and **request_id** for a specific model still require an
actual API call to that model — those stay limited to the one production model per
provider we're actively testing, to control real API spend.

| | Cost across all models | Latency / transcript / request_id |
|---|---|---|
| Method | Local math, same duration reused | Real API call, per model |
| Cost to compute | Free | Paid, per call |
| Scope in Phase 1 | All known models, all 3 providers | One model per provider only |

### 6.3 Optional reconciliation — real billed cost, Deepgram only

Deepgram provides a post-request usage lookup (not a pricing API — a lookup of what a
*specific already-made request* actually cost):

```python
async def reconcile_deepgram_cost(project_id: str, request_id: str) -> float:
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"https://api.deepgram.com/v1/projects/{project_id}/requests/{request_id}",
            headers={"Authorization": f"Token {DEEPGRAM_API_KEY}"},
        )
    return r.json()["request"]["response"]["details"]["usd"]
```

- This is **optional** — a validation check against our computed cost, not a
  dependency. Our locally-computed cost is already available the moment the turn
  happens.
- **Retention limit: 90 days.** Deepgram only keeps usage log data for 90 days — any
  reconciliation must happen within that window, or only our local estimate remains.
- **ElevenLabs**: closest equivalent is `GET /v1/user/subscription` — gives usage/
  character-count deltas against plan limits, not a per-request `cost_usd` figure. Can
  be used as a coarser sanity check (did total consumption roughly match expectations),
  not a per-turn reconciliation.
- **Sarvam**: no equivalent exists. Local estimate is the only number we will ever have
  — this is fine, since Sarvam's billing is duration-based and we control the audio.

## 7. Latency — always measured client-side, never from a provider response

No provider returns a "latency" field, for any model. We wrap each API call with a
timer (`time.monotonic()` before/after) — the elapsed time is our latency measurement.
Identical method across all three providers, making it directly comparable.

## 8. request_id — captured for traceability, location differs per provider

| Provider | Where request_id comes from |
|---|---|
| Deepgram | Response body (`metadata.request_id`) |
| ElevenLabs | Response **headers** (`request-id`) — not in the JSON body |
| Sarvam | Response body (`request_id`) |

## 9. Foreground vs background

- **Deepgram: foreground** — the code waits for its response before moving on. Hard
  requirement for this phase.
- **ElevenLabs and Sarvam: background** (`asyncio.create_task`) — fired without
  waiting, never block anything else. Logged whenever each completes.

## 10. What changes vs. our previous (pre-audio-buffer) approach

**Previous approach:**

```text
Live streaming STT call -> Deepgram issues a request_id -> store request_id in
trace_events -> AFTER session ends, call Deepgram's Usage/Billing API with that
request_id -> get back cost/duration for that request.
```

This was **mandatory** in the old flow — it was the only way to get a cost number.

**New approach (this plan):** duration and cost are known **the moment each turn
happens**, computed locally, with zero dependency on any billing API. The Deepgram
billing lookup becomes an **optional reconciliation step**, not a requirement — and
only Deepgram offers even that option; ElevenLabs/Sarvam have no per-request
equivalent, so local computation is their permanent, only cost source.

## 11. Per-turn metrics record (metrics.jsonl)

```json
{
  "session_id": "abc123",
  "turn": "T1",
  "speaker": "user",
  "provider": "deepgram",
  "model": "nova-3-monolingual",
  "request_id": "...",
  "duration_sec": 3.21,
  "latency_ms": 410.0,
  "cost_usd": 0.000257,
  "cost_source": "computed"
}
```

## 12. Session-level rollup

Already computed continuously, simply summed at session end:

```text
session_stt_duration_sec  = sum(per-turn durations)
session_cost[provider]    = session_stt_duration_min x provider_rate   (per model too)
```

## 13. Evaluate Mode — why it exists

Since this makes 2-3 extra paid API calls per user turn (for the one model per provider
being tested for real metrics), it must be an **explicit opt-in flag**, not always-on —
avoiding unnecessary provider cost during normal day-to-day development/testing.

## 14. Summary of key decisions locked in this phase

| Decision | Answer |
|---|---|
| Bot audio capture | Not in scope yet |
| Duration source | Raw bytes (Method 1), not the saved file |
| Audio storage | Disk only, never DB blob |
| DB (if added) | Path + metadata reference only |
| Pricing API per provider | Confirmed: none exists, for any of the three |
| Cost across all models | Free — same duration, different rate constants |
| Real latency/transcript across all models | Not free — limited to 1 model/provider |
| Deepgram real-cost reconciliation | Optional, within 90 days |
| ElevenLabs real-cost reconciliation | Coarser usage-delta only, not per-request |
| Sarvam real-cost reconciliation | Not available — estimate is permanent |
| Deepgram call mode | Foreground (blocking) |
| ElevenLabs / Sarvam call mode | Background (non-blocking) |
| Trigger | Evaluate Mode flag, opt-in only |

## 15. Roadmap — not in this phase, but where this is heading

- Bot-turn audio capture + TTS cost/latency evaluation
- Accuracy: Word Error Rate (WER) against a small human-verified reference transcript set
- Relevancy scoring
- LLM-stage token/cost tracking
- Promote `metrics.jsonl` to a real DB table (schema in section 5) once volume justifies it
