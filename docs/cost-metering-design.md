# Cross-Provider Cost Comparison: Design & Metering Plan

**Status:** Design proposal (not yet implemented)
**Date:** 2026-07-15
**Scope:** STT + TTS cost metering and cross-provider cost comparison for voice sessions.

---

## 1. Intent

VoiceLab runs each voice session on one configured STT provider and one TTS
provider (currently Deepgram or ElevenLabs). At the end of a session, the user
should see a **cost comparison**: what this exact session cost on the
configured providers, and what it *would have cost* on each alternative
provider/model.

## 2. Guiding principle

> **Cost is not a thing you measure — usage is. Cost = usage × rate.**

If usage is captured once, in provider-neutral billing units, then comparing
N providers is pure arithmetic against a rate table. The billing units are:

| Service | Billing unit | Comparable across providers? |
|---------|-------------|------------------------------|
| STT | Seconds of **audio streamed** to the provider (silence included) | Yes — same audio would be streamed to any provider |
| TTS | **Characters** of input text | Yes — exactly, the text is identical regardless of provider |
| LLM | Input/output **tokens** | Approximately (tokenizers differ) — out of scope for now |

A direct corollary: **do not run shadow sessions on other providers to learn
cost.** Real parallel calls are the right tool for comparing *quality and
latency* (which the existing STT-evaluation feature does), but for cost they
are pure waste — you would pay every provider to learn a number that is
computable from published rates. Extrapolation from measured usage is the
correct method for cost.

---

## 3. Audit of the current implementation

Findings from a full sweep of the codebase (2026-07-15):

### 3.1 Two contradictory pricing tables

- `server/app/services/pricing.py` — LLM + STT + TTS rates. **Dead code**:
  imported nowhere in `app/` (only its own test). Consumes `usage.llm` /
  `usage.stt` / `usage.tts` trace events that are no longer emitted.
- `server/app/services/stt_evaluation_pricing.py` — STT-only, the live one.
  Deepgram, ElevenLabs, Sarvam rates per audio-minute.
- The two tables **disagree** (e.g. Deepgram STT $0.0043/min vs $0.0048/min)
  and use different model naming.

### 3.2 Only STT usage is measured, and it measures the wrong thing

- `AudioBufferProcessor(enable_turn_audio=True)`
  (`pipecat_streaming_runtime.py:524`) captures per-user-turn audio.
- `compute_all_model_costs(duration_sec)`
  (`stt_evaluation_pricing.py:71`) multiplies that single turn duration by
  every provider's rate.
- **Problem:** streaming STT providers bill on audio *streamed* to them —
  silence included — not on VAD-detected speech turns. Turn-only counting
  systematically underestimates real cost.

### 3.3 TTS and LLM are not metered at all

- `PipelineParams(enable_usage_metrics=False)`
  (`pipecat_streaming_runtime.py:565`) disables Pipecat's usage metrics.
- No TTS character counting exists in the active path; no LLM token counting.
- The TTS half of the cost-comparison intent is currently 100% missing.

### 3.4 Results are stored on disk, ranked on the frontend

- Costs live in `recordings/<session_id>/metrics.jsonl`
  (`stt_evaluation_store.py`), not Postgres — not transactional, not
  queryable; losing the recordings dir loses cost history even though the
  runs still exist in the DB.
- `GET /api/audio-evaluations/agent/{agent_id}` re-reads JSONL files per
  request.
- The highest/lowest ranking is recomputed client-side on every render
  (`client/src/components/audio/AudioView.tsx:159-166`).

### 3.5 Other gaps

- **Pricing alias gap:** a live agent using Deepgram `nova-3` misses the
  pricing keys `nova-3-monolingual` / `nova-3-multilingual` and silently
  computes **$0** (`stt_evaluation_pricing.py:64-66`).
- **Sarvam mismatch:** Sarvam is priced and shadow-evaluated but is not a
  selectable live provider (`SUPPORTED_STT_PROVIDERS` excludes it,
  `schemas/agent.py:10`).
- Shadow STT calls to ElevenLabs + Sarvam run on every turn regardless of
  the agent's provider — justified for quality comparison only, and already
  gated by `enable_stt_evaluation`; keep it that way.

---

## 4. Target architecture (four layers)

### Layer 1 — Meter usage in neutral units, per session, into `trace_events`

Emit immutable usage facts alongside existing transcript events. **No prices
anywhere in these events** — prices change, facts don't.

- `usage.stt` → `{ provider, model, streamed_seconds, speech_seconds }`
- `usage.tts` → `{ processor, model, characters }` (one per synthesized
  utterance; sum per run at aggregation time)
- `usage.llm` → `{ model, input_tokens, output_tokens }` (future)

### Layer 2 — One pricing catalog, server-side

A single source of truth (delete the dead `pricing.py`). Entries keyed by
`(service, provider, model)` with:

- `unit` — per audio-minute / per 1M chars / per 1M tokens
- `rate`
- `effective_from` — so rate history is explicit
- **billing adjusters** — per-provider minimum billable duration,
  second-rounding, character-block rounding. These make the comparison
  honest; naive `duration × rate` is only an approximation.

Start as a Python module; keep the door open to a `pricing_rates` DB table so
rates can change without deploys. Fix the `nova-3` alias gap.

### Layer 3 — Compute + snapshot the comparison server-side, at session end

When the run closes: aggregate the run's usage events → apply the catalog →
produce one cost object:

- actual cost for the configured providers,
- hypothetical cost per alternative provider/model,
- **the rate used embedded in each line** (snapshot — when a provider changes
  prices next quarter, old runs must still show what was true at run time).

Store it in `runs.summary` (existing, unused JSONB column) or a small
`run_costs` table — **not** JSONL files on disk. The server also computes
ranking and deltas; the frontend only renders.

### Layer 4 — Presentation

End-of-session summary in the test-call panel and the Runs view: a table of
provider/model → estimated cost, the actually-used provider highlighted,
delta vs. actual ("ElevenLabs would have been +$0.0021, +38%"). Label
alternatives explicitly as *estimates*.

---

## 5. STT metering: what we can do, do, and should do

**The question:** how many seconds does the provider bill for a session?
Providers bill on **audio sent to them**, silence included.

### Three possible measuring points

| Option | How | Verdict |
|--------|-----|---------|
| 1. Speech turns | Capture audio only while VAD says the user is speaking | What we do today. Right for analytics, **wrong for billing** — most of a session is silence/agent speech that still streams to the provider |
| 2. Connection wall-time | Websocket open duration × sample rate | Crude approximation; ignores mutes, reconnect gaps |
| 3. **Bytes actually sent** | Count bytes crossing the wire to the provider; seconds = bytes ÷ (sample_rate × 2) for 16-bit mono PCM | **Correct** — this is exactly the billed quantity |

### Does Pipecat provide a tool for this?

**No.** Verified against the installed Pipecat 1.3.0: there is no
`STTUsageMetricsData` and no STT usage metering of any kind (STT services
emit only TTFB/processing metrics). We must count it ourselves.

### The one right seam

Pipecat's `STTService.process_audio_frame`
(`pipecat/services/stt_service.py:349`) applies all "will this audio actually
be sent" guards — reconnect buffering, mute-drop, empty-frame skip — and only
then calls `run_stt(frame.audio)`, which pushes the bytes over the provider
websocket. So **`run_stt` receives exactly the bytes the provider bills
for.**

We already subclass both STT services in
`pipecat_streaming_runtime.py` (`InstrumentedDeepgramSTTService:143` and the
ElevenLabs equivalent), so:

```python
class InstrumentedDeepgramSTTService(ProviderRequestTraceMixin, DeepgramSTTService):
    def __init__(self, ...):
        ...
        self._streamed_bytes = 0

    async def run_stt(self, audio: bytes):
        self._streamed_bytes += len(audio)
        async for frame in super().run_stt(audio):
            yield frame

    @property
    def streamed_seconds(self) -> float:
        # 16-bit mono PCM: 2 bytes per sample
        return self._streamed_bytes / (self.sample_rate * 2)
```

(`self.sample_rate` is set once the `StartFrame` arrives; input is mono per
the websocket serializer at `pipecat_streaming_runtime.py:71`.)

At session teardown (after `runner.run(task)` returns), emit one event:

```python
await record_trace("usage.stt", {
    "provider": ...,
    "model": ...,
    "streamed_seconds": stt.streamed_seconds,
})
```

### Keep both numbers

Do **not** delete the `AudioBufferProcessor` turn capture. Keep:

- `streamed_seconds` — the billing truth (feeds cost),
- `speech_seconds` — the analytics number (feeds quality/latency work).

They answer different questions.

### Free calibration signal

`InstrumentedDeepgramSTTService._on_message` already intercepts Deepgram's
`ListenV1Metadata` for `request_id`
(`pipecat_streaming_runtime.py:158-160`). That metadata also carries a
`duration` field — the seconds **Deepgram itself** says it processed. Log it
next to our byte-counted `streamed_seconds`: if they agree within rounding,
the meter is provably accurate, which is what makes extrapolated costs for
*other* providers trustworthy. No extra HTTP calls needed. (A fuller
usage-API reconciliation was attempted in commit `07f2dd9` and reverted;
revisit once metering is solid.)

---

## 6. TTS metering: Pipecat already does this — it's switched off

Pipecat has a built-in TTS usage metric. Every TTS service calls
`start_tts_usage_metrics(text)` after synthesizing, emitting a `MetricsFrame`
carrying `TTSUsageMetricsData(value=<character count>)`. Verified in the
installed package for both providers we use:

- Deepgram: `pipecat/services/deepgram/tts.py:497`
- ElevenLabs: `pipecat/services/elevenlabs/tts.py:1026`

It is gated behind the flag we currently disable:

```python
# pipecat_streaming_runtime.py:565
enable_usage_metrics=False,   # ← flip to True
```

Our `MetricsSink` (`server/app/services/pipeline_metrics.py`) already sits at
the pipeline tail and iterates `MetricsFrame` items for TTFB, so TTS metering
is a small addition:

```python
from pipecat.metrics.metrics import TTFBMetricsData, TTSUsageMetricsData

# in MetricsSink._handle_metric:
elif isinstance(item, TTSUsageMetricsData):
    await self._record_trace(
        "usage.tts",
        {"processor": item.processor, "model": item.model, "characters": int(item.value)},
    )
```

Since TTS providers bill on input characters and the text is identical
regardless of provider, the cross-provider TTS comparison is essentially
exact (modulo per-provider rounding/minimum rules from the pricing catalog).

**Caveat:** `enable_usage_metrics=True` is pipeline-wide. If the pipecat-adk
LLM bridge emits `LLMUsageMetricsData` (token counts), those frames will also
reach `MetricsSink` — handle or ignore them explicitly rather than letting
them fall through silently. If the bridge doesn't emit them, LLM tokens can
later be read from ADK/Gemini response `usage_metadata`.

---

## 7. Implementation checklist (in order)

1. **Pricing catalog** — consolidate to one table with units, effective
   dates, and billing adjusters; delete dead `pricing.py`; fix the `nova-3`
   alias gap (currently silently $0).
2. **STT metering** — ✅ implemented (2026-07-15). `SttUsageMeterMixin` counts
   bytes in `run_stt` on both instrumented STT subclasses; a `usage.stt`
   trace event (streamed + speech + provider-reported seconds) is emitted at
   session teardown; Deepgram metadata `duration` is accumulated for
   calibration. Tests in `server/tests/test_stt_usage_meter.py`.
3. **TTS metering** — flip `enable_usage_metrics=True`; add
   `TTSUsageMetricsData` branch to `MetricsSink` emitting `usage.tts`;
   explicitly handle/ignore `LLMUsageMetricsData`.
4. **Aggregation** — at run close, aggregate `usage.*` events → compute
   actual + hypothetical costs with rate snapshots → store in
   `runs.summary` (or `run_costs` table). Stop treating `metrics.jsonl` as
   the source of truth for cost.
5. **Presentation** — server-computed ranking/deltas; render in the
   test-call end screen and Runs view; label alternatives as estimates.

## 8. Key file reference

| Concern | Path |
|---------|------|
| Live pricing (STT-only) | `server/app/services/stt_evaluation_pricing.py` |
| Dead pricing (to delete) | `server/app/services/pricing.py` |
| Pipeline + instrumented services | `server/app/services/pipecat_streaming_runtime.py` |
| Metrics sink (pipeline tail) | `server/app/services/pipeline_metrics.py` |
| STT shadow evaluation | `server/app/services/stt_evaluation_service.py` |
| JSONL metrics store (to retire for cost) | `server/app/services/stt_evaluation_store.py` |
| Evaluation API | `server/app/api/routes/audio_evaluations.py` |
| Agent provider config schema | `server/app/schemas/agent.py` |
| Cost comparison UI | `client/src/components/audio/AudioView.tsx` |
| Pipecat STT base (the `run_stt` seam) | `.venv/.../pipecat/services/stt_service.py:349` |
| Pipecat usage metric types | `.venv/.../pipecat/metrics/metrics.py` |
