"""
每日经济新闻 Provider
"""
from .provider import NbdProvider
from .fetchers.news import NbdNewsFetcher

__all__ = ["NbdProvider", "NbdNewsFetcher"]
