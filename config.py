"""
Central configuration for Trading Analyser.

Everything here is meant to be edited by you. The tickers below are STRUCTURE
EXAMPLES that demonstrate how the supplier-linkage map and universe are wired —
they are not buy recommendations. Replace/extend them with your own coverage.
"""
from __future__ import annotations
import os


def _load_dotenv(path: str | None = None) -> None:
    """Minimal .env loader (no dependency). Reads KEY=VALUE lines from a .env in
    the project root so API keys persist in a file instead of a shell session.
    Real environment variables always win (we never overwrite them). .env is
    git-ignored — keep your keys out of version control."""
    path = path or os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    try:
        with open(path) as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))
    except FileNotFoundError:
        pass


# Load .env BEFORE anything below reads os.getenv (LLM keys, DB_PATH, ...).
_load_dotenv()

# ---------------------------------------------------------------------------
# Data source
# ---------------------------------------------------------------------------
# yfinance uses Yahoo suffixes: ".NS" for NSE, ".BO" for BSE.
EXCHANGE_SUFFIX = ".NS"

# Starting universe to screen. Keep this liquid; thin stocks make catalyst
# trading a trap (you become the exit liquidity). Edit freely.
UNIVERSE = [
    "RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK", "BHARTIARTL",
    "LT", "SBIN", "ITC", "HINDUNILVR", "BAJFINANCE", "MARUTI",
    "SUNPHARMA", "TATAMOTORS", "TATASTEEL", "POWERGRID", "NTPC",
    "ADANIPORTS", "ADANIENT", "HFCL", "STLTECH", "KEC", "KALPATPOWR",
    "CGPOWER", "BHEL", "SIEMENS", "ABB", "POLYCAB", "KEI", "DIXON",
]

# ---------------------------------------------------------------------------
# Supplier-linkage map — THE CORE EDGE
# ---------------------------------------------------------------------------
# Idea: read the *demand side* early. When a large buyer signals capex / orders /
# tenders, the linked suppliers often move before the market connects the dots.
# Each theme lists the big buyers whose news we watch, and the candidate
# suppliers to surface when a buyer catalyst fires.
#
# These are illustrative linkages to show the structure (your HFCL/fibre example
# is the 'optical_fibre' theme). Curate your own — the edge is in the mapping.
LINKAGE_MAP = {
    "optical_fibre": {
        "buyers": ["Reliance Jio", "Bharti Airtel", "BharatNet", "Vodafone Idea"],
        "buyer_keywords": ["fibre", "fiber", "FTTH", "broadband rollout",
                           "5G capex", "BharatNet", "tower"],
        "suppliers": ["HFCL", "STLTECH", "BIRLACABLE", "PARAMOUNT"],
    },
    "data_centre": {
        "buyers": ["Reliance", "Adani", "Hiranandani", "Microsoft", "Google"],
        "buyer_keywords": ["data center", "data centre", "hyperscale",
                           "cloud capex", "server farm"],
        "suppliers": ["CGPOWER", "ABB", "SIEMENS", "POLYCAB", "KEI"],
    },
    "power_transmission": {
        "buyers": ["Power Grid", "Adani Energy", "state discoms", "NTPC"],
        "buyer_keywords": ["transmission", "grid", "substation", "electrification",
                           "capex", "tender awarded"],
        "suppliers": ["KEC", "KALPATPOWR", "CGPOWER", "BHEL", "SIEMENS"],
    },
    "solar_renewables": {
        "buyers": ["Adani Green", "ReNew", "NTPC Green", "Tata Power"],
        "buyer_keywords": ["solar", "module", "PLI", "renewable capacity",
                           "GW commissioned", "cell manufacturing"],
        "suppliers": ["POLYCAB", "KEI", "CGPOWER"],
    },
}

# ---------------------------------------------------------------------------
# Fundamental screen thresholds (secondary screen — ride themes via OK businesses)
# ---------------------------------------------------------------------------
SCREEN = {
    "min_revenue_growth": 0.10,     # YoY
    "min_roe": 0.12,
    "max_debt_to_equity": 1.5,
    "min_operating_margin": 0.08,
    # Red-team relevant: we WANT margin expansion, not just revenue. A company
    # whose revenue grows while margins compress is often padding the order book
    # with low-margin work — exactly the 'narrative vs reality' trap.
    "reward_margin_expansion": True,
}

# ---------------------------------------------------------------------------
# Risk / position sizing (exit discipline > entry for catalyst trades)
# ---------------------------------------------------------------------------
RISK = {
    "max_position_pct": 0.10,       # no single name > 10% of book
    "default_stop_pct": 0.12,       # initial stop below entry
    "trail_after_gain_pct": 0.15,   # start trailing once up this much
    # 'Already running' guard: if a name is up more than this over the lookback,
    # the catalyst is likely already priced — flag, don't chase.
    "already_run_lookback_days": 30,
    "already_run_threshold_pct": 0.25,
}

# ---------------------------------------------------------------------------
# Costs (so 'survives friction' in the red-team is computed, not guessed)
# ---------------------------------------------------------------------------
COSTS = {
    "brokerage_pct": 0.0003,        # ~0.03% per side (delivery; many are ₹0)
    "stt_pct": 0.001,               # STT on delivery sell
    "slippage_pct": 0.0015,         # assumed slippage per side
    "stcg_tax_pct": 0.20,           # short-term capital gains on listed equity
}

# ---------------------------------------------------------------------------
# LLM config — Groq (free tier) by default; Gemini / Anthropic also supported.
# Set the matching env var. If none is set, thesis drafting falls back to an
# offline structured template (no narrative, but the pipeline still runs).
# ---------------------------------------------------------------------------
# Per-provider default model, used when TA_LLM_MODEL is NOT explicitly set.
# (Previously a single Groq model id was the default for every provider, so
# TA_LLM_PROVIDER=anthropic/gemini without an explicit model sent an invalid
# model id and the call failed.) Override any of these with TA_LLM_MODEL.
DEFAULT_MODELS = {
    "groq": "llama-3.1-8b-instant",   # free tier; Groq rotates models — bump to
                                      # llama-3.3-70b-versatile for a stronger draft
    "anthropic": "claude-haiku-4-5",  # cheap & capable; claude-sonnet-4-6 for deeper analysis
    "gemini": "gemini-2.0-flash",     # Gemini free tier
}

LLM = {
    "provider": os.getenv("TA_LLM_PROVIDER", "groq"),  # groq | gemini | anthropic | none
    "model": os.getenv("TA_LLM_MODEL"),                # None -> per-provider default below
    "groq_api_key": os.getenv("GROQ_API_KEY"),
    "gemini_api_key": os.getenv("GEMINI_API_KEY"),
    "anthropic_api_key": os.getenv("ANTHROPIC_API_KEY"),
}


def model_for(provider: str) -> str:
    """Resolve the model to use: explicit TA_LLM_MODEL override, else the
    default for this provider. Avoids sending a Groq model id to Anthropic/Gemini."""
    return LLM.get("model") or DEFAULT_MODELS.get(provider, "")

DB_PATH = os.getenv("TA_DB_PATH", "trading_analyser.db")


def ticker_to_yf(symbol: str) -> str:
    """RELIANCE -> RELIANCE.NS"""
    return symbol if "." in symbol else f"{symbol}{EXCHANGE_SUFFIX}"
