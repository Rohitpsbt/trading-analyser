"""
Entity resolution for buyer→supplier auto-discovery.

The supplier-linkage map (config.LINKAGE_MAP) is hand-curated — that curation IS
the edge, but it can't keep up with every name entering a theme. This module
reads free-text news and resolves company mentions to universe tickers via an
alias map (config.COMPANY_ALIASES), enabling two things:

1. resolve_entities(text): which universe tickers are named in this headline?
   Used to name the SPECIFIC supplier in a linkage hit ("...to HFCL") instead of
   surfacing the whole theme supplier list.
2. discover_suppliers(): for each theme, search supplier-side news and propose
   universe tickers that show up but AREN'T yet mapped — candidate additions to
   LINKAGE_MAP you can review and curate in.

Deliberately dependency-free: alias matching with word boundaries, no NLP/ML.
Precision depends on alias coverage in config.COMPANY_ALIASES.
"""
from __future__ import annotations
import re

import config


def _aliases_for(ticker: str) -> list[str]:
    """All match strings for a ticker: its curated aliases plus the bare ticker."""
    aliases = config.COMPANY_ALIASES.get(ticker, [])
    return sorted({ticker.lower(), *(a.lower() for a in aliases)},
                  key=len, reverse=True)  # longest-first: prefer specific names


def resolve_entities(text: str, universe: list[str] | None = None) -> list[str]:
    """Return the universe tickers whose name/alias appears in `text`
    (case-insensitive, word-boundary matched), in universe order, deduped."""
    if not text:
        return []
    universe = universe if universe is not None else config.UNIVERSE
    hay = text.lower()
    found: list[str] = []
    for ticker in universe:
        for alias in _aliases_for(ticker):
            # boundaries so "kei" doesn't match inside "monkeys", "abb" inside "cabbage"
            if re.search(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", hay):
                found.append(ticker)
                break
    return found


def _theme_buyer_tickers(theme: dict) -> set[str]:
    """Resolve the theme's buyer names to tickers so we can exclude them from
    discovered SUPPLIERS (a buyer named in a headline isn't a new supplier)."""
    out: set[str] = set()
    for buyer in theme.get("buyers", []):
        out.update(resolve_entities(buyer))
    return out


def suppliers_in_text(text: str, theme: dict) -> list[str]:
    """Universe tickers named in `text` that are mapped suppliers for this theme —
    i.e. a curated supplier is *directly* in the news (a strong, specific signal)."""
    mapped = set(theme.get("suppliers", []))
    return [t for t in resolve_entities(text) if t in mapped]


def discover_suppliers(monitor=None, themes: dict | None = None
                       ) -> tuple[dict[str, list[dict]], list[str]]:
    """For each theme, search supplier-side news and resolve universe tickers that
    appear but are NOT already mapped as suppliers (nor the theme's buyers).
    Returns ({theme: [{ticker, headline}]}, errors). These are candidates to
    review and curate into LINKAGE_MAP — auto-discovery, not auto-trust."""
    from catalysts import NewsMonitor  # local import avoids a cycle
    monitor = monitor or NewsMonitor()
    themes = themes or config.LINKAGE_MAP

    discoveries: dict[str, list[dict]] = {}
    errors: list[str] = []
    for theme_name, theme in themes.items():
        keywords = theme.get("buyer_keywords", [])
        mapped = set(theme.get("suppliers", []))
        buyers = _theme_buyer_tickers(theme)
        query = (f'({" OR ".join(keywords)}) (order OR contract OR supply OR award)'
                 if keywords else "order OR contract")
        items, err = monitor.fetch(query, limit=10)
        if err:
            errors.append(f"[{theme_name}] {err}")
            continue
        seen: set[str] = set()
        for it in items:
            for ticker in resolve_entities(it.title):
                if ticker in mapped or ticker in buyers or ticker in seen:
                    continue
                seen.add(ticker)
                discoveries.setdefault(theme_name, []).append(
                    {"ticker": ticker, "headline": it.title})
    return discoveries, errors
