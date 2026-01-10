"""
网易财经 Provider
"""
from .provider import NeteaseProvider
from .fetchers.news import NeteaseNewsFetcher

__all__ = ["NeteaseProvider", "NeteaseNewsFetcher"]
