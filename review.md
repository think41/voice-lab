# VoiceLab + pipecat-adk — Consolidated Review (MVP-scoped)

Findings re-scoped to the current MVP (2026-07-01):

**In scope:** create agent (name, first message, prompt), voice/speech selection, run voice/text test call, view analytics / run traces.
**Out of scope (do not fix now):** tools, notes, additional STT/TTS providers, multi-agent, dark mode.

Anything relating to unbuilt features is listed in the "Out of scope" section at the bottom so we don't lose the finding, but it is *not* a priority.

Legend: **P0** = correctness bug on the shipped flow. **P1** = maintainability / real hazard on next change. **P2** = hygiene.

---

## 1. Server (`voice-lab/server`)

### P0 — Correctness (shipped flow)

**S-2. `[HEARD]` markers can leak into transcript/trace data returned to the UI.**
- Where: `app/api/routes/runs.py:25-34` returns `trace_events` straight through.
- Why: pipecat-adk writes `<system>[HEARD] invocation_id="..." Candidate only heard: "..."</system>` events into ADK session history on interruption. The analytics view is a shipped feature — any leak surfaces as noise in the transcript. Strip these before returning.

**S-3. `app_name` hardcoded twice instead of derived from `App.name`.**
- Where: `App(name="voicelab", ...)` at `pipecat_adk_runtime.py:180`; `SessionParams(app_name="voicelab", ...)` at `pipecat_streaming_runtime.py:189` and `:289`.
- Why: pipecat-adk requires `SessionParams.app_name == App.name` or session lookups silently return `None` — voice sessions collapse with no error. Working today because both strings match. Rename `App.name` and it breaks silently. Pass `app.name` into `SessionParams`.

**S-4. `thinking_budget=0` not set on Gemini.**
- Where: `pipecat_adk_runtime.py:177` — `Agent(name=..., model=config.model, instruction=...)`.
- Why: pipecat-adk's own reference example sets `planner=BuiltInPlanner(thinking_config=types.ThinkingConfig(thinking_budget=0))`. Without it, Gemini 2.5-flash adds 1–3 s reasoning delay per turn. Free latency win on the primary voice flow.

### P1 — Structural

**S-5. `test_call_socket()` is 329 lines with 4+ levels of nested async closures.**
- Where: `app/api/routes/test_call.py:179-507`. Contains `listen_to_deepgram()` → `flush_transcript()`, `cancel_finalize_task()`, `schedule_partial_flush()` → `delayed_flush()`.
- Why: This handler is dead code from the shipped UI's perspective (frontend hits `/stream/ws/`). Either delete it (preferred — reduces MVP surface area) or extract classes. Deleting is the smaller change and matches "clean up unbuilt paths."

**S-6. `record_trace()` closure duplicated three times with identical lock/sequence logic.**
- Where: `test_call.py:98-107, 134-148, 201-215`.
- Why: Trace recording is core to the analytics feature. Three copies means three places to fix if the schema evolves or the race in S-7 is patched. Extract to a `TraceRecorder` helper.

**S-7. `trace_lock` guards the DB write but not the sequence counter read-modify-write.**
- Where: `test_call.py:132-147`, `repositories/run_repository.py:47-51`.
- Why: Concurrent events can read the same `max_trace_sequence()` before either commits → duplicate sequence numbers. Directly hurts the analytics view (traces render in wrong order or dedupe incorrectly). Move lock scope over read+write, or make sequence a DB-side monotonic counter.

**S-8. Duplicated Deepgram voice mapping, name normalization, text cleaning across the two runtimes.**
- Where: `pipecat_adk_runtime.py:21-32, 205-238, 40-47` vs `pipecat_streaming_runtime.py:159-166, 205-214, 286-295`.
- Why: Voice selection is an MVP feature. Any change to voice ID mapping needs two edits. Move to shared `providers.py` / `voice_config.py`. (If the legacy runtime is deleted per S-5, this collapses to a single-file cleanup.)

**S-9. ADK session fetch-or-create duplicated across runtimes.**
- Where: `pipecat_adk_runtime.py:119-133` vs `pipecat_streaming_runtime.py:286-295`.
- Why: `adk_session_service.py` already exists — belongs there as `ensure_session(session_params)`. Same note as S-8: mostly moot if legacy runtime is deleted.

**S-10. Dead code: `VoiceRuntime` abstract stub, `runs.status`, `runs.summary`, `RunRepository.max_trace_sequence()` (in the streaming path), legacy `/ws/{run_id}` handler.**
- Where: `services/voice_runtime.py:21-24`, `models/run.py:17-18`, `test_call.py:178-506`.
- Why: MVP hygiene — every dead pointer makes the codebase look like it does more than it does. Delete; git preserves history.

### P2 — Hygiene

**S-11. Loose version pinning.**
- Where: `pyproject.toml:16-17`. `pipecat-adk @ git+https://github.com/think41/pipecat-adk.git` (no ref — resolves HEAD), `pipecat-ai[deepgram]>=1.3.0` (unbounded major), `google-adk` / `google-genai` transitive only.
- Why: pipecat-adk's handbook says: "pin all of them." HEAD moves — a shipped MVP that rebuilds three months later could break. Pin `pipecat-adk` to a commit hash, cap `pipecat-ai<2`, declare `google-adk` / `google-genai` explicitly.

**S-12. Loggers hardcoded to `"uvicorn.error"`; inconsistent exception handling.**
- Where: `test_call.py:26`, `pipecat_adk_runtime.py:19`, `pipecat_streaming_runtime.py:40`. Mixed `logger.exception()` vs `logger.error()` vs bare `except Exception:` at `test_call.py:145, 172, 212`.
- Why: `logging.getLogger(__name__)` + `logger.exception()` inside except blocks. Debugging analytics/voice issues is harder without proper stack traces.

**S-13. CORS wide open, no pagination, no input length validation, raw exception strings leaked to clients.**
- Where: `app/main.py:16-17`, `AgentRepository.list()` / `RunRepository.list()` unbounded, `HTTPException(detail=str(exc))` at `test_call.py:119, 287`.
- Why: Small individually. `RunRepository.list()` unbounded matters if the analytics view ever accumulates runs. Cap it.

**S-14. Magic numbers scattered.**
- Where: `test_call.py:226` (5s dedup window), `:335` (1.1s partial flush), `:525` (`"1000"` utterance-end-ms), `pipecat_adk_runtime.py:180` (hardcoded app name `"voicelab"`).
- Why: Move to `core/config.py`. Tuning becomes searchable — directly helps voice latency/quality iteration.

**S-15. Missing test coverage on the shipped flow: agent CRUD roundtrip, WS lifecycle, trace persistence, `[HEARD]` filtering (once S-2 is fixed).**
- Where: `server/tests/` — 4 files only.
- Why: pipecat-adk ships `TestRunner` + `MockLLM` (`tests/mocks.py:785-1043`) for full end-to-end conversation testing with no API calls. Constraint: `TestRunner` hardcodes `app_name="agents"`. Highest-leverage tests: analytics roundtrip (create run → append events → read back → assert order + no `[HEARD]`).

---

## 2. Client (`voice-lab/client`)

### P0 — Correctness (shipped flow)

**C-1. `TestCallPanel.tsx` has no unmount cleanup.**
- Where: `client/src/components/test-call/TestCallPanel.tsx` — 440 lines, 15 refs, 7 state hooks.
- Why: Teardown relies on `socket.onclose` firing. If the panel closes first (user hits X mid-call), `AudioContext`, `MediaStream` tracks, `ScriptProcessor`, and fallback timers may leak. User-visible: mic light stays on, ghost audio. Add `useEffect(() => () => cleanupEverything(), [])`.

**C-2. No `AbortController` on any fetch in `lib/api.ts`.**
- Why: User starts a test call, closes it, opens another agent — earlier in-flight requests still `setState` on unmounted components. Analytics view is most exposed (list fetch on mount/refresh).

**C-3. Playback state race across four refs.**
- Where: `TestCallPanel.tsx:29-51` — `activePlaybackSourcesRef`, `serverAudioStoppedRef`, `playbackStartedRef`, `nextPlaybackTimeRef` mutated across `onmessage` handlers and async playback callbacks with no sync.
- Why: If `audio.output.stopped` interleaves with `playPcmChunk`, refs desync → ghost audio after "stop" or missed end-of-turn signals. Directly breaks the test-call feature. Consolidate into a `useReducer` state machine or `usePlaybackController` hook.

**C-4. 24 kHz `AudioContext` sample rate is assumed.**
- Where: `TestCallPanel.tsx:134`.
- Why: If the device doesn't support 24 kHz, playback drifts (speeds up/slows down). Voice quality is the MVP. Request the exact rate and handle failure, or resample.

### P1 — Structural

**C-5. `TestCallPanel.tsx` is a 440-line monolith mixing WebSocket, mic capture, PCM playback, UI, error handling, transcript state.**
- Why: Split into `useAudioSession` (mic + playback) and `useWebSocketSession` (socket lifecycle + message dispatch). Highest-leverage client refactor; also the file most likely to accumulate bugs against the shipped voice flow.

**C-6. `App.tsx` owns every piece of top-level state; views conditionally render without unmounting.**
- Where: `App.tsx:98-101`.
- Why: `draftConfig` survives navigating away and back. For single-agent MVP this is *probably fine* — flag it explicitly and move on. Don't restructure until we outgrow it.

**C-7. Hand-maintained `lib/types.ts` drifts from server Pydantic schemas.**
- Why: Every backend schema change is a client change with no compiler help. Generate from OpenAPI (`/openapi.json` → `openapi-typescript`). Small investment, catches contract breaks on the shipped analytics + agent-config flows.

### P2 — Hygiene

**C-8. Dead code on the shipped surface: unused STT/TTS provider option arrays, unused `Activity` icon import.**
- Where: `data/providerOptions.ts:7,9,11` (single-entry `sttProviderOptions` / `sttModelOptions` / `ttsProviderOptions`), `components/Sidebar.tsx:1`.
- Why: Delete. (Note: the empty-`onClick` "Delete" button in `AgentInspector.tsx:70` is in the tools UI — out of scope, see bottom.)

**C-9. Repeated Tailwind class strings on shipped components.**
- Where: `AgentInspector.tsx:79` (180-char `Field` label string), `TestCallPanel.tsx:364-365` (toggle-button styles), message bubbles duplicated in `TestCallPanel.tsx:31-35` vs `TraceTable.tsx:50-56`, panel/modal headers in three places.
- Why: Extract `<ToggleButton>`, `<PanelHeader>`, `<FormField>`, `<MessageBubble>`. Applies to agent-builder, test-call, and analytics — all MVP surface.

**C-11. Unmemoized derived state, inline handlers on hot paths.**
- Where: `RunsView.tsx:24-61` (metrics recomputed every render — analytics view), inline arrow handlers in `TestCallPanel.tsx:365, 378, 381, 388, 390`.
- Why: Low impact today. Bites when the runs list grows.

**C-13. Magic pixel values in Tailwind: `top-[68px]`, `top-[150px]`, `left-[120px]`.**
- Where: `TestCallPanel.tsx:354`, `AgentNode.tsx:12`.
- Why: Tie to semantic constants or Tailwind spacing scale.

---

## 3. pipecat-adk (`Projects/pipecat-adk` — think41 fork)

The library is well-designed. Only patch it when a change is genuinely a library concern.

### P1 — Optional upstream contributions

**A-2. `pyproject.toml` version mismatch.**
- Where: `pyproject.toml` says `version = "0.2.0"`; `src/pipecat_adk/__init__.py` says `__version__ = "0.3.0"`.
- Why: We own the fork. Bump `pyproject.toml` to `0.3.0`. Trivial. Directly relevant to S-11 (pinning).

**A-3. Example app hardcodes `session_id="session-002"`.**
- Where: `examples/assistant/bot.py:58`.
- Why: The library's own reference demonstrates the anti-pattern the handbook warns against. Two-line fix. Optional — voice-lab doesn't copy this pattern.

### Deferred (was A-1)

**A-1. Issue #4 (`app_factory=` callable when using `agent=` path).** Voice-lab uses `app=`, so we're not blocked. Skip unless we want to contribute upstream.

### Do NOT change

The `[HEARD]` mechanism, VqlTTSMixin ordering rule, `append_to_context=False` on `VqlLLMTextFrame`, function-call frame wiring. All load-bearing and deliberate.

---

## Priority ranking (MVP-scoped)

**Do first (correctness on shipped flow):**
1. **S-2** — strip `[HEARD]` markers before returning transcript/trace data (analytics view).
2. **C-1 + C-2** — unmount cleanup + `AbortController`.
3. **S-3** — pass `app.name` to `SessionParams`; kill the hardcoded string.
4. **S-4** — `thinking_budget=0` on Gemini. Free latency on every voice turn.
5. **C-3** — collapse the four playback refs into a reducer / controller hook.
6. **C-4** — handle 24 kHz `AudioContext` fallback.

**Do next (real hazards, hits us on next change):**
7. **S-11** — pin `pipecat-adk` to a commit hash, cap `pipecat-ai<2`. (Pairs with A-2.)
8. **S-7** — fix the trace-sequence race (lock scope or DB-side counter).
9. **S-10 + S-5** — delete legacy `/ws/{run_id}` handler and `VoiceRuntime` stub. Shrinks MVP surface, invalidates parts of S-6/S-8/S-9 automatically.
10. **C-5** — extract `useAudioSession` / `useWebSocketSession` hooks.
11. **S-6 + S-8 + S-9** — remaining shared-helper extraction (whatever's left after S-10).

**Do later (hygiene / dev velocity):**
12. **C-7** — codegen `client/src/lib/types.ts` from OpenAPI.
13. **S-15** — adopt pipecat-adk `TestRunner` for analytics-roundtrip and WS-lifecycle tests.
14. **S-12 + S-13 + S-14** — loggers, CORS/pagination/validation, magic numbers.
15. **C-8 + C-9 + C-11 + C-13** — client dead code, Tailwind extraction, memoization, magic pixels.
16. **A-2 / A-3** — optional upstream PRs.

---

## Out of scope (not MVP — do NOT fix now)

These findings from earlier audits touch features that aren't shipped. Kept here for future reference; do not action until the corresponding feature is actually being built.

- **S-1. Tools stored but not forwarded to ADK** (`schemas/agent.py:22`, `pipecat_adk_runtime.py:175-179`). Tools are UI-only right now. When tools become a live feature, wire `config.tools` into `Agent(tools=[...])`. Until then, don't remove the schema field either — the UI still writes to it.
- **AgentInspector "Delete" button with empty `onClick`** (`components/builder/AgentInspector.tsx:70`) — part of the unbuilt tools UI.
- **Fragile tool list key** (`AgentInspector.tsx:61`, `key={`${tool.name}-${index}`}`) — unbuilt tools UI.
- **C-10. Provider registry with capability metadata** — only ships Deepgram right now. Revisit when adding a second STT/TTS provider.
- **C-12. Dark mode variants** — theme is defined but not wired. Either delete the theme entries or defer until dark mode is a real product decision.
- **Notes feature** — does not exist. Ignore any references.

**Don't do at all:**
- Half-implemented features, "just in case" abstractions.
- Anything touching `[HEARD]`, `VqlTTSMixin`, or aggregator wiring in pipecat-adk. Working as designed.
