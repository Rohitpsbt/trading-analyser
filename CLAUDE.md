# CLAUDE.md — building decisions & conventions

Decision-support engine for Indian equities (NSE/BSE): screen → catalyst /
supplier-linkage → credibility flag → red-team → LLM thesis → graded SQLite
ledger. It generates signals a human reviews and executes; it never places
orders. See [README.md](README.md) for the product & strategy,
[RUNBOOK.md](RUNBOOK.md) for how to operate it, and [MEMORY.md](MEMORY.md) for
current status / what we're working on.

## How to work in this repo

- **Layout is flat** (no package): `run.py` uses flat imports (`import config`,
  `from providers import ...`), so every module lives at the project root. Don't
  move them into a subpackage without updating the imports.
- **Environment:** Python venv at `.venv/`. Run things with `.venv/bin/python`.
  - Run app: `python run.py <screen|scan-catalysts|thesis|ledger|grade|report|doctor>`
  - Tests: `python -m pytest` (config in [pytest.ini](pytest.ini); flat layout is
    handled via `pythonpath = .`). No network needed — tests use `MockProvider`
    and monkeypatch the LLM.
  - `python run.py doctor` is the preflight (LLM key/model + live data/news reachability).
- **Secrets & local state never get committed.** `.env`, `*.db`, and
  `.llm_cache.json` are git-ignored. Keys load from `.env` (see `.env.example`).
- **Two data modes:** add `--mock` to data commands for deterministic synthetic
  data; omit it for live yfinance + Google News.

## Key design decisions (and why)

- **Provider abstraction** ([providers.py](providers.py)): everything talks to the
  `MarketDataProvider` interface, so yfinance can be swapped for Breeze/Upstox
  later without touching screening/catalyst/thesis logic. `MockProvider` gives a
  zero-network, deterministic pipeline for tests and demos.
- **Transparent per-metric scoring** ([screening.py](screening.py)): the screen
  returns a per-check breakdown, never a single opaque number you can't interrogate.
  `passed` requires revenue-growth ∧ ROE ∧ debt (margin is scored but not gating).
- **Categorical credibility flag** ([credibility.py](credibility.py)):
  CREDIBLE / NEUTRAL / CAUTION / INSUFFICIENT_DATA with concrete reasons — a
  deliberate refusal to manufacture a false-precision percentage. Guidance-vs-
  delivery history is the strongest input when supplied.
- **Red-team as a system** ([redteam.py](redteam.py)): 8-point checklist; the
  checkable items (already-priced-in, survives-friction, ruin) are computed,
  the rest are posed to the LLM/human and stored for audit.
- **Forward paper-tracking over backtests** ([ledger.py](ledger.py)): free
  fundamentals are current-only, so naive backtests peek at the future. The
  ledger logs every dated call with full reasoning and grades it as reality
  unfolds — that's the real validation. One call = one gradeable row.
- **Thesis always completes** ([thesis.py](thesis.py)): if no LLM key/network,
  drafting falls back to a deterministic offline template (no narrative, every
  field populated) so the pipeline never breaks.

### LLM layer decisions
- **Per-provider model resolution** (`config.model_for`): `TA_LLM_MODEL` is an
  override; otherwise each provider gets its own default from `DEFAULT_MODELS`.
  Fixes an earlier bug where a Groq model id was sent to Anthropic/Gemini.
- **Defaults:** Groq `llama-3.3-70b-versatile` (tighter theses than 8b); Gemini
  `gemini-2.5-flash` (free-tier enabled — `gemini-2.0-flash` returns `limit: 0`
  / no free quota on new keys); Anthropic `claude-haiku-4-5`.
- **Second opinion** (`thesis --second-opinion`): draft the *same* skeptical
  prompt through Groq **and** Gemini, show both, and flag disagreement on
  conviction/action. Both views are saved as **separate ledger rows** tagged by
  `source`, so `report` can score which model calls better over time (`by_source`).
  Divergence is treated as a signal to dig deeper, not a green light.
- **Response caching** (`config.LLM_CACHE`, `.llm_cache.json`): cache keyed by
  (provider, model, full prompt) so re-drafting the same call doesn't re-hit the
  API — the main defence against free-tier rate limits (esp. Gemini, which is
  opt-in via second-opinion). The prompt embeds live price/fundamentals, so the
  key self-invalidates when inputs change. `--fresh` bypasses; `TA_LLM_CACHE=0`
  disables.
- **Output hardening** ([thesis.py](thesis.py)): small models return loose shapes,
  so `_clean_text` flattens dict/list fields to prose and `_norm_action` /
  `_norm_conviction` constrain values to the allowed sets.
- **Gemini uses the current `google-genai` SDK** (the old `google-generativeai`
  is end-of-life).
- **`.env` loaded with a tiny built-in parser** (`config._load_dotenv`), no
  dependency — keeps the "₹0 stack" honest. Real env vars always win.

### Infra fixes
- **News SSL** ([catalysts.py](catalysts.py)): use certifi's CA bundle for the
  Google News fetch — stock macOS Python otherwise throws
  `CERTIFICATE_VERIFY_FAILED` and silently disables the whole catalyst feature.

## Gotchas

- The ledger DB is your real track record — it's git-ignored on purpose; back it
  up yourself.
- `TA_LLM_MODEL` applies to whichever provider is active — there's no per-provider
  model override yet, so don't set it globally if you switch providers often.
