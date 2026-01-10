"""
腾讯财经 Provider
"""
from .provider import TencentProvider
from .fetchers.news import TencentNewsFetcher

__all__ = ["TencentProvider", "TencentNewsFetcher"]
