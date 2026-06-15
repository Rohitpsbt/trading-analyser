"""
Tests for guidance.py — the concall guided-vs-delivered store + its effect on
credibility.assess(). Uses a temp file so no real guidance.json is touched.
"""
from __future__ import annotations
import json

import pytest

import guidance
from providers import Fundamentals
from credibility import assess, Credibility


@pytest.fixture
def temp_store(tmp_path, monkeypatch):
    path = tmp_path / "guidance.json"
    monkeypatch.setattr("config.GUIDANCE_PATH", str(path))
    return path


# ---------------------------------------------------------------------------
# load / add round-trip
# ---------------------------------------------------------------------------

class TestStore:
    def test_load_missing_file_returns_empty(self, temp_store):
        assert guidance.load_guidance("HFCL") == []
        assert guidance.all_guidance() == {}

    def test_add_then_load(self, temp_store):
        guidance.add_guidance("hfcl", 2024, "20% growth", "12%", met=False)
        hist = guidance.load_guidance("HFCL")  # case-insensitive
        assert len(hist) == 1
        assert hist[0]["year"] == 2024
        assert hist[0]["met"] is False

    def test_add_persists_to_disk(self, temp_store):
        guidance.add_guidance("HFCL", 2024, "g", "d", met=True)
        on_disk = json.loads(temp_store.read_text())
        assert "HFCL" in on_disk
        assert on_disk["HFCL"][0]["met"] is True

    def test_add_replaces_same_year(self, temp_store):
        guidance.add_guidance("HFCL", 2024, "first", "x", met=False)
        guidance.add_guidance("HFCL", 2024, "second", "y", met=True)
        hist = guidance.load_guidance("HFCL")
        assert len(hist) == 1
        assert hist[0]["guided"] == "second"
        assert hist[0]["met"] is True

    def test_history_sorted_newest_first(self, temp_store):
        guidance.add_guidance("HFCL", 2022, "a", "x", met=True)
        guidance.add_guidance("HFCL", 2024, "b", "y", met=True)
        guidance.add_guidance("HFCL", 2023, "c", "z", met=False)
        years = [e["year"] for e in guidance.load_guidance("HFCL")]
        assert years == [2024, 2023, 2022]

    def test_met_rate(self, temp_store):
        assert guidance.met_rate("HFCL") is None
        guidance.add_guidance("HFCL", 2024, "a", "x", met=True)
        guidance.add_guidance("HFCL", 2023, "b", "y", met=False)
        assert guidance.met_rate("HFCL") == 0.5

    def test_corrupt_file_treated_as_empty(self, temp_store):
        temp_store.write_text("{not valid json")
        assert guidance.load_guidance("HFCL") == []

    def test_multiple_tickers_isolated(self, temp_store):
        guidance.add_guidance("HFCL", 2024, "a", "x", met=True)
        guidance.add_guidance("STLTECH", 2024, "b", "y", met=False)
        assert len(guidance.load_guidance("HFCL")) == 1
        assert len(guidance.load_guidance("STLTECH")) == 1
        assert set(guidance.all_guidance()) == {"HFCL", "STLTECH"}


# ---------------------------------------------------------------------------
# guidance flowing into credibility.assess()
# ---------------------------------------------------------------------------

class TestGuidanceAffectsCredibility:
    def _neutral_fundamentals(self):
        # No hard tells → without guidance this is NEUTRAL/INSUFFICIENT.
        return Fundamentals(symbol="HFCL", name="HFCL")

    def test_strong_track_record_pushes_credible(self):
        f = self._neutral_fundamentals()
        gh = [
            {"year": 2024, "guided": "x", "delivered": "y", "met": True},
            {"year": 2023, "guided": "x", "delivered": "y", "met": True},
            {"year": 2022, "guided": "x", "delivered": "y", "met": True},
        ]
        res = assess(f, guidance_history=gh)
        assert res.flag == Credibility.CREDIBLE
        assert any("hit guidance" in r for r in res.reasons)

    def test_chronic_misses_push_caution(self):
        f = self._neutral_fundamentals()
        gh = [
            {"year": 2024, "guided": "x", "delivered": "y", "met": False},
            {"year": 2023, "guided": "x", "delivered": "y", "met": False},
            {"year": 2022, "guided": "x", "delivered": "y", "met": True},
        ]
        res = assess(f, guidance_history=gh)
        assert res.flag == Credibility.CAUTION
        assert any("missed guidance" in r for r in res.reasons)

    def test_no_guidance_is_insufficient_when_no_other_signals(self):
        res = assess(self._neutral_fundamentals(), guidance_history=[])
        assert res.flag == Credibility.INSUFFICIENT

    def test_guidance_history_carried_on_result(self):
        gh = [{"year": 2024, "guided": "x", "delivered": "y", "met": True}]
        res = assess(self._neutral_fundamentals(), guidance_history=gh)
        assert res.guidance_history == gh
