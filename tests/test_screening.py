"""Fundamental screen logic — thresholds, the pass rule, and the transparency notes."""
from providers import Fundamentals
from screening import screen_one


def _f(**kw):
    return Fundamentals(symbol="X", name="X", **kw)


def test_strong_fundamentals_pass_with_margin_bonus():
    r = screen_one(_f(revenue_growth=0.20, roe=0.20, debt_to_equity=0.5,
                      operating_margin=0.15, margin_trend=0.02, shares_change=0.0))
    assert r.passed is True
    assert r.score == 100.0  # 4/4 checks, +8 margin bonus capped at 100
    assert all(r.checks.values())
    assert any("margins expanding" in n for n in r.notes)


def test_passed_requires_revenue_roe_debt_not_margin():
    # Margin check fails, but the three required checks pass -> still passed=True.
    r = screen_one(_f(revenue_growth=0.20, roe=0.20, debt_to_equity=0.5,
                      operating_margin=0.02))
    assert r.checks["margin"] is False
    assert r.passed is True


def test_score_is_fraction_of_checks_passed():
    # rev pass, roe fail, debt pass, margin fail -> 2/4 -> 50.0, no margin bonus.
    r = screen_one(_f(revenue_growth=0.20, roe=0.05, debt_to_equity=0.5,
                      operating_margin=0.02, margin_trend=None))
    assert r.score == 50.0
    assert r.passed is False  # roe failed and roe is required


def test_none_metric_is_treated_as_fail_with_note():
    r = screen_one(_f(revenue_growth=0.20, roe=None, debt_to_equity=0.5,
                      operating_margin=0.15))
    assert r.checks["roe"] is False
    assert any("no data" in n for n in r.notes)
    assert r.passed is False


def test_revenue_up_margins_down_emits_warning():
    r = screen_one(_f(revenue_growth=0.20, roe=0.20, debt_to_equity=0.5,
                      operating_margin=0.15, margin_trend=-0.02))
    assert any("WARNING" in n and "margins compress" in n for n in r.notes)


def test_low_completeness_note():
    r = screen_one(_f(revenue_growth=0.20))  # only 1 of 5 fields present
    assert any("low data completeness" in n for n in r.notes)
