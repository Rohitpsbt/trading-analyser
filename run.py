#!/usr/bin/env python3
"""
Trading Analyser — CLI orchestrator.

Decision-support only. It screens, surfaces catalysts, and drafts dated theses
with full reasoning for YOU to review. It never places an order.

Examples:
    python run.py screen --mock --top 10
    python run.py scan-catalysts --mock
    python run.py thesis HFCL --mock --catalyst "Jio fibre capex headline"
    python run.py ledger
    python run.py grade 1 --price 512.50 --verdict RIGHT --note "theme played out"
    python run.py report

Drop --mock on your own machine to use live yfinance + Google News data.
"""
from __future__ import annotations
import argparse

import config
from providers import get_provider, MockProvider
from screening import screen_universe, screen_one
from catalysts import SupplierLinkage, NewsMonitor
from credibility import assess
from redteam import run_automated, breakeven_move_pct
from thesis import draft_thesis
from ledger import Ledger


def cmd_screen(args):
    provider = get_provider(use_mock=args.mock)
    results = screen_universe(provider, config.UNIVERSE)
    top = results[: args.top]
    print(f"\nFundamental screen — top {len(top)} of {len(results)} "
          f"({'MOCK' if args.mock else 'LIVE'} data)\n" + "-" * 64)
    for r in top:
        tag = "PASS" if r.passed else "    "
        rg = r.metrics.get("revenue_growth")
        roe = r.metrics.get("roe")
        print(f"[{tag}] {r.symbol:<11} score {r.score:>5}  "
              f"rev_g {_pct(rg):>7}  roe {_pct(roe):>7}")
        for n in r.notes:
            if "WARNING" in n or "low data" in n:
                print(f"        ! {n}")


def cmd_scan(args):
    print(f"\nSupplier-linkage scan ({'MOCK' if args.mock else 'LIVE'} news)\n" + "-" * 64)
    linkage = SupplierLinkage()
    hits, errors = linkage.scan()
    if not hits:
        print("No live demand-signal headlines surfaced.")
        if errors:
            print(f"\n({len(errors)} feeds unreachable — expected in the sandbox. "
                  f"On your machine these pull live. First few:)")
            for e in errors[:4]:
                print(f"   - {e}")
        print("\nThemes & linkages currently watched:")
        for theme, d in config.LINKAGE_MAP.items():
            print(f"   {theme}: buyers={d['buyers']} -> suppliers={d['suppliers']}")
        return
    for h in hits:
        print(f"[{h.theme}] {h.buyer}: \"{h.trigger_headline}\"")
        print(f"        -> watch suppliers: {h.suppliers}")


def cmd_thesis(args):
    provider = get_provider(use_mock=args.mock)
    f = provider.get_fundamentals(args.symbol)
    screen = screen_one(f)
    cred = assess(f)
    recent = provider.get_return_pct(args.symbol,
                                     config.RISK["already_run_lookback_days"])
    rt = run_automated(args.symbol, recent)
    t = draft_thesis(screen, cred, rt, catalyst=args.catalyst, ref_price=f.price)

    print("\n" + "=" * 64)
    print(f"THESIS  {t.symbol} ({t.name})   as of {t.as_of}")
    print(f"{'(offline template — no LLM narrative)' if not t.narrated else ''}")
    print("=" * 64)
    print(f"Conviction      : {t.conviction}")
    print(f"Suggested action: {t.suggested_action}   (you decide & execute)")
    print(f"Reference price : {t.reference_price}")
    print(f"Credibility flag: {t.credibility_flag}")
    print(f"\nFundamentals : {t.fundamental_summary}")
    print(f"\nBull case    : {t.bull_case}")
    print(f"Bear case    : {t.bear_case}")
    print(f"\nExit plan    : {t.exit_conditions}")
    print(f"\nRed-team:")
    for k, v in t.redteam.items():
        print(f"   - {k}: {v}")

    if args.save:
        led = Ledger()
        tid = led.record(t)
        led.close()
        print(f"\nSaved to ledger as thesis #{tid}.")
    else:
        print("\n(not saved — add --save to log this call for later grading)")


def cmd_ledger(args):
    led = Ledger()
    rows = led.open_theses()
    print(f"\nOpen theses ({len(rows)})\n" + "-" * 64)
    for r in rows:
        print(f"#{r['id']:<3} {r['created']}  {r['symbol']:<10} "
              f"{r['suggested_action']:<14} conv={r['conviction']:<7} "
              f"ref={r['reference_price']}")
    led.close()


def cmd_grade(args):
    led = Ledger()
    res = led.grade(args.id, args.price, args.verdict, args.note or "")
    led.close()
    pnl = res["pnl_pct"]
    print(f"Graded thesis #{res['thesis_id']}: {res['verdict']}, "
          f"P&L {('%.1f%%' % (pnl*100)) if pnl is not None else 'n/a'}")


def cmd_report(args):
    led = Ledger()
    perf = led.performance()
    led.close()
    print(f"\nForward-track performance\n" + "-" * 64)
    for k, v in perf.items():
        print(f"   {k}: {v}")
    print(f"\n(break-even move per round trip ≈ {breakeven_move_pct():.2%} "
          f"before tax — alpha must clear this)")


def cmd_doctor(args):
    """Preflight: check the LLM and live-data paths so live runs fail loudly,
    not by silently degrading to mock/offline."""
    print("\nTrading Analyser — preflight check\n" + "=" * 64)

    # LLM provider / key / resolved model.
    cfg = config.LLM
    provider = (cfg.get("provider") or "none").lower()
    env_var = {"groq": "GROQ_API_KEY", "anthropic": "ANTHROPIC_API_KEY",
               "gemini": "GEMINI_API_KEY"}.get(provider)
    print(f"LLM provider     : {provider}")
    if env_var:
        key_set = bool(cfg.get(f"{provider}_api_key"))
        print(f"  {env_var:<18}: {'set' if key_set else 'NOT set'}")
        print(f"  model           : {config.model_for(provider)}")
        if not key_set:
            print(f"  -> no key: thesis uses the OFFLINE template (no narrative). "
                  f"Set {env_var} or change TA_LLM_PROVIDER.")
    else:
        print("  (no LLM provider configured — thesis uses the offline template)")

    # Market data (yfinance) reachability.
    print("\nMarket data (yfinance):")
    try:
        prov = get_provider(use_mock=False)
        if isinstance(prov, MockProvider):
            print("  yfinance unavailable — would fall back to MockProvider (no live data).")
        else:
            f = prov.get_fundamentals("RELIANCE")
            if f.price:
                print(f"  OK — RELIANCE ₹{f.price}, data completeness {f.completeness():.0%}")
            else:
                print(f"  reachable but no price returned; gaps: {f.data_gaps[:3]}")
    except Exception as e:
        print(f"  FAILED: {type(e).__name__}: {e}")

    # News feed (Google News RSS) reachability — also exercises the SSL fix.
    print("\nNews feed (Google News RSS):")
    items, err = NewsMonitor().fetch("Reliance capex", limit=3)
    if err:
        print(f"  FAILED: {err}")
    else:
        print(f"  OK — fetched {len(items)} headlines")
        for it in items[:2]:
            print(f"     - {it.title[:70]}")

    print("\nFix anything that FAILED above before logging live calls.")


def _pct(v):
    return f"{v*100:.1f}%" if isinstance(v, (int, float)) else "n/a"


def build_parser():
    p = argparse.ArgumentParser(description="Trading Analyser (decision-support, not execution)")
    sub = p.add_subparsers(dest="cmd", required=True)

    def add_mock(sp):
        sp.add_argument("--mock", action="store_true",
                        help="use synthetic data (no network)")

    s = sub.add_parser("screen"); add_mock(s)
    s.add_argument("--top", type=int, default=10); s.set_defaults(func=cmd_screen)

    s = sub.add_parser("scan-catalysts"); add_mock(s); s.set_defaults(func=cmd_scan)

    s = sub.add_parser("thesis"); add_mock(s)
    s.add_argument("symbol")
    s.add_argument("--catalyst", default="")
    s.add_argument("--save", action="store_true")
    s.set_defaults(func=cmd_thesis)

    s = sub.add_parser("ledger"); s.set_defaults(func=cmd_ledger)

    s = sub.add_parser("grade")
    s.add_argument("id", type=int)
    s.add_argument("--price", type=float, required=True)
    s.add_argument("--verdict", required=True, choices=["RIGHT", "WRONG", "EARLY", "NOISE"])
    s.add_argument("--note", default="")
    s.set_defaults(func=cmd_grade)

    s = sub.add_parser("report"); s.set_defaults(func=cmd_report)

    s = sub.add_parser("doctor",
                       help="preflight: check LLM key/model + live data/news reachability")
    s.set_defaults(func=cmd_doctor)
    return p


if __name__ == "__main__":
    args = build_parser().parse_args()
    args.func(args)
