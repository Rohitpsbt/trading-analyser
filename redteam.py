"""
Red-team checklist as a SYSTEM, not a vibe.

Every thesis runs through eight questions. Some we can check programmatically
(already-priced-in, survives-friction, ruin); the rest are framed for the LLM
to answer explicitly and are stored so you can audit the reasoning later.
"""
from __future__ import annotations
from dataclasses import dataclass, field

import config

CHECKLIST = [
    ("hidden_assumption", "What must be true for this to work that we haven't verified?"),
    ("look_ahead", "Are we using any info we wouldn't have had at the decision moment?"),
    ("base_rate", "Ignoring the story, how often does this kind of setup actually work?"),
    ("already_priced_in", "By the time we can see this signal, has the market already moved?"),
    ("other_side", "Who is selling to us when we buy, and what do they know/believe?"),
    ("survives_friction", "Does the edge survive brokerage, STT, slippage and STCG tax?"),
    ("regime", "Does this only work in the current bull/liquidity regime?"),
    ("ruin", "Worst realistic case — can it permanently impair capital?"),
]


@dataclass
class RedTeamReport:
    automated: dict[str, str] = field(default_factory=dict)
    flags: list[str] = field(default_factory=list)
    # Questions left for the LLM / human to answer explicitly.
    open_questions: dict[str, str] = field(default_factory=dict)


def breakeven_move_pct() -> float:
    """Round-trip cost as a fraction of price — the move needed just to break even.
    This is what 'survives_friction' must clear before any alpha counts."""
    c = config.COSTS
    round_trip = 2 * (c["brokerage_pct"] + c["slippage_pct"]) + c["stt_pct"]
    return round_trip  # pre-tax; tax applies to gains above this


def run_automated(symbol: str, recent_return_pct: float | None) -> RedTeamReport:
    rep = RedTeamReport()

    # 4. Already priced in.
    thr = config.RISK["already_run_threshold_pct"]
    lb = config.RISK["already_run_lookback_days"]
    if recent_return_pct is None:
        rep.automated["already_priced_in"] = f"no price data for last {lb}d — verify manually."
    elif recent_return_pct >= thr:
        rep.automated["already_priced_in"] = (
            f"ALREADY UP {recent_return_pct:.0%} in {lb}d (> {thr:.0%}). "
            f"Catalyst likely priced in — high risk of being exit liquidity.")
        rep.flags.append("already_run")
    else:
        rep.automated["already_priced_in"] = (
            f"up {recent_return_pct:.0%} in {lb}d — not yet over-extended on this window.")

    # 6. Survives friction.
    be = breakeven_move_pct()
    rep.automated["survives_friction"] = (
        f"round-trip cost ≈ {be:.2%}; need > {be:.2%} move just to break even, "
        f"then {config.COSTS['stcg_tax_pct']:.0%} STCG on gains. "
        f"Thesis target should clear this with margin.")

    # 8. Ruin / sizing.
    mp = config.RISK["max_position_pct"]
    stop = config.RISK["default_stop_pct"]
    risk_of_book = mp * stop
    rep.automated["ruin"] = (
        f"at max {mp:.0%} position with a {stop:.0%} stop, worst single-trade hit "
        f"≈ {risk_of_book:.1%} of book (gap risk excluded). Keep stop honest.")

    # Open questions for the LLM/human.
    for key, q in CHECKLIST:
        if key not in rep.automated:
            rep.open_questions[key] = q
    return rep
