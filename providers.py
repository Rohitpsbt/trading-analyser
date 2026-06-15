"""
Data providers. The rest of the system talks ONLY to the MarketDataProvider
interface, so you can swap yfinance for Breeze/Upstox later without touching
screening, catalysts, or thesis logic.

- YFinanceProvider: real data (needs internet; runs on your machine).
- MockProvider: deterministic synthetic data so the pipeline runs anywhere
  (used here because the build sandbox can't reach Yahoo).
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional
import hashlib
import math

import config


@dataclass
class Fundamentals:
    symbol: str
    name: str = ""
    price: Optional[float] = None
    market_cap: Optional[float] = None
    revenue_growth: Optional[float] = None     # YoY, fraction
    earnings_growth: Optional[float] = None     # YoY, fraction
    roe: Optional[float] = None
    debt_to_equity: Optional[float] = None
    operating_margin: Optional[float] = None
    # Margin trend: latest operating margin minus year-ago. >0 = expanding.
    margin_trend: Optional[float] = None
    # Share count YoY change — serial dilution is a credibility red flag.
    shares_change: Optional[float] = None
    promoter_pledge: Optional[float] = None
    # Free-form notes about what was missing/unreliable (yfinance is patchy).
    data_gaps: list[str] = field(default_factory=list)

    def completeness(self) -> float:
        fields = [self.revenue_growth, self.earnings_growth, self.roe,
                  self.debt_to_equity, self.operating_margin]
        have = sum(1 for f in fields if f is not None)
        return have / len(fields)


class MarketDataProvider(ABC):
    @abstractmethod
    def get_fundamentals(self, symbol: str) -> Fundamentals: ...

    @abstractmethod
    def get_return_pct(self, symbol: str, lookback_days: int) -> Optional[float]:
        """Price return over the lookback window, as a fraction."""
        ...

    def get_price(self, symbol: str) -> Optional[float]:
        """Latest price. Default pulls it from fundamentals; a provider with a
        cheaper quote endpoint may override. Used to auto-fill the grade price."""
        return self.get_fundamentals(symbol).price


class YFinanceProvider(MarketDataProvider):
    """Real provider. Requires internet. yfinance fundamentals are incomplete
    and occasionally wrong, so every extraction is defensive."""

    def __init__(self):
        import yfinance as yf  # imported lazily so MockProvider works without it
        self._yf = yf
        self._cache: dict[str, object] = {}

    def _ticker(self, symbol: str):
        yt = config.ticker_to_yf(symbol)
        if yt not in self._cache:
            self._cache[yt] = self._yf.Ticker(yt)
        return self._cache[yt]

    def get_fundamentals(self, symbol: str) -> Fundamentals:
        f = Fundamentals(symbol=symbol)
        try:
            t = self._ticker(symbol)
            info = t.info or {}
        except Exception as e:
            f.data_gaps.append(f"info fetch failed: {e}")
            return f

        f.name = info.get("shortName") or info.get("longName") or symbol
        f.price = info.get("currentPrice") or info.get("regularMarketPrice")
        f.market_cap = info.get("marketCap")
        f.revenue_growth = info.get("revenueGrowth")
        f.earnings_growth = info.get("earningsGrowth")
        f.roe = info.get("returnOnEquity")
        dte = info.get("debtToEquity")
        # yfinance reports D/E as a percentage (e.g. 45.0 means 0.45x).
        f.debt_to_equity = dte / 100.0 if dte is not None else None
        f.operating_margin = info.get("operatingMargins")

        for label, val in [("revenue_growth", f.revenue_growth),
                           ("roe", f.roe), ("operating_margin", f.operating_margin)]:
            if val is None:
                f.data_gaps.append(f"missing {label}")

        # Margin trend + share-count change from financial statements when present.
        try:
            self._enrich_from_statements(t, f)
        except Exception as e:
            f.data_gaps.append(f"statement parse failed: {e}")
        return f

    def _enrich_from_statements(self, t, f: Fundamentals) -> None:
        # Operating margin trend from annual income statements.
        try:
            fin = t.income_stmt  # columns are periods, most-recent first
            if fin is not None and fin.shape[1] >= 2:
                def margin(col):
                    rev = _row(fin, ["Total Revenue", "Operating Revenue"], col)
                    op = _row(fin, ["Operating Income", "EBIT"], col)
                    return (op / rev) if (rev and op and rev != 0) else None
                m_now, m_prev = margin(0), margin(1)
                if m_now is not None and m_prev is not None:
                    f.margin_trend = m_now - m_prev
        except Exception:
            pass

        # Share-count change (dilution) from balance sheet.
        try:
            bs = t.balance_sheet
            if bs is not None and bs.shape[1] >= 2:
                s_now = _row(bs, ["Share Issued", "Common Stock", "Ordinary Shares Number"], 0)
                s_prev = _row(bs, ["Share Issued", "Common Stock", "Ordinary Shares Number"], 1)
                if s_now and s_prev and s_prev != 0:
                    f.shares_change = (s_now - s_prev) / s_prev
        except Exception:
            pass

    def get_return_pct(self, symbol: str, lookback_days: int) -> Optional[float]:
        try:
            t = self._ticker(symbol)
            hist = t.history(period=f"{max(lookback_days + 5, 7)}d")
            if hist is None or hist.empty or len(hist) < 2:
                return None
            close = hist["Close"].dropna()
            first, last = close.iloc[0], close.iloc[-1]
            return (last - first) / first if first else None
        except Exception:
            return None


def _row(df, candidates, col_idx):
    """Pull a value from a yfinance statement df by trying several row labels."""
    for name in candidates:
        if name in df.index:
            try:
                v = df.loc[name].iloc[col_idx]
                if v is not None and not (isinstance(v, float) and math.isnan(v)):
                    return float(v)
            except Exception:
                continue
    return None


class MockProvider(MarketDataProvider):
    """Deterministic synthetic data derived from the symbol hash, so runs are
    repeatable. Lets you exercise the full pipeline with zero network."""

    def _seed(self, symbol: str) -> float:
        h = int(hashlib.md5(symbol.encode()).hexdigest(), 16)
        return (h % 1000) / 1000.0  # 0..1

    def get_fundamentals(self, symbol: str) -> Fundamentals:
        s = self._seed(symbol)
        return Fundamentals(
            symbol=symbol,
            name=f"{symbol} (mock)",
            price=round(100 + s * 3000, 2),
            market_cap=round((5000 + s * 500000) * 1e7, 0),
            revenue_growth=round(-0.05 + s * 0.45, 3),
            earnings_growth=round(-0.15 + s * 0.65, 3),
            roe=round(0.04 + s * 0.30, 3),
            debt_to_equity=round(s * 2.2, 3),
            operating_margin=round(0.02 + s * 0.30, 3),
            margin_trend=round(-0.04 + s * 0.10, 3),
            shares_change=round(max(0.0, (s - 0.7)) * 0.5, 3),  # most ~0, a few dilute
        )

    def get_return_pct(self, symbol: str, lookback_days: int) -> Optional[float]:
        s = self._seed(symbol + str(lookback_days))
        return round(-0.20 + s * 0.70, 3)  # -20%..+50%


def get_provider(use_mock: bool = False) -> MarketDataProvider:
    if use_mock:
        return MockProvider()
    try:
        return YFinanceProvider()
    except Exception:
        print("[providers] yfinance unavailable — falling back to MockProvider.")
        return MockProvider()
