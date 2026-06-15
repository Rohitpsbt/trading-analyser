# MEMORY.md — where we are

Running status of the project. For *why* things are built the way they are, see
[CLAUDE.md](CLAUDE.md). Last updated: **2026-06-15**.

## Status: M1 complete + foundation/LLM hardening done

The engine runs end-to-end on live data, is under git, and is tested. We are in
the **forward paper-tracking** phase per the README's deployment ladder
(paper-trade on live data before any real capital).

## What's built & verified

- **Full M1 pipeline:** screen → scan-catalysts (supplier-linkage) → thesis →
  ledger → grade → report. Runs in `--mock` and live.
- **Tested:** 56 pytest tests, no network required. Green as of last run.
- **Verified live (2026-06-14/15):**
  - yfinance: real fundamentals (e.g. RELIANCE, HFCL), 100% completeness on majors.
  - Google News supplier-linkage: real hits surfacing (NTPC power capex, NTPC
    Green solar, etc.). (SSL cert bug that previously disabled this is fixed.)
  - Groq thesis (`llama-3.3-70b-versatile`): clean narrated output.
  - **Second opinion live:** Groq + Gemini (`gemini-2.5-flash`, new SDK) both
    draft and disagreements are flagged.

## Current configuration

- Default provider: **Groq** (`TA_LLM_PROVIDER=groq`). Keys live in `.env`
  (git-ignored): `GROQ_API_KEY`, `GEMINI_API_KEY`.
- Models: Groq `llama-3.3-70b-versatile`, Gemini `gemini-2.5-flash`,
  Anthropic `claude-haiku-4-5`. Override with `TA_LLM_MODEL`.
- LLM response caching ON (`.llm_cache.json`). Gemini is opt-in (second-opinion only).

## Commit history (newest first)

| Commit | What |
|---|---|
| `ad606d6` | Port Gemini to `google-genai` SDK; default `gemini-2.5-flash` |
| `d0ba4d4` | Harden LLM output (clean text, constrain action/conviction) + response cache |
| `5173712` | Load API keys from `.env` (no dependency) |
| `9cde66c` | Second-opinion mode (Groq + Gemini, flag disagreement, per-source `report`) |
| `f4c3676` | RUNBOOK + commit the build brief |
| `607393d` | Per-provider LLM model fix, news SSL fix, `doctor` preflight |
| `caa6f7a` | pytest suite |
| `a0e0443` | M1 baseline (extracted from zip into runnable flat layout) |

## Open follow-ups / next steps

**Housekeeping**
- [ ] **Rotate the Gemini API key** — it was pasted in chat earlier, so treat it
  as exposed. (Groq key already rotated.)
- [x] **Universe hygiene:** Removed stale `TATAMOTORS` (404s post-demerger).
- [x] Removed redundant `trading_analyser.zip` and merged `Build.md` (the build
  brief) into [README.md](README.md) — docs are now README / RUNBOOK / CLAUDE / MEMORY.

**Possible enhancements**
- [ ] Per-provider model override (e.g. `TA_GEMINI_MODEL`) so `TA_LLM_MODEL`
  doesn't apply to whichever provider is active. Useful once leaning on
  second-opinion with different model tiers.
- [ ] Mind Gemini free-tier caps (per-minute + per-day on `gemini-2.5-flash`);
  cache helps, but space out `--second-opinion` runs. `gemini-2.5-flash-lite`
  has higher free limits if needed.

**Roadmap (from README)**
- [ ] **M2:** more RSS sources beyond Google News; buyer→supplier auto-discovery
  (entity resolution); feed real concall guidance history into the credibility flag.
- [ ] **M3:** paper-trading loop on a live broker feed with circuit breakers.
- [ ] **M4:** honest backtest harness only where point-in-time data exists.
