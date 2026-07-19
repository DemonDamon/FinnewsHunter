"""Xquik news Fetcher."""

import asyncio
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

import requests

from ...base import BaseFetcher
from ....models.news import NewsData, NewsQueryParams


class MissingXquikApiKeyError(RuntimeError):
    """Raised when the Xquik provider is selected without credentials."""


class XquikNewsFetcher(BaseFetcher[NewsQueryParams, NewsData]):
    """Xquik news signal fetcher using the lowest provider priority."""

    query_model = NewsQueryParams
    data_model = NewsData

    BASE_URL = "https://xquik.com"
    DEFAULT_QUERY = "finance OR stocks OR earnings"
    SEARCH_PATH = "/api/v1/x/tweets/search"
    SOURCE_NAME = "xquik"
    TIMEOUT_SECONDS = 60
    MAX_PAGE_SIZE = 100

    def transform_query(self, params: NewsQueryParams) -> Dict[str, Any]:
        """Convert NewsQueryParams into Xquik tweet search parameters."""
        request_params: Dict[str, Any] = {
            "limit": min(params.limit, self.MAX_PAGE_SIZE),
            "q": " OR ".join(_unique_terms(params)) or self.DEFAULT_QUERY,
        }
        if params.start_date:
            request_params["sinceTime"] = _utc_search_date(params.start_date)
        if params.end_date:
            request_params["untilTime"] = _utc_search_date(params.end_date)

        return {
            "base_url": os.getenv("XQUIK_BASE_URL", self.BASE_URL).rstrip("/"),
            "params": request_params,
            "requested_limit": params.limit,
        }

    async def extract_data(self, query: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Fetch raw tweet search results from Xquik."""
        api_key = os.getenv("XQUIK_API_KEY", "").strip()
        if not api_key:
            raise MissingXquikApiKeyError(
                "XQUIK_API_KEY is required when the Xquik provider is selected."
            )

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: self._request_tweets(query, api_key),
        )

    def _request_tweets(
        self,
        query: Dict[str, Any],
        api_key: str,
    ) -> List[Dict[str, Any]]:
        """Request tweets from the Xquik API."""
        requested_limit = int(query["requested_limit"])
        params = dict(query["params"])
        tweets: List[Dict[str, Any]] = []
        seen_cursors = set()

        while len(tweets) < requested_limit:
            params["limit"] = min(
                requested_limit - len(tweets),
                self.MAX_PAGE_SIZE,
            )
            response = requests.get(
                urljoin(str(query["base_url"]), self.SEARCH_PATH),
                headers={"x-api-key": api_key},
                params=params,
                timeout=self.TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            body = response.json()
            if not isinstance(body, dict):
                break

            page = body.get("tweets", [])
            if isinstance(page, list):
                tweets.extend(item for item in page if isinstance(item, dict))

            cursor = body.get("next_cursor") or body.get("nextCursor")
            has_more = any(
                body.get(key) is True
                for key in ("has_more", "has_next_page", "hasNextPage")
            )
            if (
                not has_more
                or not isinstance(cursor, str)
                or not cursor
                or cursor in seen_cursors
            ):
                break
            seen_cursors.add(cursor)
            params["cursor"] = cursor

        return tweets[:requested_limit]

    def transform_data(
        self,
        raw_data: List[Dict[str, Any]],
        query: NewsQueryParams,
    ) -> List[NewsData]:
        """Convert Xquik tweet records into NewsData."""
        return [
            _to_news(item, query, self.SOURCE_NAME) for item in raw_data if _text(item)
        ]


def _unique_terms(params: NewsQueryParams) -> List[str]:
    """Return unique non-empty query terms from news params."""
    values = [
        *[value.strip() for value in params.keywords or []],
        *[value.strip() for value in params.stock_codes or []],
    ]
    return list(dict.fromkeys(value for value in values if value))


def _utc_search_date(value: datetime) -> str:
    """Return an ISO date after deterministic UTC normalization."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    else:
        value = value.astimezone(timezone.utc)
    return value.date().isoformat()


def _to_news(item: Dict[str, Any], query: NewsQueryParams, source: str) -> NewsData:
    """Convert one Xquik tweet record into NewsData."""
    text = _text(item)
    url = _tweet_url(item)
    return NewsData(
        id=NewsData.generate_id(url),
        title=_title(item, text),
        content=text,
        source=source,
        source_url=url,
        publish_time=_publish_time(item),
        stock_codes=query.stock_codes or [],
        keywords=query.keywords or [],
        author=_author_name(item),
        extra={"tweet_id": _string_value(item, "id")},
    )


def _tweet_url(item: Dict[str, Any]) -> str:
    """Return the tweet URL or a stable fallback URL."""
    url = _string_value(item, "url")
    if url:
        return url
    tweet_id = _string_value(item, "id") or "unknown"
    return f"https://x.com/i/status/{tweet_id}"


def _title(item: Dict[str, Any], text: str) -> str:
    """Build a compact NewsData title from tweet text."""
    username = _author_username(item)
    prefix = f"@{username}: " if username else "X post: "
    return f"{prefix}{' '.join(text.split())[:100]}"


def _publish_time(item: Dict[str, Any]) -> datetime:
    """Parse the tweet creation time."""
    value = item.get("created")
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, timezone.utc)

    for key in ("created", "created_at", "createdAt"):
        value = _string_value(item, key)
        if not value:
            continue
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            continue
    return datetime.now(timezone.utc)


def _author_name(item: Dict[str, Any]) -> Optional[str]:
    """Return the tweet author's display name when present."""
    author = _author(item)
    value = author.get("name")
    return value if isinstance(value, str) and value else _author_username(item)


def _author_username(item: Dict[str, Any]) -> Optional[str]:
    """Return the tweet author's username when present."""
    author = _author(item)
    for key in ("username", "userName", "screen_name"):
        value = author.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _author(item: Dict[str, Any]) -> Dict[str, Any]:
    """Return the nested author record when present."""
    author = item.get("author")
    return author if isinstance(author, dict) else {}


def _text(item: Dict[str, Any]) -> str:
    """Return tweet text when present."""
    return _string_value(item, "text")


def _string_value(item: Dict[str, Any], key: str) -> str:
    """Return a string field or an empty string."""
    value = item.get(key)
    return value if isinstance(value, str) else ""
