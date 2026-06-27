# MEMORY.md — where we are

Running status of the project. For *why* things are built the way they are, see
[CLAUDE.md](CLAUDE.md). Last updated: **2026-06-15**.

## Status: M1 + hardening + M2 done; M3 started (risk layer)

The engine runs end-to-end on live data, is under git (private repo
`Rohitpsbt/trading-analyser`), and is tested (132 pytest tests). We are in the
**forward paper-tracking** phase per the README's deployment ladder (paper-trade
on live data before any real capital). M2 is in (extra RSS feeds, concall
guidance history, supplier auto-discovery). M3's **risk layer** is in (sizing,
real position/exposure tracking, portfolio-heat circuit breakers, auto-fetched
prices) — deliberately before any broker feed.

## ▶ Next session — start here

1. **Orient:** read this file + [CLAUDE.md](CLAUDE.md) (auto-loaded); the full
   command list is in [RUNBOOK.md](RUNBOOK.md) → "Command reference".
2. **Sanity:** `.venv/bin/python -m pytest` (expect 132 green, no network) and
   `python run.py doctor` (checks keys + live data/news; `.env` holds the keys).
3. **The real next move is *operating*, not coding** — the tool only earns trust
   once the ledger holds graded forward calls. Run the daily loop (RUNBOOK) on
   live data for a stretch: `scan-catalysts`/`discover` → `thesis … --save` →
   `size … --open` → later `close`/`grade` → `report`.
4. **If building instead, in priority order:**
   - (a) Fold a positions/heat summary into `report` (currently `report` only
     covers graded theses; open exposure lives in `positions`). Small, self-contained.
   - (b) Broaden `config.COMPANY_ALIASES` — entity-resolution precision is bounded
     by alias coverage.
   - (c) Per-provider model override (`TA_GEMINI_MODEL`, etc.) — `TA_LLM_MODEL` is
     currently global across providers.
   - (d) Only after the ledger shows an edge: the live broker-feed spike (M3's
     last rung) — Breeze/Upstox, paper first. Note the **static-IP from 1 Apr 2026**
     requirement for Indian broker APIs (see README).
5. **Housekeeping still open:** rotate the **Gemini API key** (was pasted in chat
   earlier — treat as exposed).

## Conventions reminder (don't relearn the hard way)

- Flat layout (no package); run modules with `.venv/bin/python`.
- Secrets/local state are git-ignored: `.env`, `*.db`, `.llm_cache.json`.
  `guidance.json` is **tracked** (curated research). Never commit keys.
- `--mock` = synthetic market data, no network (LLM still runs if a key is set).
- Decision-support only: no code path places an order, by design.

## What's built & verified

- **Full M1 pipeline:** screen → scan-catalysts (supplier-linkage) → thesis →
  ledger → grade → report. Runs in `--mock` and live.
- **Tested:** 132 pytest tests, no network required. Green as of last run.
- **M2 so far:**
  - **Extra RSS feeds** (ET / Moneycontrol / Business Standard) merged + deduped
    with Google News in `scan-catalysts`; `doctor` checks each feed.
  - **Concall guidance history** (`guidance.py` + `run.py guidance`) wired into
    the credibility flag — closes the gap where `assess()` had a guidance hook
    that nothing fed.
  - **Entity resolution + auto-discovery** (`linkage.py` + `run.py discover`):
    alias map resolves news text → tickers; names specific suppliers in hits and
    proposes unmapped suppliers to curate in.
- **M3 so far:**
  - **Risk layer** (`sizing.py` + `run.py size`): conviction-scaled position
    sizing within `max_position_pct`, stop-based capital-at-risk, 2R reference
    target. Decision-support only — never places an order.
  - **Auto-fetch prices**: `grade`/`close` pull the current price when `--price`
    is omitted (via `provider.get_price`).
  - **Real position/exposure tracking** (`positions` table; `run.py positions`,
    `size --open`, `close`): a position = what you actually took (shares/entry/
    stop/linked thesis). `close` realizes capital P&L; `grade` still judges the
    thesis. Circuit breakers now read real positions + portfolio **heat**
    (`max_portfolio_heat_pct`), include the prospective plan, and **block**
    `size --open` unless `--force`.
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
| `5dbc9f9` | M3: real position/exposure tracking + portfolio-heat circuit breakers |
| `3e3f374` | Auto-fetch grade/close price when `--price` omitted |
| `2e79f76` | M3: position sizing + circuit breakers (`size`) |
| `16a1f09` | M2: concall guidance history → credibility + entity resolution/auto-discovery |
| `cb8b55f` | M2: supplementary RSS feeds (ET / Moneycontrol / Business Standard) |
| `5b72786` | Docs cleanup: merge Build.md into README |
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
- [x] **M2:** more RSS sources beyond Google News; buyer→supplier auto-discovery
  (entity resolution); feed real concall guidance history into the credibility flag.
  *(Next for M2: broaden COMPANY_ALIASES coverage; per-provider model override.)*
- [~] **M3:** risk layer (sizing + circuit breakers) **done**; auto-fetch prices
  **done**; real position/exposure tracking + portfolio-heat breakers **done**
  (`positions`/`size --open`/`close`). Still to do — paper-trading loop on a live
  (free) broker feed. *(Next for M3: a `doctor`-style positions/heat summary in
  `report`, or begin the broker-feed spike once the ledger shows an edge.)*
- [ ] **M4:** honest backtest harness only where point-in-time data exists.
