# Runbook — setup & the live "log real calls" loop

How to set up and operate the engine. For *what it is, the strategy, and why*,
see [README.md](README.md).

## One-time setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Optional but recommended — live LLM thesis narrative (pick ONE free tier):
pip install groq                                  # default provider

# Put your keys in a .env file (loaded automatically; git-ignored). Do this once
# and they persist — unlike `export`, which only lasts one terminal session:
cp .env.example .env                              # then edit .env:
#   TA_LLM_PROVIDER=groq
#   GROQ_API_KEY=...                              # from console.groq.com
# anthropic / gemini also supported — the model auto-selects per provider; override
# with TA_LLM_MODEL. Without any key, thesis falls back to an offline template.

# For the second-opinion mode (Groq + Gemini side by side) install BOTH and set
# BOTH keys:
pip install groq google-genai
export GROQ_API_KEY=...  GEMINI_API_KEY=...        # gemini key from aistudio.google.com
```

## Preflight — run before any live session

```bash
python3 run.py doctor
```

Confirms: which LLM provider/model is active and whether its key is set; that
**yfinance** reaches Yahoo (fetches RELIANCE); and that the news feeds work
(**Google News** plus each supplementary RSS feed in `config.NEWS_FEEDS`,
checked individually). If anything says `FAILED`, fix it before trusting live
output — a missing
LLM key silently drops you to the offline template, and a broken news feed
silently disables the entire catalyst edge.

## The daily loop (paper-tracking real calls)

1. **Scan the demand side** — surface suppliers behind live buyer catalysts.
   A mapped supplier named directly in a headline is flagged as a specific signal:
   ```bash
   python run.py scan-catalysts
   ```
   Periodically **auto-discover** universe names appearing in theme news that
   aren't mapped yet, then curate the real ones into `config.LINKAGE_MAP`:
   ```bash
   python run.py discover
   ```
2. **Sanity-screen the universe** (optional, fundamentals view):
   ```bash
   python run.py screen --top 10
   ```
   Keep the **credibility** flag honest by logging concall guidance over time —
   guided-vs-delivered is the strongest credibility input, loaded into the thesis
   automatically once on file (`guidance.json`; see `guidance.example.json`):
   ```bash
   python run.py guidance HFCL --year 2024 --guided "20% rev growth" --delivered "12%" --missed
   python run.py guidance HFCL        # view one ticker; `guidance` alone lists all
   ```
3. **Draft + log a dated thesis** for each candidate. `--save` writes it to the
   ledger for later grading:
   ```bash
   python run.py thesis HFCL --catalyst "Jio fibre capex order" --save
   ```
   **Second opinion** — draft from Groq *and* Gemini, show both, and flag where
   they disagree on conviction/action (agreement corroborates; disagreement is a
   signal to dig deeper). Saves both views as separate ledger rows so `report`
   can later tell you which model calls better:
   ```bash
   python run.py thesis HFCL --catalyst "Jio fibre capex order" --second-opinion --save
   ```
4. **Size anything you intend to act on** — conviction-scaled position within the
   max-position cap, with a stop, capital-at-risk, and circuit-breaker checks
   (open positions + trades/day). Decision-support; it never places an order:
   ```bash
   python run.py size --thesis 1 --account 200000      # pulls symbol/entry/conviction
   python run.py size HFCL --account 200000 --entry 512.50 --conviction HIGH
   ```
5. **Review open calls**:
   ```bash
   python run.py ledger
   ```
6. **Grade as reality unfolds** (days/weeks later) — verdict ∈
   RIGHT | WRONG | EARLY | NOISE. Omit `--price` to auto-fetch the current price
   for the thesis's symbol (pass it explicitly to grade at a specific level):
   ```bash
   python run.py grade 1 --verdict RIGHT --note "theme played out"  # auto-priced
   python run.py grade 1 --price 512.50 --verdict RIGHT             # explicit
   ```
7. **Forward-track performance** (hit rate, P&L, P&L by conviction, and — if you
   use second-opinion — a per-model scoreboard under `by_source`):
   ```bash
   python run.py report
   ```

Add `--mock` to `screen` / `scan-catalysts` / `thesis` / `grade` to exercise the
pipeline with deterministic synthetic data and no network (on `grade`, `--mock`
sources the auto-fetched price from the mock provider).

## LLM cost & rate limits (especially Gemini)

LLM responses are **cached on disk** (`.llm_cache.json`, git-ignored), keyed by
provider + model + the full prompt. Re-drafting the same call returns the cached
answer instead of re-hitting the API — the main defence against free-tier rate
limits. Because the prompt embeds the live price and fundamentals, the cache
invalidates itself naturally when those change. Notes:

- **Gemini is opt-in** — only `--second-opinion` ever calls it. Day-to-day single
  theses use Groq alone, so you rarely touch Gemini's quota.
- A `429 quota exceeded` from Gemini means the **free-tier limit**, not a bad key.
  Space out `--second-opinion` runs, or raise quota/enable billing in
  [Google AI Studio](https://aistudio.google.com). Gemini's model is set in
  `config.DEFAULT_MODELS` (override per provider with `TA_LLM_MODEL`).
- `--fresh` forces a live re-draft (ignores the cached answer); `TA_LLM_CACHE=0`
  disables caching entirely.
- Default Groq model is now `llama-3.3-70b-versatile` (tighter theses); set
  `TA_LLM_MODEL=llama-3.1-8b-instant` in `.env` if you prefer speed.

## Where the data lives

The ledger is a local SQLite file at `trading_analyser.db` (override with
`TA_DB_PATH`). It is **git-ignored** — your real calls stay on your machine.
Back it up yourself; it *is* your track record.

## Tests

```bash
python -m pytest        # 121 tests, no network required
```

## Deployment ladder (don't skip steps — from the README)

Paper-track on live data until the ledger shows the model actually works →
tiny live capital (₹5–10k) with hard stops/circuit breakers → scale **only** if
live results match paper. There is deliberately no order-placement code: this is
decision-support; you review and execute.

## Known follow-ups (not blockers)

- **Universe hygiene:** Curating the universe + linkage map is the real edge;
  thin or 404ing symbols are handled gracefully by the screen but add noise.
- **Roadmap M2–M4** (more RSS sources, buyer→supplier auto-discovery, concall
  guidance history, paper-trading automation, point-in-time backtest) — see the
  README roadmap. Foundation comes first.
