"""
网易财经 Provider
"""
from typing import Dict, Type

from ..base import BaseProvider, BaseFetcher, ProviderInfo
from .fetchers.news import NeteaseNewsFetcher


class NeteaseProvider(BaseProvider):
    """
    网易财经数据源

    支持的数据类型:
    - news: 财经新闻
    """

    @property
    def info(self) -> ProviderInfo:
        return ProviderInfo(
            name="163",
            display_name="网易财经",
            description="网易财经股票新闻 (money.163.com)",
            website="https://money.163.com/",
            requires_credentials=False,
            priority=6  # 第六优先级
        )

    @property
    def fetchers(self) -> Dict[str, Type[BaseFetcher]]:
        return {
            "news": NeteaseNewsFetcher,
        }
