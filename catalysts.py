"""
Catalyst detection.

NewsMonitor    : pulls recent headlines from Google News RSS (search, free, no
                 key) and from supplementary Indian financial feeds (ET, MC, BS)
                 configured in config.NEWS_FEEDS["extra_rss"].
SupplierLinkage: the core edge. Watch BUYER capex/order/tender signals, then
                 surface linked SUPPLIERS as candidates — ideally before the
                 supplier itself is in headlines.

Network note: all RSS feeds are unreachable from a build sandbox, so every
method degrades gracefully (returns empty + a reason string). On your machine
they work.
"""
from __future__ import annotations
import re
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


def _norm_title(t: str) -> str:
    """Lowercase alphanumeric-only string used for cross-source dedup."""
    return re.sub(r"[^a-z0-9]", "", t.lower())


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

    # ------------------------------------------------------------------
    # Google News search (existing path — per-buyer query)
    # ------------------------------------------------------------------

    def _google_news_rss(self, query: str) -> str:
        q = urllib.parse.quote(f"{query} when:3d")
        return (f"https://news.google.com/rss/search?q={q}"
                f"&hl=en-IN&gl=IN&ceid=IN:en")

    def fetch(self, query: str, limit: int = 10) -> tuple[list[NewsItem], str | None]:
        """Search Google News RSS. Returns (items, error); error is None on success."""
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

    # ------------------------------------------------------------------
    # Static feed fetch (supplementary Indian financial RSS)
    # ------------------------------------------------------------------

    def fetch_static(self, url: str, limit: int = 50) -> tuple[list[NewsItem], str | None]:
        """Fetch a static RSS feed URL (no search query).
        Used for supplementary feeds like ET / Moneycontrol / Business Standard."""
        import feedparser
        try:
            req = urllib.request.Request(url, headers={"User-Agent": _UA})
            with urllib.request.urlopen(req, timeout=15, context=_SSL_CTX) as resp:
                raw = resp.read()
        except Exception as e:
            return [], f"feed fetch failed ({type(e).__name__}): {e}"

        hostname = urllib.parse.urlparse(url).netloc.replace("www.", "")
        feed = feedparser.parse(raw)
        items = []
        for entry in feed.entries[:limit]:
            items.append(NewsItem(
                title=getattr(entry, "title", ""),
                source=(getattr(getattr(entry, "source", None), "title", "")
                        or getattr(entry, "publisher", "")
                        or hostname),
                published=getattr(entry, "published", ""),
                link=getattr(entry, "link", ""),
            ))
        return items, None

    def fetch_all_extra(self, limit_per_feed: int = 50) -> tuple[list[NewsItem], list[str]]:
        """Batch-fetch all extra RSS feeds from config.NEWS_FEEDS.
        Returns (all_items, errors). Errors are non-fatal."""
        all_items: list[NewsItem] = []
        errors: list[str] = []
        for url in config.NEWS_FEEDS.get("extra_rss", []):
            items, err = self.fetch_static(url, limit=limit_per_feed)
            if err:
                errors.append(f"[{url}] {err}")
            else:
                all_items.extend(items)
        return all_items, errors


class SupplierLinkage:
    """For each theme, search the BUYER + buyer_keywords via Google News AND
    filter pre-fetched supplementary feeds by the same keywords. Any hit flags
    the theme's suppliers as candidates with the triggering headline attached."""

    def __init__(self, monitor: NewsMonitor | None = None):
        self.monitor = monitor or NewsMonitor()

    def scan(self, themes: dict | None = None) -> tuple[list[LinkageHit], list[str]]:
        themes = themes or config.LINKAGE_MAP
        hits: list[LinkageHit] = []
        errors: list[str] = []

        # Pre-fetch extra feeds ONCE — not repeated per buyer query (efficiency)
        extra_items, extra_errors = self.monitor.fetch_all_extra()
        errors.extend(extra_errors)

        for theme_name, theme in themes.items():
            keywords = theme.get("buyer_keywords", [])
            kw_lower = [k.lower() for k in keywords]
            buyers = theme.get("buyers", [])
            seen: set[str] = set()
            candidates: list[tuple[str, NewsItem]] = []  # (buyer_attribution, item)

            # 1. Google News search (per buyer, existing path)
            for buyer in buyers:
                query = f'{buyer} ({" OR ".join(keywords)})' if keywords else buyer
                items, err = self.monitor.fetch(query, limit=5)
                if err:
                    errors.append(f"[{theme_name}/{buyer}] {err}")
                    continue
                for it in items:
                    key = _norm_title(it.title)
                    if key and key not in seen:
                        seen.add(key)
                        candidates.append((buyer, it))

            # 2. Extra feeds: filter by theme keywords, dedup, attribute buyer
            for it in extra_items:
                h = it.title.lower()
                if not any(k in h for k in kw_lower):
                    continue
                key = _norm_title(it.title)
                if not key or key in seen:
                    continue
                seen.add(key)
                # Attribute to a buyer if named in the headline; else use feed source
                buyer_attr = next(
                    (b for b in buyers if b.lower() in h),
                    it.source or "market-feed",
                )
                candidates.append((buyer_attr, it))

            # 3. Demand-signal filter → hits
            for buyer_attr, it in candidates:
                if self._is_demand_signal(it.title, keywords):
                    hits.append(LinkageHit(
                        theme=theme_name,
                        buyer=buyer_attr,
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
