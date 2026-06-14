Project: Trading Analyser — Build Brief
What this is. A decision-support engine for Indian equities (NSE/BSE) that screens stocks, drafts a reasoned thesis per name, monitors for catalysts, and surfaces ranked buy/trim recommendations with full reasoning. A human (Rohit) reviews every recommendation and places all orders manually. The assistant builds the engine and generates signals — it does not place live trades and is not a discretionary stock-picker. Goal is twofold: learn, and generate returns.
Strategy (locked in):

Thematic catalyst swing trading, weeks-to-months horizon. Not F&O scalping; not multi-year buy-and-hold.
Core edge — supplier-linkage detection: track capex announcements, order-book expansions, and tender/contract wins from large buyers (Reliance, Adani, BharatNet, etc.) and map them to their suppliers before the market connects the dots. Reading the demand side early beats reading sentiment about a stock that's already run.
Secondary screen: fundamental quality, so we ride themes via decent businesses, not junk.
LLM-honesty mechanism: a management-credibility flag, not a precise score. Check concrete facts (did management hit the last ~3 years of guidance? did past contract wins actually expand margins, or just pad the order book?) and use them to downweight hype. No false-precision percentages.
Risk: exit discipline and position sizing matter more than entry — catalyst trades buy tops without exit logic. Hard rules to avoid being late / becoming exit liquidity.

Free stack (target cost: ₹0 to build, paper-test, and even go live):

Broker (data + execution): ICICI Direct Breeze API (free) or Upstox API (free). Zerodha Kite Connect (₹500/mo) optional. Static IP becomes mandatory for live API trading from 1 Apr 2026.
Backtest data (no account): yfinance + NSE Python libs (pnsea / jugaad-data / nsepython) — free, though the NSE scrapers are fragile.
News: RSS from ET / Moneycontrol / Mint / Business Standard + BSE & NSE corporate-announcement feeds; Google News RSS; GDELT. Free.
Fundamentals & filings: yfinance financials; BSE/NSE filings; concall transcripts; annual reports. Free.
LLM/analysis: Groq free tier, local Ollama, or Gemini free tier; classical sentiment via FinBERT / VADER. Free.
Backtest libs: backtrader / vectorbt / backtesting.py. Storage: SQLite. Hosting: local / GitHub Actions / Oracle always-free VM. Free.

Methodology guardrails (non-negotiable):

Point-in-time data trap: free fundamentals are current-only, so naive backtests secretly peek at the future (look-ahead + survivorship bias) and will flatter garbage strategies. So lean on forward paper-tracking — every pick gets a dated, written thesis graded as reality plays out — more than on historical backtests.
Deployment ladder: backtest only where data is honest → paper-trade on live data with no money → tiny live capital (₹5–10k) with hard circuit breakers (max daily loss, max position size, max trades/day, kill switch) → scale only if live matches paper.

Red-team every strategy and step through this 8-point checklist before committing code:

Hidden assumption — what must be true that we haven't verified?
Look-ahead — are we using info we wouldn't have had at the decision moment?
Base rate — ignoring the story, how often does this actually work?
Already priced in — by the time we can see the signal, has the market moved?
Other side — who's selling to us, and what do they know?
Survives friction — does the edge survive STT, brokerage, slippage, short-term capital-gains tax?
Regime dependence — does it only work in the current bull/liquidity regime?
Ruin — worst realistic case; can it permanently impair capital?

First milestone: a free-stack Python pipeline — screening-and-thesis engine + thesis-tracking ledger — that screens NSE/BSE stocks on fundamentals and drafts a structured, dated thesis per name for review. Build order: (a) data layer on yfinance + free sources, (b) fundamental screen, (c) supplier-linkage/news monitor, (d) LLM thesis drafter with the credibility flag, (e) SQLite ledger logging each call with reasoning for later grading.