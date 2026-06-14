"""SQLite forward-tracking ledger — record -> grade -> performance round-trip."""
from datetime import date

import pytest

from thesis import Thesis
from ledger import Ledger


def _thesis(symbol="HFCL", ref=100.0, conviction="MEDIUM"):
    return Thesis(
        symbol=symbol, name=symbol, as_of=date.today().isoformat(), catalyst="cat",
        conviction=conviction, suggested_action="BUY_CANDIDATE", reference_price=ref,
        fundamental_summary="fs", credibility_flag="CREDIBLE",
        bull_case="bull", bear_case="bear", exit_conditions="exit",
        redteam={"ruin": "x"}, narrated=False)


@pytest.fixture()
def ledger(tmp_path):
    led = Ledger(db_path=str(tmp_path / "test.db"))
    yield led
    led.close()


def test_record_then_open_theses(ledger):
    tid = ledger.record(_thesis())
    assert tid == 1
    rows = ledger.open_theses()
    assert len(rows) == 1
    assert rows[0]["symbol"] == "HFCL"
    assert rows[0]["status"] == "OPEN"


def test_grade_computes_pnl_and_closes(ledger):
    tid = ledger.record(_thesis(ref=100.0))
    res = ledger.grade(tid, 110.0, "right", note="played out")
    assert res["pnl_pct"] == pytest.approx(0.10)
    assert res["verdict"] == "RIGHT"  # upper-cased
    # Graded theses leave the OPEN list.
    assert ledger.open_theses() == []


def test_grade_handles_missing_reference_price(ledger):
    tid = ledger.record(_thesis(ref=None))
    res = ledger.grade(tid, 110.0, "NOISE")
    assert res["pnl_pct"] is None


def test_grade_unknown_thesis_raises(ledger):
    with pytest.raises(ValueError):
        ledger.grade(999, 100.0, "RIGHT")


def test_performance_aggregates_hit_rate_and_by_conviction(ledger):
    a = ledger.record(_thesis(ref=100.0, conviction="HIGH"))
    b = ledger.record(_thesis(ref=100.0, conviction="LOW"))
    ledger.grade(a, 120.0, "RIGHT")   # +20%
    ledger.grade(b, 90.0, "WRONG")    # -10%
    perf = ledger.performance()
    assert perf["graded"] == 2
    assert perf["hit_rate"] == 0.5
    assert perf["avg_pnl_pct"] == pytest.approx(0.05)
    assert perf["avg_pnl_by_conviction"]["HIGH"] == pytest.approx(0.20)
    assert perf["avg_pnl_by_conviction"]["LOW"] == pytest.approx(-0.10)


def test_performance_empty_ledger(ledger):
    assert ledger.performance()["graded"] == 0
