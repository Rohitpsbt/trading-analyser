"""Automated red-team checks — friction math, already-run guard, ruin sizing."""
import pytest

import config
from redteam import run_automated, breakeven_move_pct, CHECKLIST


def test_breakeven_matches_cost_config():
    c = config.COSTS
    expected = 2 * (c["brokerage_pct"] + c["slippage_pct"]) + c["stt_pct"]
    assert breakeven_move_pct() == pytest.approx(expected)
    assert breakeven_move_pct() == pytest.approx(0.0046)


def test_already_run_flag_trips_past_threshold():
    rep = run_automated("X", config.RISK["already_run_threshold_pct"] + 0.05)
    assert "already_run" in rep.flags
    assert "ALREADY UP" in rep.automated["already_priced_in"]


def test_not_over_extended_below_threshold():
    rep = run_automated("X", 0.10)
    assert "already_run" not in rep.flags
    assert "not yet over-extended" in rep.automated["already_priced_in"]


def test_missing_price_is_flagged_for_manual_check():
    rep = run_automated("X", None)
    assert "already_run" not in rep.flags
    assert "no price data" in rep.automated["already_priced_in"]


def test_ruin_uses_position_and_stop_config():
    rep = run_automated("X", 0.0)
    expected = config.RISK["max_position_pct"] * config.RISK["default_stop_pct"]
    assert f"{expected:.1%}" in rep.automated["ruin"]  # 1.2%


def test_open_questions_cover_non_automated_checklist_items():
    rep = run_automated("X", 0.0)
    automated_keys = set(rep.automated)
    open_keys = set(rep.open_questions)
    all_keys = {k for k, _ in CHECKLIST}
    assert automated_keys.isdisjoint(open_keys)
    assert automated_keys | open_keys == all_keys
