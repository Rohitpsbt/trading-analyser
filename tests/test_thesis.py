"""Thesis drafter — offline conviction mapping and the LLM fallback contract."""
import json

from screening import ScreenResult
from credibility import CredibilityResult, Credibility
from redteam import RedTeamReport
import thesis
from thesis import (draft_thesis, draft_second_opinion, _offline_thesis,
                    _extract_json, _short_source)


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
    monkeypatch.setattr(thesis, "_call_llm", lambda s, u, provider=None: None)
    t = draft_thesis(_screen(), _cred(), _rt(), catalyst="cat", ref_price=100)
    assert t.narrated is False
    assert t.conviction == "MEDIUM"  # offline mapping
    assert t.reference_price == 100
    assert t.source == "offline"


def test_draft_uses_llm_json_when_available(monkeypatch):
    payload = json.dumps({
        "conviction": "high", "suggested_action": "buy_candidate",
        "fundamental_summary": "fs", "bull_case": "bull", "bear_case": "bear",
        "exit_conditions": "exit", "redteam": {"hidden_assumption": "answered"},
    })
    monkeypatch.setattr(thesis, "_call_llm", lambda s, u, provider=None: payload)
    t = draft_thesis(_screen(), _cred(), _rt(), catalyst="cat", ref_price=100)
    assert t.narrated is True
    assert t.conviction == "HIGH"          # normalised to upper
    assert t.bull_case == "bull"
    assert t.redteam["hidden_assumption"] == "answered"
    assert t.source.startswith("groq:")    # configured provider stamped


def test_draft_falls_back_on_invalid_json(monkeypatch):
    monkeypatch.setattr(thesis, "_call_llm", lambda s, u, provider=None: "not valid json")
    t = draft_thesis(_screen(), _cred(), _rt(), catalyst="cat", ref_price=100)
    assert t.narrated is False


def test_draft_parses_fenced_json_from_chatty_model(monkeypatch):
    payload = ("Sure! Here is the thesis:\n```json\n" + json.dumps({
        "conviction": "HIGH", "suggested_action": "BUY_CANDIDATE",
        "fundamental_summary": "", "bull_case": "", "bear_case": "",
        "exit_conditions": "", "redteam": {}}) + "\n```")
    monkeypatch.setattr(thesis, "_call_llm", lambda s, u, provider=None: payload)
    t = draft_thesis(_screen(), _cred(), _rt(), ref_price=100)
    assert t.narrated is True
    assert t.conviction == "HIGH"


def test_extract_json_strips_fences_and_prose():
    assert json.loads(_extract_json('```json\n{"a": 1}\n```')) == {"a": 1}
    assert json.loads(_extract_json('blah {"a": 1} trailing')) == {"a": 1}


def _payload(conviction, action):
    return json.dumps({
        "conviction": conviction, "suggested_action": action,
        "fundamental_summary": "", "bull_case": "", "bear_case": "",
        "exit_conditions": "", "redteam": {}})


def test_second_opinion_agreement(monkeypatch):
    monkeypatch.setattr(thesis, "_call_llm",
                        lambda s, u, provider=None: _payload("MEDIUM", "BUY_CANDIDATE"))
    so = draft_second_opinion(_screen(), _cred(), _rt(), providers=("groq", "gemini"))
    assert len(so.theses) == 2
    assert so.agree is True
    assert so.disagreements == []
    assert {_short_source(t) for t in so.theses} == {"groq", "gemini"}


def test_second_opinion_flags_disagreement(monkeypatch):
    def fake(system, user, provider=None):
        return (_payload("HIGH", "BUY_CANDIDATE") if provider == "groq"
                else _payload("LOW", "WATCH"))
    monkeypatch.setattr(thesis, "_call_llm", fake)
    so = draft_second_opinion(_screen(), _cred(), _rt())
    assert so.agree is False
    assert any("Conviction differs" in d for d in so.disagreements)
    assert any("Suggested action differs" in d for d in so.disagreements)
    # The shared disagreement note travels with every thesis (each is its own row).
    assert all(t.disagreements == so.disagreements for t in so.theses)


def test_second_opinion_narrated_count(monkeypatch):
    # Only groq has a "key"; gemini falls back to the offline template.
    def fake(system, user, provider=None):
        return _payload("MEDIUM", "BUY_CANDIDATE") if provider == "groq" else None
    monkeypatch.setattr(thesis, "_call_llm", fake)
    so = draft_second_opinion(_screen(), _cred(), _rt())
    assert so.narrated_count == 1
