"""
东方财富 Provider
"""
from .provider import EastmoneyProvider
from .fetchers.news import EastmoneyNewsFetcher

__all__ = ["EastmoneyProvider", "EastmoneyNewsFetcher"]
