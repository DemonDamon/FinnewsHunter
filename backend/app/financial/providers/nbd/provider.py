"""
每日经济新闻 Provider
"""
from typing import Dict, Type

from ..base import BaseProvider, BaseFetcher, ProviderInfo
from .fetchers.news import NbdNewsFetcher


class NbdProvider(BaseProvider):
    """
    每日经济新闻数据源

    支持的数据类型:
    - news: 财经新闻
    """

    @property
    def info(self) -> ProviderInfo:
        return ProviderInfo(
            name="nbd",
            display_name="每日经济新闻",
            description="每日经济新闻 (nbd.com.cn)",
            website="https://www.nbd.com.cn/",
            requires_credentials=False,
            priority=3  # 第三优先级
        )

    @property
    def fetchers(self) -> Dict[str, Type[BaseFetcher]]:
        return {
            "news": NbdNewsFetcher,
        }
