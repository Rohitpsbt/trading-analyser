"""
Tests for catalysts.py — NewsMonitor multi-feed path + SupplierLinkage.scan().
All network calls are mocked; no real HTTP requests are made.
"""
from __future__ import annotations
from unittest.mock import MagicMock, patch

import pytest

from catalysts import (
    NewsItem, LinkageHit, NewsMonitor, SupplierLinkage, _norm_title,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FIBRE_RSS = b"""<?xml version="1.0"?>
<rss version="2.0"><channel><title>ET Markets</title>
  <item>
    <title>Reliance Jio awards fibre rollout contract worth 500 crore</title>
    <link>https://example.com/1</link>
    <pubDate>Sun, 15 Jun 2026 10:00:00 +0530</pubDate>
  </item>
  <item>
    <title>IT sector rally: TCS and Infosys lead gains</title>
    <link>https://example.com/2</link>
    <pubDate>Sun, 15 Jun 2026 09:00:00 +0530</pubDate>
  </item>
</channel></rss>"""

_EMPTY_RSS = b"""<?xml version="1.0"?>
<rss version="2.0"><channel><title>Empty</title></channel></rss>"""


def _make_resp(content: bytes):
    """Build a context-manager mock that .read()s the given bytes."""
    resp = MagicMock()
    resp.read.return_value = content
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    return resp


# ---------------------------------------------------------------------------
# _norm_title
# ---------------------------------------------------------------------------

class TestNormTitle:
    def test_strips_punctuation_and_lowercases(self):
        assert _norm_title("Hello, World! 2026") == "helloworld2026"

    def test_empty_string(self):
        assert _norm_title("") == ""

    def test_identical_after_norm(self):
        a = _norm_title("Reliance: fibre capex order!")
        b = _norm_title("Reliance  fibre capex order")
        assert a == b


# ---------------------------------------------------------------------------
# NewsMonitor.fetch_static
# ---------------------------------------------------------------------------

class TestFetchStatic:
    def test_returns_items_on_success(self):
        with patch("urllib.request.urlopen", return_value=_make_resp(_FIBRE_RSS)):
            monitor = NewsMonitor()
            items, err = monitor.fetch_static("https://example.com/rss.cms")
        assert err is None
        assert len(items) == 2
        assert "Reliance Jio" in items[0].title

    def test_source_falls_back_to_hostname(self):
        with patch("urllib.request.urlopen", return_value=_make_resp(_FIBRE_RSS)):
            monitor = NewsMonitor()
            items, err = monitor.fetch_static("https://economictimes.indiatimes.com/rss.cms")
        assert err is None
        # source should be hostname when feed has no <source> element
        assert "economictimes" in items[0].source

    def test_returns_error_on_network_failure(self):
        with patch("urllib.request.urlopen", side_effect=OSError("timeout")):
            monitor = NewsMonitor()
            items, err = monitor.fetch_static("https://example.com/rss.cms")
        assert items == []
        assert err is not None
        assert "timeout" in err

    def test_respects_limit(self):
        with patch("urllib.request.urlopen", return_value=_make_resp(_FIBRE_RSS)):
            monitor = NewsMonitor()
            items, err = monitor.fetch_static("https://example.com/rss.cms", limit=1)
        assert err is None
        assert len(items) == 1


# ---------------------------------------------------------------------------
# NewsMonitor.fetch_all_extra
# ---------------------------------------------------------------------------

class TestFetchAllExtra:
    def test_empty_when_no_feeds_configured(self, monkeypatch):
        monkeypatch.setattr("config.NEWS_FEEDS", {"extra_rss": []})
        items, errors = NewsMonitor().fetch_all_extra()
        assert items == []
        assert errors == []

    def test_aggregates_items_across_feeds(self, monkeypatch):
        monkeypatch.setattr("config.NEWS_FEEDS", {
            "extra_rss": ["https://a.com/rss", "https://b.com/rss"],
        })
        with patch("urllib.request.urlopen", return_value=_make_resp(_FIBRE_RSS)):
            items, errors = NewsMonitor().fetch_all_extra()
        # 2 feeds × 2 items each
        assert len(items) == 4
        assert errors == []

    def test_collects_errors_without_raising(self, monkeypatch):
        monkeypatch.setattr("config.NEWS_FEEDS", {
            "extra_rss": ["https://bad.com/rss"],
        })
        with patch("urllib.request.urlopen", side_effect=OSError("refused")):
            items, errors = NewsMonitor().fetch_all_extra()
        assert items == []
        assert len(errors) == 1


# ---------------------------------------------------------------------------
# SupplierLinkage.scan — extra-feed integration
# ---------------------------------------------------------------------------

_OPTICAL_FIBRE_THEME = {
    "optical_fibre": {
        "buyers": ["Reliance Jio", "Bharti Airtel"],
        "buyer_keywords": ["fibre", "fiber", "broadband rollout"],
        "suppliers": ["HFCL", "STLTECH"],
    }
}


class TestScanExtraFeeds:
    def _monitor_with_feeds(self, extra_items: list[NewsItem], google_err="network"):
        """NewsMonitor stub: fetch() fails, fetch_all_extra() returns extra_items."""
        monitor = NewsMonitor()

        def _fake_fetch(query, limit=10):
            return [], f"google news {google_err}"

        def _fake_extra(limit_per_feed=50):
            return extra_items, []

        monitor.fetch = _fake_fetch
        monitor.fetch_all_extra = _fake_extra
        return monitor

    def test_extra_feed_hit_surfaces_suppliers(self):
        extra = [NewsItem(
            title="Reliance Jio awards fibre rollout contract worth 500 crore",
            source="ET Markets",
            published="Sun, 15 Jun 2026 10:00:00 +0530",
            link="https://example.com/1",
        )]
        monitor = self._monitor_with_feeds(extra)
        hits, errors = SupplierLinkage(monitor).scan(_OPTICAL_FIBRE_THEME)
        assert len(hits) == 1
        assert hits[0].theme == "optical_fibre"
        assert "HFCL" in hits[0].suppliers

    def test_extra_feed_item_not_matching_keywords_excluded(self):
        extra = [NewsItem(
            title="IT sector rally: TCS and Infosys lead gains",
            source="ET Markets",
            published="Sun, 15 Jun 2026 09:00:00 +0530",
            link="https://example.com/2",
        )]
        monitor = self._monitor_with_feeds(extra)
        hits, _ = SupplierLinkage(monitor).scan(_OPTICAL_FIBRE_THEME)
        assert hits == []

    def test_dedup_same_title_from_google_and_extra_feed(self):
        """Same headline from Google News AND extra feed should appear only once."""
        duplicate_title = "Reliance Jio awards fibre broadband rollout deal"
        google_item = NewsItem(title=duplicate_title, source="Google",
                               published="", link="")
        extra_item = NewsItem(title=duplicate_title, source="ET Markets",
                              published="", link="")

        monitor = NewsMonitor()
        monitor.fetch = lambda q, limit=10: ([google_item], None)
        monitor.fetch_all_extra = lambda limit_per_feed=50: ([extra_item], [])

        hits, _ = SupplierLinkage(monitor).scan(_OPTICAL_FIBRE_THEME)
        assert len(hits) == 1

    def test_buyer_attributed_when_named_in_headline(self):
        extra = [NewsItem(
            title="Bharti Airtel fibre broadband rollout deal signed",
            source="Moneycontrol",
            published="",
            link="",
        )]
        monitor = self._monitor_with_feeds(extra)
        hits, _ = SupplierLinkage(monitor).scan(_OPTICAL_FIBRE_THEME)
        assert len(hits) == 1
        assert hits[0].buyer == "Bharti Airtel"

    def test_buyer_falls_back_to_source_when_not_named(self):
        extra = [NewsItem(
            title="Telecom sector fibre broadband rollout deal worth 1000 cr",
            source="ET Markets",
            published="",
            link="",
        )]
        monitor = self._monitor_with_feeds(extra)
        hits, _ = SupplierLinkage(monitor).scan(_OPTICAL_FIBRE_THEME)
        assert len(hits) == 1
        assert hits[0].buyer == "ET Markets"

    def test_errors_from_extra_feeds_collected_not_raised(self):
        monitor = NewsMonitor()
        monitor.fetch = lambda q, limit=10: ([], "google fail")
        monitor.fetch_all_extra = lambda limit_per_feed=50: ([], ["[url] timeout"])
        _, errors = SupplierLinkage(monitor).scan(_OPTICAL_FIBRE_THEME)
        assert any("timeout" in e for e in errors)

    def test_no_extra_feed_hits_when_all_fail_demand_signal_check(self):
        extra = [NewsItem(
            title="Reliance Jio fibre network overview",  # no demand word
            source="ET Markets",
            published="",
            link="",
        )]
        monitor = self._monitor_with_feeds(extra)
        hits, _ = SupplierLinkage(monitor).scan(_OPTICAL_FIBRE_THEME)
        assert hits == []
