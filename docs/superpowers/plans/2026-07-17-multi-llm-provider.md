# Multi-LLM-Provider Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a saved agent config select OpenAI or Anthropic (Claude) models in addition to Gemini, on both the text and voice paths, with zero changes to pipecat-adk.

**Architecture:** The LLM is selected in `PipecatAdkRuntime.build_adk_app()` via `Agent(model=<string>)`. Google ADK 2.2.0's `LLMRegistry` already resolves model-id strings by pattern: `gemini-*` → native Gemini, `openai/...` and `anthropic/...` → the `LiteLlm` wrapper (requires the `litellm` package, keys read from `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` env vars). So the work is: open the schema whitelist, export the right env key per provider, make the Gemini-only planner conditional, and replace the two hard `GEMINI_API_KEY` gates with per-provider checks. pipecat-adk (`AdkLLMService`) receives the pre-built `App` and is provider-blind — no changes there.

**Model-ID convention (decided):** Gemini models stay bare (`gemini-3.5-flash`). All other providers use LiteLLM-prefixed IDs (`openai/gpt-5.1`, `anthropic/claude-sonnet-5`). The prefix doubles as the provider discriminator: `llm_provider_for_model()` returns the segment before `/`, or `"gemini"` when there is no slash. This scales to Groq/Mistral/etc. later without another refactor.

**Tech Stack:** FastAPI, pydantic, google-adk 2.2.0, litellm (new dep), pytest (`uv run pytest -q`), ruff.

**Out of scope (follow-ups, not in this plan):**
- Frontend model dropdown (`client/src/data/providerOptions.ts`) — until that's updated, select non-Gemini models via the UI's JSON config editor or the agents API.
- Latency benchmarking of non-Gemini models on the voice path (the pipecat-adk handbook flags LiteLLM voice latency as a risk — measure with the existing `pipeline_metrics.py` instrumentation before presenting these as equal options in the UI).
- Per-provider pricing in `services/pricing.py`.

**Curated model IDs** (constants, easy to extend later):
- Gemini (existing): `gemini-3.5-flash`, `gemini-3.1-flash-lite`
- Anthropic: `anthropic/claude-sonnet-5`, `anthropic/claude-haiku-4-5`, `anthropic/claude-opus-4-8` (current IDs per Anthropic docs, verified 2026-07-17)
- OpenAI: `openai/gpt-5.1`, `openai/gpt-5-mini` (**verify against OpenAI's live model list in Task 6 before demoing** — OpenAI IDs move fast; if an ID 404s, edit the constant in `schemas/agent.py`, nothing else changes)

---

### Task 1: Dependency + settings fields

**Files:**
- Modify: `server/pyproject.toml`
- Modify: `server/app/core/config.py`
- Modify: `server/.env.example`
- Test: `server/tests/test_settings.py` (new)

- [ ] **Step 1: Write the failing test**

Create `server/tests/test_settings.py`:

```python
from app.core.config import Settings


def test_settings_have_llm_provider_key_fields() -> None:
    settings = Settings(_env_file=None)
    assert settings.openai_api_key is None
    assert settings.anthropic_api_key is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server && uv run pytest tests/test_settings.py -v`
Expected: FAIL with `AttributeError: 'Settings' object has no attribute 'openai_api_key'`

- [ ] **Step 3: Add the settings fields**

In `server/app/core/config.py`, after the line `gemini_api_key: str | None = None` (line 16), add:

```python
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
```

- [ ] **Step 4: Add the litellm dependency**

In `server/pyproject.toml`, append to the `dependencies` list (after the `google-genai` line):

```toml
    # LiteLLM backs ADK's openai/... and anthropic/... model-id resolution.
    "litellm>=1.70",
```

Run: `cd server && uv sync`
Expected: resolves and installs `litellm` without dependency conflicts. If the resolver reports a conflict with `google-adk`/`pipecat-ai`, relax the pin to the version the resolver suggests and note it in the commit message.

- [ ] **Step 5: Add env placeholders**

In `server/.env.example`, after the `GEMINI_API_KEY=` line, add:

```dotenv
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
```

- [ ] **Step 6: Run test to verify it passes**

Run: `cd server && uv run pytest tests/test_settings.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add server/pyproject.toml server/uv.lock server/app/core/config.py server/.env.example server/tests/test_settings.py
git commit -m "feat: add litellm dependency and OpenAI/Anthropic key settings"
```

---

### Task 2: Schema — provider map, provider helper, open the model whitelist

**Files:**
- Modify: `server/app/schemas/agent.py:5-9` (replace `SUPPORTED_MODELS` block)
- Test: `server/tests/test_agent_config.py`

- [ ] **Step 1: Write the failing tests**

Append to `server/tests/test_agent_config.py`:

```python
from app.schemas.agent import llm_provider_for_model


def test_llm_provider_for_model_derives_provider_from_prefix() -> None:
    assert llm_provider_for_model('gemini-3.5-flash') == 'gemini'
    assert llm_provider_for_model('openai/gpt-5.1') == 'openai'
    assert llm_provider_for_model('anthropic/claude-sonnet-5') == 'anthropic'


def test_agent_config_accepts_openai_and_anthropic_models() -> None:
    config = AgentConfig(name='Support Agent', model='openai/gpt-5.1')
    assert config.model == 'openai/gpt-5.1'
    config = AgentConfig(name='Support Agent', model='anthropic/claude-sonnet-5')
    assert config.model == 'anthropic/claude-sonnet-5'


def test_agent_config_still_normalizes_unknown_models_to_default() -> None:
    config = AgentConfig(name='Support Agent', model='mistral/mistral-large')
    assert config.model == 'gemini-3.5-flash'
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd server && uv run pytest tests/test_agent_config.py -v`
Expected: FAIL — `ImportError: cannot import name 'llm_provider_for_model'`

- [ ] **Step 3: Implement the schema changes**

In `server/app/schemas/agent.py`, replace lines 5–9:

```python
SUPPORTED_MODELS = {
    "gemini-3.5-flash",
    "gemini-3.1-flash-lite",
}
DEFAULT_MODEL = "gemini-3.5-flash"
```

with:

```python
# Gemini models are bare IDs (resolved natively by ADK); all other providers use
# LiteLLM-prefixed IDs ("provider/model"), resolved via ADK's LiteLlm wrapper.
SUPPORTED_MODELS_BY_PROVIDER = {
    "gemini": {
        "gemini-3.5-flash",
        "gemini-3.1-flash-lite",
    },
    "openai": {
        "openai/gpt-5.1",
        "openai/gpt-5-mini",
    },
    "anthropic": {
        "anthropic/claude-sonnet-5",
        "anthropic/claude-haiku-4-5",
        "anthropic/claude-opus-4-8",
    },
}
SUPPORTED_MODELS = set().union(*SUPPORTED_MODELS_BY_PROVIDER.values())
DEFAULT_MODEL = "gemini-3.5-flash"


def llm_provider_for_model(model: str) -> str:
    if "/" in model:
        return model.split("/", 1)[0]
    return "gemini"
```

The existing `normalize_unsupported_model` validator needs no change — it already checks membership in `SUPPORTED_MODELS` and coerces unknown values to `DEFAULT_MODEL`, which is exactly the behavior asserted in step 1.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd server && uv run pytest tests/test_agent_config.py -v`
Expected: PASS (all — including the pre-existing tests in the file)

- [ ] **Step 5: Commit**

```bash
git add server/app/schemas/agent.py server/tests/test_agent_config.py
git commit -m "feat: provider-keyed model whitelist and llm_provider_for_model helper"
```

---

### Task 3: Runtime — per-provider env keys, key gate, conditional planner

**Files:**
- Modify: `server/app/services/pipecat_adk_runtime.py`
- Test: `server/tests/test_voice_runtime.py`

- [ ] **Step 1: Write the failing tests**

Append to `server/tests/test_voice_runtime.py`:

```python
from app.services.pipecat_adk_runtime import require_llm_api_key


def test_build_adk_app_attaches_planner_only_for_gemini() -> None:
    runtime = PipecatAdkRuntime()
    gemini_app = runtime.build_adk_app(AgentConfig(name="G", model="gemini-3.5-flash"))
    assert gemini_app.root_agent.planner is not None

    claude_app = runtime.build_adk_app(
        AgentConfig(name="C", model="anthropic/claude-sonnet-5")
    )
    assert claude_app.root_agent.planner is None
    assert claude_app.root_agent.model == "anthropic/claude-sonnet-5"


def test_require_llm_api_key_raises_when_provider_key_missing(monkeypatch) -> None:
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "openai_api_key", None)
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        require_llm_api_key(AgentConfig(name="O", model="openai/gpt-5.1"))


def test_require_llm_api_key_passes_when_key_present(monkeypatch) -> None:
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "anthropic_api_key", "test-key")
    require_llm_api_key(AgentConfig(name="A", model="anthropic/claude-sonnet-5"))
```

Note: `get_settings()` is `@lru_cache`d, so `monkeypatch.setattr` on the cached instance mutates the same object the code under test sees, and monkeypatch restores the original value after each test.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd server && uv run pytest tests/test_voice_runtime.py -v`
Expected: FAIL — `ImportError: cannot import name 'require_llm_api_key'`

- [ ] **Step 3: Implement the runtime changes**

In `server/app/services/pipecat_adk_runtime.py`:

**(a)** Extend the schema import (lines 15–19) to include the provider helper:

```python
from app.schemas.agent import (
    AgentConfig,
    LEGACY_DEEPGRAM_VOICES,
    SUPPORTED_DEEPGRAM_VOICES,
    llm_provider_for_model,
)
```

**(b)** Add a module-level key map and gate function (after the `logger = ...` line):

```python
# provider -> (Settings attribute, env var the ADK/LiteLLM client reads)
LLM_PROVIDER_KEYS = {
    "gemini": ("gemini_api_key", "GEMINI_API_KEY"),
    "openai": ("openai_api_key", "OPENAI_API_KEY"),
    "anthropic": ("anthropic_api_key", "ANTHROPIC_API_KEY"),
}


def require_llm_api_key(config: AgentConfig) -> None:
    provider = llm_provider_for_model(config.model)
    settings_attr, env_name = LLM_PROVIDER_KEYS[provider]
    if not getattr(get_settings(), settings_attr):
        raise RuntimeError(
            f"{env_name} is required to run model {config.model!r}"
        )
```

**(c)** Replace `configure_google_api_key` (lines 106–110) with a provider-aware version. (Safe to remove the old name entirely: its only callers are inside this class, at `generate_agent_response` and `build_adk_app`, both rewritten in this task — verified with `rg -n "configure_google_api_key"` on 2026-07-17.)

```python
    def configure_provider_env(self, config: AgentConfig) -> None:
        settings = get_settings()
        provider = llm_provider_for_model(config.model)
        if provider == "gemini" and settings.gemini_api_key:
            os.environ.setdefault("GOOGLE_API_KEY", settings.gemini_api_key)
            os.environ.setdefault("GEMINI_API_KEY", settings.gemini_api_key)
        elif provider == "openai" and settings.openai_api_key:
            os.environ.setdefault("OPENAI_API_KEY", settings.openai_api_key)
        elif provider == "anthropic" and settings.anthropic_api_key:
            os.environ.setdefault("ANTHROPIC_API_KEY", settings.anthropic_api_key)
```

**(d)** In `generate_agent_response` (line 50) replace `self.configure_google_api_key()` with `self.configure_provider_env(config)`.

**(e)** In `build_adk_app` (lines 92–104), replace the body:

```python
    def build_adk_app(self, config: AgentConfig) -> App:
        from pipecat_adk import AdkInterruptionPlugin

        self.configure_provider_env(config)
        agent_kwargs: dict[str, Any] = {}
        if llm_provider_for_model(config.model) == "gemini":
            # BuiltInPlanner/ThinkingConfig are Gemini-specific (google.genai types).
            agent_kwargs["planner"] = BuiltInPlanner(
                thinking_config=types.ThinkingConfig(thinking_budget=0),
            )
        agent = Agent(
            name=self._normalize_agent_name(config.name),
            model=config.model,
            instruction=config.instruction,
            **agent_kwargs,
        )
        return App(name="voicelab", root_agent=agent, plugins=[AdkInterruptionPlugin()])
```

**(f)** Delete the `validate_environment` method (lines 28–40) — it is dead code (defined, never called anywhere in `app/` or `tests/`; verified 2026-07-17) and hardcodes the Gemini requirement.

**(g)** Generalize the quota error in `generate_agent_response` (lines 76–82). Replace:

```python
            if "RESOURCE_EXHAUSTED" in message_text or "429" in message_text:
                logger.error("adk quota exhausted session_id=%s", session_id)
                raise RuntimeError(
                    "Gemini quota is exhausted for the configured API key/model. "
                    "Use a key with available quota or switch to a model/project with quota, "
                    "then restart the FastAPI server."
                ) from exc
```

with:

```python
            if "RESOURCE_EXHAUSTED" in message_text or "429" in message_text:
                provider = llm_provider_for_model(config.model)
                logger.error(
                    "adk quota exhausted session_id=%s provider=%s", session_id, provider
                )
                raise RuntimeError(
                    f"The {provider} API quota is exhausted for the configured key/model "
                    f"({config.model}). Use a key with available quota or switch models, "
                    "then restart the FastAPI server."
                ) from exc
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd server && uv run pytest tests/test_voice_runtime.py tests/test_agent_config.py -v`
Expected: PASS (all, including pre-existing `test_build_adk_app_uses_ui_config`)

- [ ] **Step 5: Commit**

```bash
git add server/app/services/pipecat_adk_runtime.py server/tests/test_voice_runtime.py
git commit -m "feat: provider-aware runtime — env keys, key gate, Gemini-only planner"
```

---

### Task 4: Replace the two hard GEMINI_API_KEY gates in routes

**Files:**
- Modify: `server/app/api/routes/test_call.py:83-97`
- Modify: `server/app/services/pipecat_streaming_runtime.py:650-652`
- Test: existing suite (gate logic itself is unit-tested in Task 3)

- [ ] **Step 1: Update the text-chat route**

In `server/app/api/routes/test_call.py`, the current code (lines 83–97) checks the Gemini key before the config is even loaded:

```python
    runtime = PipecatAdkRuntime()
    settings = get_settings()
    if not settings.gemini_api_key:
        raise HTTPException(status_code=400, detail="GEMINI_API_KEY is required for text chat")
```

Replace it with a per-provider check that runs **after** `config` is validated. Move the existing `config = AgentConfig.model_validate(run.agent.config)` line (currently line 97) up to directly after `runtime = PipecatAdkRuntime()`, then gate:

```python
    runtime = PipecatAdkRuntime()
    config = AgentConfig.model_validate(run.agent.config)
    try:
        require_llm_api_key(config)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
```

Add `require_llm_api_key` to the existing import from `app.services.pipecat_adk_runtime`. If `get_settings` / `settings` becomes unused in this function after the edit, remove the local `settings = get_settings()` line (keep the module import if other routes in the file still use it — check with `rg -n "get_settings" server/app/api/routes/test_call.py`).

- [ ] **Step 2: Update the streaming (voice) runtime gate**

In `server/app/services/pipecat_streaming_runtime.py`, replace lines 650–652:

```python
        settings = get_settings()
        if not settings.gemini_api_key:
            raise RuntimeError("GEMINI_API_KEY is required to run a streaming voice test call")
```

with:

```python
        settings = get_settings()
        require_llm_api_key(config)
```

(`settings` is still used further down in `run_websocket` for STT/TTS service construction — keep it.) Add `require_llm_api_key` to the existing import from `app.services.pipecat_adk_runtime` (line 45).

- [ ] **Step 3: Run the full backend checks**

Run: `cd server && uv run ruff check . && uv run pytest -q`
Expected: ruff clean, all tests PASS

- [ ] **Step 4: Commit**

```bash
git add server/app/api/routes/test_call.py server/app/services/pipecat_streaming_runtime.py
git commit -m "feat: per-provider API key gates on text and voice paths"
```

---

### Task 5: Wire `temperature` into the text path (pre-existing gap)

`config.temperature` is currently honored only by the streaming runtime's `LLMSettings`; the `Agent` built in `build_adk_app` ignores it, so the text path always runs at the model default. ADK's `Agent` accepts `generate_content_config: types.GenerateContentConfig`, which ADK maps into the request for both native Gemini and LiteLLM-backed models.

**Files:**
- Modify: `server/app/services/pipecat_adk_runtime.py` (the `build_adk_app` body from Task 3)
- Test: `server/tests/test_voice_runtime.py`

- [ ] **Step 1: Write the failing test**

Append to `server/tests/test_voice_runtime.py`:

```python
def test_build_adk_app_applies_temperature() -> None:
    runtime = PipecatAdkRuntime()
    app = runtime.build_adk_app(
        AgentConfig(name="T", model="gemini-3.5-flash", temperature=0.9)
    )
    assert app.root_agent.generate_content_config.temperature == 0.9
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server && uv run pytest tests/test_voice_runtime.py::test_build_adk_app_applies_temperature -v`
Expected: FAIL — `generate_content_config` is `None`

- [ ] **Step 3: Implement**

In `build_adk_app` (as rewritten in Task 3), add one keyword to the `Agent(...)` call:

```python
        agent = Agent(
            name=self._normalize_agent_name(config.name),
            model=config.model,
            instruction=config.instruction,
            generate_content_config=types.GenerateContentConfig(
                temperature=config.temperature,
            ),
            **agent_kwargs,
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd server && uv run pytest tests/test_voice_runtime.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add server/app/services/pipecat_adk_runtime.py server/tests/test_voice_runtime.py
git commit -m "fix: honor agent temperature in ADK text path"
```

---

### Task 6: End-to-end smoke test + docs

**Files:**
- Modify: `AGENTS.md` (env-var block and provider notes)
- No code changes expected; fixes only if the smoke test surfaces one.

- [ ] **Step 1: Full check run**

Run: `cd server && uv run ruff check . && uv run pytest -q`
Expected: clean / all pass

- [ ] **Step 2: Live text-path smoke test (requires at least one non-Gemini key in `server/.env`)**

If no `OPENAI_API_KEY`/`ANTHROPIC_API_KEY` is available, skip to Step 4 and note the skip in the commit message — the unit tests still cover the wiring; only the provider round-trip goes unverified.

```bash
docker compose up -d postgres
cd server && uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 &
sleep 3
# create an agent with a Claude model
AGENT_ID=$(curl -s -X POST http://localhost:8000/api/agents \
  -H 'content-type: application/json' \
  -d '{"name":"claude-smoke","config":{"name":"claude-smoke","model":"anthropic/claude-haiku-4-5","instruction":"Reply with exactly: PROVIDER OK"}}' \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["id"])')
# start a session and send a text turn
RUN_ID=$(curl -s -X POST http://localhost:8000/api/test-call/session \
  -H 'content-type: application/json' -d "{\"agent_id\":\"$AGENT_ID\"}" \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["run_id"])')
curl -s -X POST "http://localhost:8000/api/test-call/session/$RUN_ID/text" \
  -H 'content-type: application/json' -d '{"message":"hello"}'
```

Expected: JSON response whose assistant text contains `PROVIDER OK`. Repeat with `"model":"openai/gpt-5-mini"` if an OpenAI key is present — **this is also the step that validates the curated OpenAI model IDs**; if the provider returns a model-not-found error, correct the ID in `SUPPORTED_MODELS_BY_PROVIDER` (`server/app/schemas/agent.py`) and in the test from Task 2, and re-run.

Route paths verified against `app/main.py` (`prefix="/api"`) and `test_call.py` (`POST /session` → `TestSessionRead.run_id`, `POST /session/{run_id}/text`) on 2026-07-17.

Kill the uvicorn background process when done: `kill %1`.

- [ ] **Step 3: Voice-path sanity (manual, optional but recommended)**

Start the frontend (`cd client && npm run dev`), open the test-call panel with the `claude-smoke` agent, speak once, and confirm a `transcript.final` → `agent.text` → `audio.output` sequence appears in `trace_events` for the run. This exercises `pipecat_streaming_runtime.run_websocket` with a non-Gemini model end to end.

- [ ] **Step 4: Update AGENTS.md**

In `AGENTS.md`:
- In the "Environment variables" dotenv block, add `OPENAI_API_KEY=` and `ANTHROPIC_API_KEY=` after `GEMINI_API_KEY=`.
- In "Known Issues And Notes", add:

```markdown
- LLM provider is selected per-agent via the model ID: bare `gemini-*` IDs run natively; `openai/...` and `anthropic/...` IDs run through ADK's LiteLLM wrapper and require `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` respectively. Supported IDs live in `SUPPORTED_MODELS_BY_PROVIDER` (`server/app/schemas/agent.py`); unknown IDs are normalized to the default model by the pydantic validator, same as before.
- The frontend model dropdown (`client/src/data/providerOptions.ts`) does not list non-Gemini models yet — use the JSON config editor or the agents API to select them.
```

- [ ] **Step 5: Commit**

```bash
git add AGENTS.md
git commit -m "docs: multi-provider LLM env vars and model-id conventions"
```
