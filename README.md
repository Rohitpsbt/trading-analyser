# Trading Analyser

A decision-support engine for Indian equities (NSE/BSE). It **screens** stocks,
detects **catalysts** via supplier-linkage, drafts a dated, reasoned **thesis**
per name, and logs every call to a **ledger** you grade over time.

> It generates signals **you** review and execute. It does **not** place orders
> and is **not** a discretionary stock-picker. The logic is yours, transparent,
> and auditable.

## Strategy (what this is built for)
- **Thematic catalyst-swing**, weeks-to-months horizon. Not F&O scalping, not
  decade-long buy-and-hold.
- **Core edge — supplier-linkage:** watch *buyer* capex/order/tender signals
  (Reliance, Adani, BharatNet…) and surface the linked *suppliers* before the
  market connects the dots. (Your HFCL ↔ fibre example is the `optical_fibre` theme.)
- **Secondary screen:** fundamental quality, so you ride themes via decent businesses.
- **Credibility flag:** a categorical hype-discount (CREDIBLE / NEUTRAL / CAUTION),
  never a false-precision percentage.
- **Exit discipline > entry:** catalyst trades buy tops without exit rules.

## Free stack (₹0 to build, paper-test, even go live)
| Layer | Free option |
|---|---|
| Market data | yfinance (`RELIANCE.NS`), or `pnsea`/`jugaad-data` (NSE scrapers, fragile) |
| Broker/execution | ICICI **Breeze** or **Upstox** API (free); Zerodha **Kite** (₹500/mo) optional |
| News | **Google News RSS** (built in), plus ET/Moneycontrol/Mint RSS, GDELT |
| Fundamentals | yfinance financials, BSE/NSE filings, concall transcripts |
| LLM thesis | **Groq** (default) · **Gemini** · local **Ollama**; FinBERT/VADER for classical sentiment |
| Backtest/store/host | backtrader/vectorbt · SQLite · local / GitHub Actions / Oracle free VM |

## Setup
```bash
pip install -r requirements.txt
pip install groq           # optional LLM narrative (Groq free tier; default)
cp .env.example .env       # put GROQ_API_KEY / GEMINI_API_KEY here (git-ignored)
```
Without an LLM key it still runs — thesis drafting falls back to an offline
structured template (no narrative, all fields populated). See
[RUNBOOK.md](RUNBOOK.md) for full setup, the `doctor` preflight, and the daily
operating loop.

## Use
```bash
python run.py screen --top 10                 # rank universe on fundamentals
python run.py scan-catalysts                  # supplier-linkage news scan
python run.py thesis HFCL --catalyst "Jio fibre capex" --save
python run.py ledger                          # open calls
python run.py grade 1 --price 512.5 --verdict RIGHT --note "theme played out"
python run.py report                          # forward-track performance
```
Add `--mock` to any data command to run with synthetic data and no network
(useful for testing the plumbing; that's how this was validated in a sandbox).

## Methodology guardrails (read before trusting any number)
- **Point-in-time data trap.** Free fundamentals are *current-only*, so naive
  backtests secretly peek at the future and flatter garbage strategies. This tool
  deliberately leans on **forward paper-tracking** (the ledger) over historical
  backtests. Every call is dated and graded as reality unfolds — that's the real
  validation.
- **Deployment ladder.** Backtest only where data is honest → **paper-trade on
  live data** → tiny live capital (₹5–10k) with hard circuit breakers (max daily
  loss, max position size, max trades/day, kill switch) → scale *only* if live
  matches paper. Note: live API trading via Indian brokers requires a **static IP
  from 1 Apr 2026**.

## Red-team checklist (runs on every thesis)
1. Hidden assumption · 2. Look-ahead · 3. Base rate · 4. Already priced in ·
5. Other side · 6. Survives friction · 7. Regime dependence · 8. Ruin.
Items 4, 6, 8 are computed automatically; the rest are answered by the LLM/you
and stored for audit.

## Module map
```
config.py       universe, supplier-linkage map, thresholds, risk, costs, LLM env
providers.py    MarketDataProvider ABC + YFinanceProvider + MockProvider
screening.py    fundamental screen (transparent per-metric scoring)
catalysts.py    Google News RSS monitor + supplier-linkage detection
credibility.py  categorical management-credibility flag
redteam.py      8-point checklist + automated checks
thesis.py       LLM thesis drafter (+ offline fallback)
ledger.py       SQLite forward-tracking ledger
run.py          CLI orchestrator
```

## Roadmap
- **M1 (this):** screen + linkage + thesis + ledger.
- **M2:** feed real concall guidance history into the credibility flag; add
  RSS sources beyond Google News; entity-resolution for buyer→supplier auto-discovery.
- **M3:** paper-trading loop on a live (free) broker feed with the circuit breakers.
- **M4:** honest backtest harness only where point-in-time data exists.
```
```
