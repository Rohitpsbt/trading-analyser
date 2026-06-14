"""Categorical management-credibility flag — merit/demerit tallies and overrides."""
from providers import Fundamentals
from credibility import assess, Credibility


def _f(**kw):
    return Fundamentals(symbol="X", name="X", **kw)


def test_insufficient_data_when_no_signals():
    r = assess(_f())
    assert r.flag is Credibility.INSUFFICIENT


def test_credible_when_merits_dominate():
    # no dilution (merit) + margin expansion alongside growth (merit) = 2 merits, 0 demerits
    r = assess(_f(shares_change=0.0, revenue_growth=0.10, margin_trend=0.02,
                  debt_to_equity=0.5))
    assert r.flag is Credibility.CREDIBLE


def test_caution_when_demerits_dominate():
    # dilution + growth-without-margins + high leverage = 3 demerits
    r = assess(_f(shares_change=0.10, revenue_growth=0.10, margin_trend=-0.02,
                  debt_to_equity=2.0))
    assert r.flag is Credibility.CAUTION


def test_neutral_when_balanced():
    # no dilution (1 merit) vs high leverage (1 demerit)
    r = assess(_f(shares_change=0.0, debt_to_equity=2.0))
    assert r.flag is Credibility.NEUTRAL


def test_guidance_history_is_strongest_signal():
    gh = [{"met": True}, {"met": True}, {"met": True}, {"met": True}, {"met": False}]
    r = assess(_f(), guidance_history=gh)  # 4/5 = 0.8 -> +2 merits -> CREDIBLE
    assert r.flag is Credibility.CREDIBLE
    assert any("hit guidance" in reason for reason in r.reasons)


def test_chronic_misses_flag_caution():
    gh = [{"met": False}, {"met": False}, {"met": False}, {"met": True}]
    r = assess(_f(), guidance_history=gh)  # 1/4 = 0.25 -> +2 demerits -> CAUTION
    assert r.flag is Credibility.CAUTION
