"""
Fundamental screen — the secondary filter. We ride themes through businesses
that aren't junk. Returns a transparent, per-metric breakdown (never a single
opaque score you can't interrogate).
"""
from __future__ import annotations
from dataclasses import dataclass, field

import config
from providers import Fundamentals


@dataclass
class ScreenResult:
    symbol: str
    name: str
    passed: bool
    score: float                       # 0..100, transparency over precision
    checks: dict[str, bool] = field(default_factory=dict)
    metrics: dict[str, object] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


def screen_one(f: Fundamentals) -> ScreenResult:
    cfg = config.SCREEN
    checks: dict[str, bool] = {}
    notes: list[str] = []

    def chk(name, value, predicate, desc):
        if value is None:
            checks[name] = False
            notes.append(f"{desc}: no data (treated as fail)")
        else:
            checks[name] = bool(predicate(value))

    chk("revenue_growth", f.revenue_growth,
        lambda v: v >= cfg["min_revenue_growth"], "revenue growth")
    chk("roe", f.roe, lambda v: v >= cfg["min_roe"], "ROE")
    chk("debt", f.debt_to_equity,
        lambda v: v <= cfg["max_debt_to_equity"], "debt/equity")
    chk("margin", f.operating_margin,
        lambda v: v >= cfg["min_operating_margin"], "operating margin")

    # Red-team flag: revenue up but margins down = likely low-margin order-book
    # padding. We don't auto-fail it, but we surface it loudly for the thesis.
    margin_expanding = (f.margin_trend is not None and f.margin_trend > 0)
    if f.revenue_growth and f.revenue_growth > 0 and f.margin_trend is not None \
            and f.margin_trend < 0:
        notes.append("WARNING: revenue growing while margins compress — "
                     "check for low-margin order-book padding, not real operating leverage.")

    passed_count = sum(1 for v in checks.values() if v)
    base = 100.0 * passed_count / len(checks)
    # Small bonus for genuine margin expansion (real operating leverage).
    if config.SCREEN.get("reward_margin_expansion") and margin_expanding:
        base = min(100.0, base + 8)
        notes.append("margins expanding — genuine operating leverage signal.")

    if f.completeness() < 0.6:
        notes.append(f"low data completeness ({f.completeness():.0%}); "
                     "score is unreliable — verify on screener.in / filings.")

    passed = all([checks["revenue_growth"], checks["roe"], checks["debt"]])
    return ScreenResult(
        symbol=f.symbol, name=f.name, passed=passed, score=round(base, 1),
        checks=checks,
        metrics={
            "revenue_growth": f.revenue_growth, "roe": f.roe,
            "debt_to_equity": f.debt_to_equity, "operating_margin": f.operating_margin,
            "margin_trend": f.margin_trend, "shares_change": f.shares_change,
        },
        notes=notes,
    )


def screen_universe(provider, symbols: list[str]) -> list[ScreenResult]:
    results = [screen_one(provider.get_fundamentals(s)) for s in symbols]
    results.sort(key=lambda r: r.score, reverse=True)
    return results
