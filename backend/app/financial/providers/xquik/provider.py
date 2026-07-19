"""Xquik Provider."""

from typing import Dict, Type

from ..base import BaseFetcher, BaseProvider, ProviderInfo
from .fetchers.news import XquikNewsFetcher


class XquikProvider(BaseProvider):
    """Xquik social signal data source."""

    @property
    def info(self) -> ProviderInfo:
        """Return provider metadata."""
        return ProviderInfo(
            name="xquik",
            display_name="Xquik",
            description="X post search results for financial news signals",
            website="https://xquik.com/",
            requires_credentials=True,
            credential_keys=["XQUIK_API_KEY"],
            priority=99,
        )

    @property
    def fetchers(self) -> Dict[str, Type[BaseFetcher]]:
        """Return supported fetcher types."""
        return {
            "news": XquikNewsFetcher,
        }
