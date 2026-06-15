"""SQLite forward-tracking ledger — record -> grade -> performance round-trip."""
from datetime import date

import pytest

from thesis import Thesis
from ledger import Ledger


def _thesis(symbol="HFCL", ref=100.0, conviction="MEDIUM", source=""):
    return Thesis(
        symbol=symbol, name=symbol, as_of=date.today().isoformat(), catalyst="cat",
        conviction=conviction, suggested_action="BUY_CANDIDATE", reference_price=ref,
        fundamental_summary="fs", credibility_flag="CREDIBLE",
        bull_case="bull", bear_case="bear", exit_conditions="exit",
        redteam={"ruin": "x"}, narrated=False, source=source)


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


def test_source_is_persisted(ledger):
    ledger.record(_thesis(source="groq:llama-3.1-8b-instant"))
    row = ledger.open_theses()[0]
    assert row["source"] == "groq:llama-3.1-8b-instant"


def test_performance_breaks_down_by_source(ledger):
    g = ledger.record(_thesis(ref=100.0, source="groq:llama"))
    gm = ledger.record(_thesis(ref=100.0, source="gemini:flash"))
    ledger.grade(g, 120.0, "RIGHT")   # groq +20%, right
    ledger.grade(gm, 90.0, "WRONG")   # gemini -10%, wrong
    bs = ledger.performance()["by_source"]
    assert bs["groq"]["hit_rate"] == 1.0
    assert bs["groq"]["avg_pnl_pct"] == pytest.approx(0.20)
    assert bs["gemini"]["hit_rate"] == 0.0
    assert bs["gemini"]["avg_pnl_pct"] == pytest.approx(-0.10)


class TestPositions:
    def test_open_then_list(self, ledger):
        pid = ledger.open_position("hfcl", 50, 100.0, stop_price=88.0,
                                   account_size=100_000, thesis_id=1, note="probe")
        assert pid == 1
        rows = ledger.open_positions()
        assert len(rows) == 1
        assert rows[0]["symbol"] == "HFCL"   # upper-cased
        assert rows[0]["shares"] == 50
        assert rows[0]["status"] == "OPEN"
        assert rows[0]["thesis_id"] == 1

    def test_close_computes_realized_pnl(self, ledger):
        pid = ledger.open_position("HFCL", 100, 100.0, stop_price=88.0)
        res = ledger.close_position(pid, 120.0, note="target hit")
        assert res["realized_pnl"] == pytest.approx(2000.0)   # 100 * (120-100)
        assert res["pnl_pct"] == pytest.approx(0.20)
        assert ledger.open_positions() == []                  # left the OPEN list

    def test_close_negative_pnl(self, ledger):
        pid = ledger.open_position("HFCL", 10, 100.0, stop_price=88.0)
        res = ledger.close_position(pid, 88.0)
        assert res["realized_pnl"] == pytest.approx(-120.0)

    def test_close_unknown_raises(self, ledger):
        with pytest.raises(ValueError):
            ledger.close_position(999, 100.0)

    def test_close_already_closed_raises(self, ledger):
        pid = ledger.open_position("HFCL", 10, 100.0, stop_price=88.0)
        ledger.close_position(pid, 110.0)
        with pytest.raises(ValueError):
            ledger.close_position(pid, 120.0)

    def test_exposure_aggregates_invested_and_heat(self, ledger):
        ledger.open_position("HFCL", 100, 100.0, stop_price=88.0)     # value 10000, risk 1200
        ledger.open_position("STLTECH", 10, 200.0, stop_price=180.0)  # value 2000, risk 200
        exp = ledger.exposure()
        assert exp["open"] == 2
        assert exp["invested"] == pytest.approx(12000.0)
        assert exp["at_risk"] == pytest.approx(1400.0)

    def test_exposure_no_stop_counts_full_value_at_risk(self, ledger):
        ledger.open_position("HFCL", 10, 100.0, stop_price=None)      # no stop
        exp = ledger.exposure()
        assert exp["at_risk"] == pytest.approx(1000.0)                # full value

    def test_closed_position_excluded_from_exposure(self, ledger):
        pid = ledger.open_position("HFCL", 100, 100.0, stop_price=88.0)
        ledger.close_position(pid, 110.0)
        exp = ledger.exposure()
        assert exp["open"] == 0
        assert exp["invested"] == 0


def test_legacy_db_without_source_column_is_migrated(tmp_path):
    """A DB created before the `source` column exists must gain it on open."""
    import sqlite3
    path = str(tmp_path / "legacy.db")
    conn = sqlite3.connect(path)
    conn.executescript(
        """CREATE TABLE theses (
               id INTEGER PRIMARY KEY AUTOINCREMENT, created TEXT, symbol TEXT,
               name TEXT, catalyst TEXT, conviction TEXT, suggested_action TEXT,
               reference_price REAL, credibility_flag TEXT, narrated INTEGER,
               payload TEXT, status TEXT DEFAULT 'OPEN');""")
    conn.commit()
    conn.close()

    led = Ledger(db_path=path)
    cols = {r["name"] for r in led.conn.execute("PRAGMA table_info(theses)")}
    assert "source" in cols
    assert led.record(_thesis(source="groq:x")) == 1
    led.close()
