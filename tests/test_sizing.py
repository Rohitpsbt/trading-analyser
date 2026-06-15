"""
Tests for sizing.py — position sizing math and ledger circuit breakers.
Sizing tests are pure (no DB); circuit-breaker tests use a temp ledger.
"""
from __future__ import annotations
from datetime import date

import pytest

import config
from sizing import plan_position, circuit_breakers, PositionPlan
from ledger import Ledger


# ---------------------------------------------------------------------------
# plan_position
# ---------------------------------------------------------------------------

class TestPlanPosition:
    def test_basic_shares_within_cap(self):
        # MEDIUM = 0.7 of 10% cap = 7% of 100000 = 7000 / 100 entry = 70 shares
        p = plan_position("HFCL", 100_000, 100.0, "MEDIUM")
        assert p.shares == 70
        assert p.position_value == 7000.0
        assert p.position_pct == pytest.approx(0.07)

    def test_high_conviction_uses_full_cap(self):
        p = plan_position("HFCL", 100_000, 100.0, "HIGH")
        # 1.0 * 10% = 10% = 10000 / 100 = 100 shares
        assert p.shares == 100
        assert p.position_pct == pytest.approx(0.10)

    def test_low_conviction_is_a_probe(self):
        p = plan_position("HFCL", 100_000, 100.0, "LOW")
        # 0.4 * 10% = 4% = 4000 / 100 = 40 shares
        assert p.shares == 40

    def test_never_exceeds_max_position_pct(self):
        for conv in ("LOW", "MEDIUM", "HIGH"):
            p = plan_position("X", 100_000, 100.0, conv)
            assert p.position_pct <= config.RISK["max_position_pct"] + 1e-9

    def test_stop_price_and_risk(self):
        p = plan_position("HFCL", 100_000, 100.0, "HIGH", stop_pct=0.10)
        assert p.stop_price == 90.0
        # 100 shares * (100 - 90) = 1000 at risk = 1% of book
        assert p.risk_value == 1000.0
        assert p.risk_pct == pytest.approx(0.01)

    def test_target_is_2R(self):
        p = plan_position("HFCL", 100_000, 100.0, "HIGH", stop_pct=0.10)
        # risk/share = 10 → target = 100 + 2*10 = 120
        assert p.target_price == 120.0

    def test_default_stop_pct_used_when_none(self):
        p = plan_position("HFCL", 100_000, 100.0, "HIGH")
        expected = round(100.0 * (1 - config.RISK["default_stop_pct"]), 2)
        assert p.stop_price == expected

    def test_unknown_conviction_uses_half_and_notes(self):
        p = plan_position("HFCL", 100_000, 100.0, "INSANE")
        # half the 10% cap = 5% = 50 shares
        assert p.shares == 50
        assert any("unknown conviction" in n for n in p.notes)

    def test_account_too_small_zero_shares_with_note(self):
        p = plan_position("HFCL", 1_000, 5000.0, "LOW")
        assert p.shares == 0
        assert any("too small" in n for n in p.notes)

    def test_invalid_account_raises(self):
        with pytest.raises(ValueError):
            plan_position("HFCL", 0, 100.0, "HIGH")

    def test_invalid_entry_raises(self):
        with pytest.raises(ValueError):
            plan_position("HFCL", 100_000, 0, "HIGH")

    def test_symbol_uppercased(self):
        p = plan_position("hfcl", 100_000, 100.0, "HIGH")
        assert p.symbol == "HFCL"


# ---------------------------------------------------------------------------
# circuit_breakers (against a temp ledger)
# ---------------------------------------------------------------------------

@pytest.fixture
def temp_ledger(tmp_path, monkeypatch):
    monkeypatch.setattr("config.DB_PATH", str(tmp_path / "test.db"))
    led = Ledger()
    yield led
    led.close()


def _open(led, symbol="HFCL", shares=10, entry=100.0, stop=88.0, opened=None):
    return led.open_position(symbol, shares, entry, stop_price=stop, opened=opened)


class TestCircuitBreakers:
    def test_clear_when_empty(self, temp_ledger):
        assert circuit_breakers(temp_ledger) == []

    def test_trips_max_trades_per_day(self, temp_ledger, monkeypatch):
        monkeypatch.setitem(config.RISK, "max_trades_per_day", 2)
        today = date.today().isoformat()
        for _ in range(3):
            _open(temp_ledger, opened=today)
        breaches = circuit_breakers(temp_ledger)
        assert any("TRADES TODAY" in b for b in breaches)

    def test_trips_max_open_positions(self, temp_ledger, monkeypatch):
        monkeypatch.setitem(config.RISK, "max_open_positions", 2)
        # distinct dates so the per-day breaker doesn't also fire
        _open(temp_ledger, opened="2026-01-01")
        _open(temp_ledger, opened="2026-01-02")
        _open(temp_ledger, opened="2026-01-03")
        breaches = circuit_breakers(temp_ledger, when="2026-01-04")
        assert any("OPEN POSITIONS" in b for b in breaches)

    def test_positions_opened_on_isolates_by_date(self, temp_ledger):
        _open(temp_ledger, opened="2026-01-01")
        _open(temp_ledger, opened="2026-01-01")
        _open(temp_ledger, opened="2026-01-02")
        assert temp_ledger.positions_opened_on("2026-01-01") == 2
        assert temp_ledger.positions_opened_on("2026-01-02") == 1
        assert temp_ledger.positions_opened_on("2026-01-03") == 0

    def test_closed_position_not_counted_as_open(self, temp_ledger, monkeypatch):
        monkeypatch.setitem(config.RISK, "max_open_positions", 1)
        pid = _open(temp_ledger, opened="2026-01-01")
        temp_ledger.close_position(pid, 110.0, "done")
        # closed → no longer OPEN, so the open-position breaker stays clear
        breaches = circuit_breakers(temp_ledger, when="2026-01-02")
        assert not any("OPEN POSITIONS" in b for b in breaches)

    def test_prospective_plan_counts_toward_open_cap(self, temp_ledger, monkeypatch):
        monkeypatch.setitem(config.RISK, "max_open_positions", 1)
        _open(temp_ledger, opened="2026-01-01")  # 1 open = at cap
        plan = plan_position("STLTECH", 100_000, 100.0, "HIGH")  # would be the 2nd
        breaches = circuit_breakers(temp_ledger, when="2026-01-02", prospective=plan)
        assert any("OPEN POSITIONS" in b for b in breaches)

    def test_portfolio_heat_breach(self, temp_ledger, monkeypatch):
        monkeypatch.setitem(config.RISK, "max_portfolio_heat_pct", 0.02)
        # one open position risking 1200 (100 sh * (100-88)); prospective adds more
        _open(temp_ledger, shares=100, entry=100.0, stop=88.0, opened="2026-01-01")
        plan = plan_position("STLTECH", 100_000, 100.0, "HIGH", stop_pct=0.12)
        breaches = circuit_breakers(temp_ledger, when="2026-01-02", prospective=plan)
        assert any("PORTFOLIO HEAT" in b for b in breaches)

    def test_heat_within_cap_is_clear(self, temp_ledger, monkeypatch):
        monkeypatch.setitem(config.RISK, "max_portfolio_heat_pct", 0.06)
        plan = plan_position("HFCL", 1_000_000, 100.0, "LOW", stop_pct=0.12)
        breaches = circuit_breakers(temp_ledger, prospective=plan)
        assert not any("PORTFOLIO HEAT" in b for b in breaches)
