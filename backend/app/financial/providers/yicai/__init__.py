"""
第一财经 Provider
"""
from .provider import YicaiProvider
from .fetchers.news import YicaiNewsFetcher

__all__ = ["YicaiProvider", "YicaiNewsFetcher"]
