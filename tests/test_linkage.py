"""
Tests for linkage.py — entity resolution (text -> universe tickers) and
buyer->supplier auto-discovery. News fetches are stubbed; no network.
"""
from __future__ import annotations

import pytest

import linkage
from catalysts import NewsItem


# A small, self-contained alias map + universe so tests don't depend on the
# real config contents.
_UNIVERSE = ["HFCL", "STLTECH", "RELIANCE", "POLYCAB", "KEI"]
_ALIASES = {
    "HFCL": ["hfcl", "himachal futuristic"],
    "STLTECH": ["sterlite technologies", "stl"],
    "RELIANCE": ["reliance jio", "jio"],
    "POLYCAB": ["polycab"],
    "KEI": ["kei industries"],
}


@pytest.fixture(autouse=True)
def patch_config(monkeypatch):
    monkeypatch.setattr("config.UNIVERSE", _UNIVERSE)
    monkeypatch.setattr("config.COMPANY_ALIASES", _ALIASES)


# ---------------------------------------------------------------------------
# resolve_entities
# ---------------------------------------------------------------------------

class TestResolveEntities:
    def test_resolves_alias_to_ticker(self):
        assert linkage.resolve_entities("Sterlite Technologies bags order") == ["STLTECH"]

    def test_resolves_bare_ticker(self):
        assert "HFCL" in linkage.resolve_entities("HFCL wins fibre deal")

    def test_case_insensitive(self):
        assert linkage.resolve_entities("himachal futuristic news") == ["HFCL"]

    def test_multiple_entities_in_universe_order(self):
        text = "Polycab and HFCL both named; Reliance Jio too"
        # universe order is HFCL, STLTECH, RELIANCE, POLYCAB, KEI
        assert linkage.resolve_entities(text) == ["HFCL", "RELIANCE", "POLYCAB"]

    def test_no_match_returns_empty(self):
        assert linkage.resolve_entities("Some unrelated company news") == []

    def test_empty_text(self):
        assert linkage.resolve_entities("") == []

    def test_word_boundary_prevents_substring_false_positive(self):
        # "stl" should NOT match inside "wrestling" (preceded by a letter)
        assert "STLTECH" not in linkage.resolve_entities("a wrestling match today")

    def test_dedup_when_two_aliases_hit(self):
        # both "reliance jio" and "jio" present → RELIANCE once
        assert linkage.resolve_entities("Reliance Jio, jio jio") == ["RELIANCE"]

    def test_respects_explicit_universe_arg(self):
        out = linkage.resolve_entities("HFCL and Polycab", universe=["POLYCAB"])
        assert out == ["POLYCAB"]


# ---------------------------------------------------------------------------
# suppliers_in_text
# ---------------------------------------------------------------------------

class TestSuppliersInText:
    _THEME = {
        "buyers": ["Reliance Jio"],
        "suppliers": ["HFCL", "STLTECH"],
    }

    def test_named_mapped_supplier_returned(self):
        out = linkage.suppliers_in_text("Reliance Jio awards order to HFCL", self._THEME)
        assert out == ["HFCL"]

    def test_unmapped_entity_excluded(self):
        # POLYCAB is in universe but not a supplier of this theme
        out = linkage.suppliers_in_text("Polycab wins unrelated order", self._THEME)
        assert out == []

    def test_buyer_not_counted_as_supplier(self):
        out = linkage.suppliers_in_text("Reliance Jio announces capex", self._THEME)
        assert out == []


# ---------------------------------------------------------------------------
# discover_suppliers
# ---------------------------------------------------------------------------

class _StubMonitor:
    def __init__(self, items_by_call, err=None):
        self._items = items_by_call
        self._err = err
        self.calls = []

    def fetch(self, query, limit=10):
        self.calls.append(query)
        if self._err:
            return [], self._err
        return self._items, None


class TestDiscoverSuppliers:
    _THEMES = {
        "optical_fibre": {
            "buyers": ["Reliance Jio"],
            "buyer_keywords": ["fibre"],
            "suppliers": ["HFCL"],   # STLTECH deliberately NOT mapped yet
        }
    }

    def test_discovers_unmapped_supplier(self):
        items = [NewsItem(
            title="Sterlite Technologies bags large fibre supply contract",
            source="ET", published="", link="")]
        monitor = _StubMonitor(items)
        found, errors = linkage.discover_suppliers(monitor=monitor, themes=self._THEMES)
        assert errors == []
        assert "optical_fibre" in found
        assert found["optical_fibre"][0]["ticker"] == "STLTECH"

    def test_already_mapped_supplier_not_rediscovered(self):
        items = [NewsItem(title="HFCL wins fibre order", source="ET",
                          published="", link="")]
        monitor = _StubMonitor(items)
        found, _ = linkage.discover_suppliers(monitor=monitor, themes=self._THEMES)
        assert found == {}

    def test_buyer_not_discovered_as_supplier(self):
        items = [NewsItem(title="Reliance Jio fibre capex order announced",
                          source="ET", published="", link="")]
        monitor = _StubMonitor(items)
        found, _ = linkage.discover_suppliers(monitor=monitor, themes=self._THEMES)
        assert found == {}

    def test_fetch_error_collected(self):
        monitor = _StubMonitor([], err="network down")
        found, errors = linkage.discover_suppliers(monitor=monitor, themes=self._THEMES)
        assert found == {}
        assert len(errors) == 1
        assert "network down" in errors[0]

    def test_dedup_same_ticker_across_headlines(self):
        items = [
            NewsItem(title="Sterlite Technologies bags fibre order", source="ET",
                     published="", link=""),
            NewsItem(title="STL wins another fibre supply deal", source="MC",
                     published="", link=""),
        ]
        monitor = _StubMonitor(items)
        found, _ = linkage.discover_suppliers(monitor=monitor, themes=self._THEMES)
        tickers = [d["ticker"] for d in found["optical_fibre"]]
        assert tickers.count("STLTECH") == 1
