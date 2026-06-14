"""
Catalyst detection.

NewsMonitor   : pulls recent headlines via Google News RSS (free, no key).
SupplierLinkage: the core edge. Watch BUYER capex/order/tender signals, then
                surface linked SUPPLIERS as candidates — ideally before the
                supplier itself is in headlines.

Network note: Google News RSS is unreachable from the build sandbox, so the
methods degrade gracefully (return empty + a reason). On your machine they work.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
import ssl
import urllib.parse
import urllib.request

import config

_UA = "Mozilla/5.0 (TradingAnalyser/0.1)"

# Use certifi's CA bundle if available. Stock Python on macOS often isn't wired
# to the system trust store, so the default context throws CERTIFICATE_VERIFY_FAILED
# and silently kills the entire news feed. certifi ships transitively with
# yfinance/requests; if it's somehow missing we fall back to the default context.
try:
    import certifi
    _SSL_CTX: ssl.SSLContext | None = ssl.create_default_context(cafile=certifi.where())
except Exception:
    _SSL_CTX = None


@dataclass
class NewsItem:
    title: str
    source: str
    published: str
    link: str


@dataclass
class LinkageHit:
    theme: str
    buyer: str
    trigger_headline: str
    suppliers: list[str]
    published: str
    # Red-team field 4 ('already priced in'): filled in by the runner using price.
    supplier_already_run: dict[str, bool] = field(default_factory=dict)


class NewsMonitor:
    def __init__(self, lookback_hours: int = 72):
        self.lookback_hours = lookback_hours

    def _google_news_rss(self, query: str) -> str:
        q = urllib.parse.quote(f"{query} when:3d")
        return (f"https://news.google.com/rss/search?q={q}"
                f"&hl=en-IN&gl=IN&ceid=IN:en")

    def fetch(self, query: str, limit: int = 10) -> tuple[list[NewsItem], str | None]:
        """Returns (items, error). error is None on success."""
        import feedparser
        url = self._google_news_rss(query)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": _UA})
            with urllib.request.urlopen(req, timeout=15, context=_SSL_CTX) as resp:
                raw = resp.read()
        except Exception as e:
            return [], f"news fetch blocked/failed ({type(e).__name__}): {e}"

        feed = feedparser.parse(raw)
        items = []
        for entry in feed.entries[:limit]:
            items.append(NewsItem(
                title=getattr(entry, "title", ""),
                source=getattr(getattr(entry, "source", None), "title", "")
                       or getattr(entry, "publisher", ""),
                published=getattr(entry, "published", ""),
                link=getattr(entry, "link", ""),
            ))
        return items, None


class SupplierLinkage:
    """For each theme, search the BUYER + buyer_keywords. Any hit flags the
    theme's suppliers as candidates with the triggering headline attached."""

    def __init__(self, monitor: NewsMonitor | None = None):
        self.monitor = monitor or NewsMonitor()

    def scan(self, themes: dict | None = None) -> tuple[list[LinkageHit], list[str]]:
        themes = themes or config.LINKAGE_MAP
        hits: list[LinkageHit] = []
        errors: list[str] = []

        for theme_name, theme in themes.items():
            keywords = theme.get("buyer_keywords", [])
            for buyer in theme.get("buyers", []):
                query = f'{buyer} ({" OR ".join(keywords)})' if keywords else buyer
                items, err = self.monitor.fetch(query, limit=5)
                if err:
                    errors.append(f"[{theme_name}/{buyer}] {err}")
                    continue
                for it in items:
                    if self._is_demand_signal(it.title, keywords):
                        hits.append(LinkageHit(
                            theme=theme_name, buyer=buyer,
                            trigger_headline=it.title,
                            suppliers=theme.get("suppliers", []),
                            published=it.published or datetime.now(timezone.utc).isoformat(),
                        ))
        return hits, errors

    @staticmethod
    def _is_demand_signal(headline: str, keywords: list[str]) -> bool:
        h = headline.lower()
        demand_words = ["capex", "order", "contract", "tender", "award",
                        "expansion", "invest", "rollout", "deploy", "plant",
                        "capacity", "deal", "partnership"]
        kw_hit = any(k.lower() in h for k in keywords) if keywords else True
        return kw_hit and any(d in h for d in demand_words)
