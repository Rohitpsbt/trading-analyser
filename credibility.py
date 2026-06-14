"""
Management credibility flag.

Per our design decision: this is a CATEGORICAL FLAG with concrete reasons, not a
precise percentage. Its job is to *downweight hype*, not to manufacture false
precision you can't calibrate. It anchors on checkable facts.

Where guidance-vs-delivery history is available (you'll feed it in later from
concall transcripts), it's the strongest input. Until then we use the hard
financial tells that don't lie: serial dilution, margin delivery, leverage,
pledging.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum

from providers import Fundamentals


class Credibility(str, Enum):
    CREDIBLE = "CREDIBLE"
    NEUTRAL = "NEUTRAL"
    CAUTION = "CAUTION"
    INSUFFICIENT = "INSUFFICIENT_DATA"


@dataclass
class CredibilityResult:
    flag: Credibility
    reasons: list[str] = field(default_factory=list)
    # Optional structured guidance history you supply later:
    # [{"year": 2024, "guided": "20% rev growth", "delivered": "12%", "met": False}, ...]
    guidance_history: list[dict] = field(default_factory=list)


def assess(f: Fundamentals, guidance_history: list[dict] | None = None) -> CredibilityResult:
    reasons: list[str] = []
    demerits = 0
    merits = 0
    data_points = 0

    # 1. Serial dilution — issuing shares repeatedly erodes per-share value and
    #    often funds growth that doesn't earn its cost of capital.
    if f.shares_change is not None:
        data_points += 1
        if f.shares_change > 0.05:
            demerits += 1
            reasons.append(f"share count up {f.shares_change:.0%} YoY — dilution risk.")
        elif f.shares_change <= 0.0:
            merits += 1
            reasons.append("no dilution (stable/declining share count).")

    # 2. Margin delivery — did growth come with margin expansion or compression?
    if f.margin_trend is not None and f.revenue_growth is not None:
        data_points += 1
        if f.revenue_growth > 0 and f.margin_trend < -0.005:
            demerits += 1
            reasons.append("growth without margin expansion — possible low-quality "
                           "order-book padding; discount optimistic guidance.")
        elif f.margin_trend > 0.005:
            merits += 1
            reasons.append("margins expanding alongside growth — real operating leverage.")

    # 3. Leverage — high debt narrows the margin for error on any 'future thinking'.
    if f.debt_to_equity is not None:
        data_points += 1
        if f.debt_to_equity > 1.5:
            demerits += 1
            reasons.append(f"high leverage (D/E {f.debt_to_equity:.2f}) — execution risk on promises.")

    # 4. Promoter pledging, when available.
    if f.promoter_pledge is not None and f.promoter_pledge > 0.20:
        data_points += 1
        demerits += 1
        reasons.append(f"promoter pledge {f.promoter_pledge:.0%} — governance caution.")

    # 5. Guidance vs delivery — strongest signal when present.
    gh = guidance_history or []
    if gh:
        met = sum(1 for g in gh if g.get("met"))
        data_points += len(gh)
        rate = met / len(gh)
        if rate >= 0.7:
            merits += 2
            reasons.append(f"hit guidance {met}/{len(gh)} years — credible communicators.")
        elif rate <= 0.4:
            demerits += 2
            reasons.append(f"missed guidance often ({met}/{len(gh)}) — chronic over-promisers.")

    if data_points == 0:
        return CredibilityResult(Credibility.INSUFFICIENT,
                                 ["no credibility signals available — gather concall "
                                  "guidance history before sizing up."], gh)

    if demerits >= 2 and demerits > merits:
        flag = Credibility.CAUTION
    elif merits >= 2 and merits > demerits:
        flag = Credibility.CREDIBLE
    else:
        flag = Credibility.NEUTRAL
    return CredibilityResult(flag, reasons, gh)
