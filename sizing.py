"""
Position sizing + circuit breakers — the risk layer.

This is the first half of M3 (the README's 'tiny live capital with hard circuit
breakers' rung), deliberately built BEFORE any broker feed: a live broker
integration is premature until the ledger shows the model works, but the sizing
math and the guardrails are self-contained and useful now.

It is decision-support, not execution. `plan_position` turns an account size +
entry + conviction into a recommended share count, stop, capital-at-risk, and a
reference target — bounded by config.RISK. `circuit_breakers` checks a plan
against the ledger (open positions, trades today). Nothing here places an order.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date

import config
from redteam import breakeven_move_pct


@dataclass
class PositionPlan:
    symbol: str
    account_size: float
    conviction: str
    entry: float
    stop_pct: float
    stop_price: float
    target_price: float            # 2R reference; your thesis exit conditions govern
    shares: int
    position_value: float
    position_pct: float            # of account
    risk_value: float              # capital at risk to the stop
    risk_pct: float                # of account
    notes: list[str] = field(default_factory=list)


def plan_position(symbol: str, account_size: float, entry: float,
                  conviction: str = "MEDIUM", stop_pct: float | None = None
                  ) -> PositionPlan:
    """Recommend a position bounded by config.RISK. Conviction scales the size
    within the max-position cap (HIGH = full cap, LOW = a probe). The stop drives
    capital-at-risk; the target is a 2R reference, not a price prediction."""
    if account_size <= 0:
        raise ValueError("account_size must be positive")
    if entry <= 0:
        raise ValueError("entry must be positive")

    conv = (conviction or "MEDIUM").upper()
    frac = config.RISK["conviction_sizing"].get(conv, 0.5)
    cap_pct = config.RISK["max_position_pct"]
    target_alloc_pct = cap_pct * frac          # never exceeds the per-name cap

    # Round the rupee budget to paise before flooring to whole shares, so float
    # dust (0.10 * 0.7 = 0.06999…) doesn't shave off a share.
    budget = round(account_size * target_alloc_pct, 2)
    shares = int(budget // entry)
    position_value = round(shares * entry, 2)
    position_pct = position_value / account_size

    sp = config.RISK["default_stop_pct"] if stop_pct is None else stop_pct
    stop_price = round(entry * (1 - sp), 2)
    risk_per_share = entry - stop_price
    risk_value = round(risk_per_share * shares, 2)
    risk_pct = risk_value / account_size
    target_price = round(entry + 2 * risk_per_share, 2)  # 2R reference

    notes: list[str] = []
    if shares == 0:
        notes.append(f"account too small for one lot at ₹{entry:.2f} within the "
                     f"{target_alloc_pct:.0%} allocation — no position.")
    be = breakeven_move_pct()
    notes.append(f"need > {be:.2%} move just to clear round-trip friction "
                 f"(then {config.COSTS['stcg_tax_pct']:.0%} STCG on gains); "
                 f"2R target implies ~{(2*sp):.0%} move — comfortably above friction.")
    if conv not in config.RISK["conviction_sizing"]:
        notes.append(f"unknown conviction '{conviction}' — used half the cap.")

    return PositionPlan(
        symbol=symbol.upper(), account_size=account_size, conviction=conv,
        entry=entry, stop_pct=sp, stop_price=stop_price, target_price=target_price,
        shares=shares, position_value=position_value, position_pct=position_pct,
        risk_value=risk_value, risk_pct=risk_pct, notes=notes,
    )


def circuit_breakers(ledger, when: str | None = None) -> list[str]:
    """Check the ledger against the daily/concurrent caps in config.RISK. Returns
    a list of breach messages (empty = clear to proceed). Treats each saved thesis
    as a paper position — a reasonable proxy until real position tracking lands."""
    when = when or date.today().isoformat()
    breaches: list[str] = []

    open_n = len(ledger.open_theses())
    max_open = config.RISK["max_open_positions"]
    if open_n >= max_open:
        breaches.append(f"OPEN POSITIONS: {open_n} open ≥ cap {max_open} — "
                        f"close/grade something before adding risk.")

    today_n = ledger.count_created_on(when)
    max_day = config.RISK["max_trades_per_day"]
    if today_n >= max_day:
        breaches.append(f"TRADES TODAY: {today_n} logged on {when} ≥ cap {max_day} "
                        f"— overtrading guard; sleep on the next one.")
    return breaches
