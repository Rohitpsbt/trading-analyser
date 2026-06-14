"""Thesis drafter — offline conviction mapping and the LLM fallback contract."""
import json

from screening import ScreenResult
from credibility import CredibilityResult, Credibility
from redteam import RedTeamReport
import thesis
from thesis import draft_thesis, _offline_thesis


def _screen(passed=True, score=100.0):
    return ScreenResult(symbol="HFCL", name="HFCL", passed=passed, score=score)


def _cred(flag=Credibility.CREDIBLE):
    return CredibilityResult(flag, ["reason"])


def _rt(already_run=False):
    return RedTeamReport(automated={"ruin": "x"},
                         flags=["already_run"] if already_run else [],
                         open_questions={"hidden_assumption": "q"})


def test_offline_buy_candidate_when_passed_credible_not_run():
    out = _offline_thesis(_screen(), _cred(Credibility.CREDIBLE), _rt(False), "cat", 100)
    assert out["conviction"] == "MEDIUM"
    assert out["suggested_action"] == "BUY_CANDIDATE"


def test_offline_watch_when_already_run():
    out = _offline_thesis(_screen(), _cred(Credibility.CREDIBLE), _rt(True), "cat", 100)
    assert out["conviction"] == "LOW"
    assert out["suggested_action"] == "WATCH"


def test_offline_watch_when_caution():
    out = _offline_thesis(_screen(), _cred(Credibility.CAUTION), _rt(False), "cat", 100)
    assert out["suggested_action"] == "WATCH"


def test_draft_falls_back_to_offline_when_no_llm(monkeypatch):
    monkeypatch.setattr(thesis, "_call_llm", lambda s, u: None)
    t = draft_thesis(_screen(), _cred(), _rt(), catalyst="cat", ref_price=100)
    assert t.narrated is False
    assert t.conviction == "MEDIUM"  # offline mapping
    assert t.reference_price == 100


def test_draft_uses_llm_json_when_available(monkeypatch):
    payload = json.dumps({
        "conviction": "high", "suggested_action": "buy_candidate",
        "fundamental_summary": "fs", "bull_case": "bull", "bear_case": "bear",
        "exit_conditions": "exit", "redteam": {"hidden_assumption": "answered"},
    })
    monkeypatch.setattr(thesis, "_call_llm", lambda s, u: payload)
    t = draft_thesis(_screen(), _cred(), _rt(), catalyst="cat", ref_price=100)
    assert t.narrated is True
    assert t.conviction == "HIGH"          # normalised to upper
    assert t.bull_case == "bull"
    assert t.redteam["hidden_assumption"] == "answered"


def test_draft_falls_back_on_invalid_json(monkeypatch):
    monkeypatch.setattr(thesis, "_call_llm", lambda s, u: "not valid json")
    t = draft_thesis(_screen(), _cred(), _rt(), catalyst="cat", ref_price=100)
    assert t.narrated is False
