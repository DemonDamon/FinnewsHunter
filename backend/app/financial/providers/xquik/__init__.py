"""Xquik Provider."""

from .fetchers.news import XquikNewsFetcher
from .provider import XquikProvider

__all__ = ["XquikProvider", "XquikNewsFetcher"]
