"""Tests for the optional Xquik financial news provider."""

import asyncio
import logging
from datetime import datetime, timezone

import pytest

QUERY_LIMIT = 12


def test_xquik_provider_info():
    """Xquik provider advertises the expected registry metadata."""
    from app.financial.providers.xquik import XquikProvider

    provider = XquikProvider()

    assert provider.info.name == "xquik"
    assert provider.info.requires_credentials is True
    assert "news" in provider.fetchers


def test_xquik_transform_query_uses_keywords_and_stock_codes(monkeypatch):
    """Query transformation combines terms without exposing credentials."""
    from app.financial.models.news import NewsQueryParams
    from app.financial.providers.xquik.fetchers.news import XquikNewsFetcher

    monkeypatch.setenv("XQUIK_API_KEY", "test-key")
    monkeypatch.setenv("XQUIK_BASE_URL", "https://example.com/")

    fetcher = XquikNewsFetcher()
    params = NewsQueryParams(
        keywords=["AI", "earnings"],
        stock_codes=["AAPL"],
        limit=QUERY_LIMIT,
        start_date=datetime(2026, 1, 1),
        end_date=datetime(2026, 1, 31, 23, 59),
    )

    query = fetcher.transform_query(params)

    assert "api_key" not in query
    assert query["base_url"] == "https://example.com"
    assert query["params"]["q"] == "AI OR earnings OR AAPL"
    assert query["params"]["limit"] == QUERY_LIMIT
    assert query["params"]["sinceTime"] == "2026-01-01"
    assert query["params"]["untilTime"] == "2026-01-31"


def test_xquik_transform_query_normalizes_timezone_offsets(monkeypatch):
    """Date filters use UTC dates regardless of host or input timezone."""
    from app.financial.models.news import NewsQueryParams
    from app.financial.providers.xquik.fetchers.news import XquikNewsFetcher

    monkeypatch.setenv("XQUIK_API_KEY", "test-key")

    query = XquikNewsFetcher().transform_query(
        NewsQueryParams(
            start_date=datetime.fromisoformat("2026-01-02T23:30:00-05:00"),
            end_date=datetime.fromisoformat("2026-01-04T00:30:00+05:00"),
        )
    )

    assert query["params"]["sinceTime"] == "2026-01-03"
    assert query["params"]["untilTime"] == "2026-01-03"


def test_xquik_transform_query_caps_page_size(monkeypatch):
    """Large requests are split into API-compatible pages."""
    from app.financial.models.news import NewsQueryParams
    from app.financial.providers.xquik.fetchers.news import XquikNewsFetcher

    monkeypatch.setenv("XQUIK_API_KEY", " test-key ")

    query = XquikNewsFetcher().transform_query(NewsQueryParams(limit=250))

    assert "api_key" not in query
    assert query["params"]["limit"] == 100
    assert query["requested_limit"] == 250


def test_xquik_extract_requires_api_key(monkeypatch):
    """The provider fails clearly when selected without credentials."""
    from app.financial.models.news import NewsQueryParams
    from app.financial.providers.xquik.fetchers.news import XquikNewsFetcher

    monkeypatch.delenv("XQUIK_API_KEY", raising=False)

    fetcher = XquikNewsFetcher()
    query = fetcher.transform_query(NewsQueryParams(keywords=["market"]))

    with pytest.raises(RuntimeError, match="XQUIK_API_KEY is required"):
        asyncio.run(fetcher.extract_data(query))


def test_xquik_extract_rejects_blank_api_key(monkeypatch):
    """Whitespace-only credentials fail before making a request."""
    from app.financial.models.news import NewsQueryParams
    from app.financial.providers.xquik.fetchers.news import XquikNewsFetcher

    monkeypatch.setenv("XQUIK_API_KEY", "   ")

    fetcher = XquikNewsFetcher()
    query = fetcher.transform_query(NewsQueryParams(keywords=["market"]))

    with pytest.raises(RuntimeError, match="XQUIK_API_KEY is required"):
        asyncio.run(fetcher.extract_data(query))


def test_xquik_fetch_does_not_log_api_key(monkeypatch, caplog):
    """Base fetcher diagnostics never receive the API credential."""
    from app.financial.models.news import NewsQueryParams
    from app.financial.providers.xquik.fetchers.news import XquikNewsFetcher

    monkeypatch.setenv("XQUIK_API_KEY", "redacted-test-value")
    fetcher = XquikNewsFetcher()
    monkeypatch.setattr(fetcher, "_request_tweets", lambda _query, _api_key: [])

    with caplog.at_level(logging.DEBUG):
        asyncio.run(fetcher.fetch(NewsQueryParams(keywords=["market"])))

    assert "redacted-test-value" not in caplog.text


def test_xquik_request_follows_pagination(monkeypatch):
    """The provider collects enough pages to honor the requested limit."""
    from app.financial.models.news import NewsQueryParams
    from app.financial.providers.xquik.fetchers.news import XquikNewsFetcher

    calls = []
    pages = [
        {
            "tweets": [{"id": str(index)} for index in range(100)],
            "has_next_page": True,
            "next_cursor": "page-2",
        },
        {
            "tweets": [{"id": str(index)} for index in range(100, 200)],
            "has_more": True,
            "nextCursor": "page-3",
        },
        {
            "tweets": [{"id": str(index)} for index in range(200, 260)],
            "has_more": False,
            "next_cursor": "",
        },
    ]

    class FakeResponse:
        """Return one configured response body to the fetcher."""

        def __init__(self, body):
            self.body = body

        @staticmethod
        def raise_for_status():
            """Accept the fake response as successful."""
            return None

        def json(self):
            """Return the configured JSON response body."""
            return self.body

    def fake_get(_url, *, headers, params, timeout):
        """Record one request and return the next response page."""
        calls.append({"headers": headers, "params": dict(params), "timeout": timeout})
        return FakeResponse(pages[len(calls) - 1])

    monkeypatch.setattr("requests.get", fake_get)
    monkeypatch.setenv("XQUIK_API_KEY", "test-key")

    fetcher = XquikNewsFetcher()
    query = fetcher.transform_query(NewsQueryParams(limit=250))
    tweets = fetcher._request_tweets(query, "test-key")

    assert len(tweets) == 250
    assert [call["params"]["limit"] for call in calls] == [100, 100, 50]
    assert [call["params"].get("cursor") for call in calls] == [
        None,
        "page-2",
        "page-3",
    ]
    assert all(call["headers"] == {"x-api-key": "test-key"} for call in calls)
    assert all(call["timeout"] == 60 for call in calls)


def test_xquik_request_stops_on_repeated_cursor(monkeypatch):
    """A malformed repeated cursor cannot cause an unbounded request loop."""
    from app.financial.models.news import NewsQueryParams
    from app.financial.providers.xquik.fetchers.news import XquikNewsFetcher

    call_count = 0

    class FakeResponse:
        """Return a successful page with a repeated cursor."""

        @staticmethod
        def raise_for_status():
            """Accept the fake response as successful."""
            return None

        @staticmethod
        def json():
            """Return a page that repeats its pagination cursor."""
            return {
                "tweets": [],
                "has_next_page": True,
                "next_cursor": "repeated",
            }

    def fake_get(_url, *, headers, params, timeout):
        """Count requests and return the repeated-cursor response."""
        nonlocal call_count
        call_count += 1
        return FakeResponse()

    monkeypatch.setattr("requests.get", fake_get)
    monkeypatch.setenv("XQUIK_API_KEY", "test-key")

    fetcher = XquikNewsFetcher()
    query = fetcher.transform_query(NewsQueryParams(limit=2))

    assert fetcher._request_tweets(query, "test-key") == []
    assert call_count == 2


def test_xquik_transform_data_maps_tweets_to_news():
    """Tweet search records are normalized into NewsData items."""
    from app.financial.models.news import NewsQueryParams
    from app.financial.providers.xquik.fetchers.news import XquikNewsFetcher

    fetcher = XquikNewsFetcher()
    params = NewsQueryParams(keywords=["market"], stock_codes=["TSLA"], limit=1)
    results = fetcher.transform_data(
        [
            {
                "id": "123",
                "text": "TSLA earnings discussion is moving fast.",
                "created": "2026-01-02T03:04:05Z",
                "url": "https://x.com/example/status/123",
                "author": {"username": "example", "name": "Example"},
            }
        ],
        params,
    )

    assert len(results) == 1
    assert results[0].source == "xquik"
    assert results[0].source_url == "https://x.com/example/status/123"
    assert results[0].stock_codes == ["TSLA"]
    assert results[0].keywords == ["market"]
    assert results[0].author == "Example"
    assert results[0].extra["tweet_id"] == "123"


def test_xquik_transform_data_parses_unix_timestamp():
    """Current API Unix timestamps map to timezone-aware datetimes."""
    from app.financial.models.news import NewsQueryParams
    from app.financial.providers.xquik.fetchers.news import XquikNewsFetcher

    results = XquikNewsFetcher().transform_data(
        [{"id": "123", "text": "Market update", "created": 1_767_225_600}],
        NewsQueryParams(limit=1),
    )

    assert results[0].publish_time == datetime(2026, 1, 1, tzinfo=timezone.utc)


def test_xquik_transform_data_parses_camel_case_timestamp():
    """Current camelCase creation times map to timezone-aware datetimes."""
    from app.financial.models.news import NewsQueryParams
    from app.financial.providers.xquik.fetchers.news import XquikNewsFetcher

    results = XquikNewsFetcher().transform_data(
        [
            {
                "id": "123",
                "text": "Market update",
                "createdAt": "2026-01-02T03:04:05Z",
            }
        ],
        NewsQueryParams(limit=1),
    )

    assert results[0].publish_time == datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
