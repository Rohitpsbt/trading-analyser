# Runbook — setup & the live "log real calls" loop

How to set up and operate the engine. For *what it is and why*, see
[README.md](README.md); for the original build brief / strategy spec, see
[Build.md](Build.md).

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
pip install groq google-generativeai
export GROQ_API_KEY=...  GEMINI_API_KEY=...        # gemini key from aistudio.google.com
```

## Preflight — run before any live session

```bash
python3 run.py doctor
```

Confirms: which LLM provider/model is active and whether its key is set; that
**yfinance** reaches Yahoo (fetches RELIANCE); and that the **Google News** feed
works. If anything says `FAILED`, fix it before trusting live output — a missing
LLM key silently drops you to the offline template, and a broken news feed
silently disables the entire catalyst edge.

## The daily loop (paper-tracking real calls)

1. **Scan the demand side** — surface suppliers behind live buyer catalysts:
   ```bash
   python run.py scan-catalysts
   ```
2. **Sanity-screen the universe** (optional, fundamentals view):
   ```bash
   python run.py screen --top 10
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
4. **Review open calls**:
   ```bash
   python run.py ledger
   ```
5. **Grade as reality unfolds** (days/weeks later) — verdict ∈
   RIGHT | WRONG | EARLY | NOISE:
   ```bash
   python run.py grade 1 --price 512.50 --verdict RIGHT --note "theme played out"
   ```
6. **Forward-track performance** (hit rate, P&L, P&L by conviction, and — if you
   use second-opinion — a per-model scoreboard under `by_source`):
   ```bash
   python run.py report
   ```

Add `--mock` to `screen` / `scan-catalysts` / `thesis` to exercise the pipeline
with deterministic synthetic data and no network.

## Where the data lives

The ledger is a local SQLite file at `trading_analyser.db` (override with
`TA_DB_PATH`). It is **git-ignored** — your real calls stay on your machine.
Back it up yourself; it *is* your track record.

## Tests

```bash
python -m pytest        # 39 tests, no network required
```

## Deployment ladder (don't skip steps — from the README)

Paper-track on live data until the ledger shows the model actually works →
tiny live capital (₹5–10k) with hard stops/circuit breakers → scale **only** if
live results match paper. There is deliberately no order-placement code: this is
decision-support; you review and execute.

## Known follow-ups (not blockers)

- **Universe hygiene:** `config.UNIVERSE` has `TATAMOTORS`, which 404s on Yahoo
  after the Tata Motors demerger. The screen skips it gracefully; update the
  symbol when convenient. Curating the universe + linkage map is the real edge.
- **Roadmap M2–M4** (more RSS sources, buyer→supplier auto-discovery, concall
  guidance history, paper-trading automation, point-in-time backtest) — see the
  README roadmap. Foundation comes first.
