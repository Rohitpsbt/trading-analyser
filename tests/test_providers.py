"""Data providers — mock determinism, completeness, statement parsing, D/E units."""
import pandas as pd

from providers import (Fundamentals, MockProvider, YFinanceProvider, _row,
                       get_provider)


def test_mock_is_deterministic():
    mp = MockProvider()
    assert mp.get_fundamentals("HFCL") == mp.get_fundamentals("HFCL")
    assert mp.get_return_pct("HFCL", 30) == mp.get_return_pct("HFCL", 30)


def test_mock_differs_by_symbol():
    mp = MockProvider()
    assert mp.get_fundamentals("HFCL") != mp.get_fundamentals("RELIANCE")


def test_get_provider_mock_flag():
    assert isinstance(get_provider(use_mock=True), MockProvider)


def test_completeness_fraction():
    f = Fundamentals(symbol="X", revenue_growth=0.1, roe=0.1, operating_margin=0.1)
    assert f.completeness() == 3 / 5  # 3 of 5 tracked fields present


def test_row_helper_resolves_labels_and_skips_missing():
    df = pd.DataFrame(
        {"2024": [100.0, 20.0], "2023": [80.0, 15.0]},
        index=["Total Revenue", "Operating Income"],
    )
    assert _row(df, ["Total Revenue"], 0) == 100.0
    assert _row(df, ["Missing", "Operating Income"], 1) == 15.0
    assert _row(df, ["Nope"], 0) is None


def test_row_helper_skips_nan():
    df = pd.DataFrame({"2024": [float("nan")]}, index=["Total Revenue"])
    assert _row(df, ["Total Revenue"], 0) is None


class _FakeTicker:
    """Stand-in for yfinance.Ticker so get_fundamentals runs without a network."""
    def __init__(self, info):
        self.info = info
        self.income_stmt = None
        self.balance_sheet = None


def test_yfinance_normalises_debt_to_equity_to_ratio(monkeypatch):
    provider = YFinanceProvider()
    fake = _FakeTicker({
        "shortName": "Test Co", "currentPrice": 100.0, "debtToEquity": 50.0,
        "revenueGrowth": 0.20, "returnOnEquity": 0.18, "operatingMargins": 0.15,
    })
    monkeypatch.setattr(provider, "_ticker", lambda symbol: fake)
    f = provider.get_fundamentals("TEST")
    # yfinance reports D/E as a percentage (50.0 -> 0.5x).
    assert f.debt_to_equity == 0.5
    assert f.revenue_growth == 0.20
    assert f.name == "Test Co"
