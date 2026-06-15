"""
Concall guidance history store — the strongest credibility input.

`credibility.assess()` treats guided-vs-delivered history as the dominant signal
(serial promise-keepers vs chronic over-promisers), but the free stack has no
structured concall API. So you curate it: after each result/concall, log what
management GUIDED for a year and what they actually DELIVERED, and whether they
met it. This module is the small file-backed store + loader behind that.

Format on disk (config.GUIDANCE_PATH), a JSON object keyed by ticker:
    {
      "HFCL": [
        {"year": 2024, "guided": "20% revenue growth", "delivered": "12%", "met": false},
        {"year": 2023, "guided": "EBITDA margin ~15%", "delivered": "14.8%", "met": true}
      ]
    }
"""
from __future__ import annotations
import json

import config


def _load() -> dict:
    try:
        with open(config.GUIDANCE_PATH) as fh:
            data = json.load(fh)
            return data if isinstance(data, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save(data: dict) -> None:
    with open(config.GUIDANCE_PATH, "w") as fh:
        json.dump(data, fh, indent=2, sort_keys=True)


def load_guidance(symbol: str) -> list[dict]:
    """Return the guidance history for a ticker (newest year first), or []."""
    entries = _load().get(symbol.upper(), [])
    return sorted(entries, key=lambda e: e.get("year", 0), reverse=True)


def add_guidance(symbol: str, year: int, guided: str, delivered: str,
                 met: bool) -> list[dict]:
    """Add (or replace, by year) one guided-vs-delivered record for a ticker.
    Returns the ticker's updated history. Creating the file on first write."""
    symbol = symbol.upper()
    data = _load()
    entries = [e for e in data.get(symbol, []) if e.get("year") != year]
    entries.append({"year": int(year), "guided": guided,
                    "delivered": delivered, "met": bool(met)})
    entries.sort(key=lambda e: e.get("year", 0), reverse=True)
    data[symbol] = entries
    _save(data)
    return entries


def all_guidance() -> dict:
    """The whole store, ticker -> history (each newest-first)."""
    return {sym: sorted(hist, key=lambda e: e.get("year", 0), reverse=True)
            for sym, hist in _load().items()}


def met_rate(symbol: str) -> float | None:
    """Fraction of logged years where guidance was met, or None if no history."""
    hist = load_guidance(symbol)
    if not hist:
        return None
    return sum(1 for e in hist if e.get("met")) / len(hist)
