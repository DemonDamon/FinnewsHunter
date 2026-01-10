"""
东方财富 Provider
"""
from typing import Dict, Type

from ..base import BaseProvider, BaseFetcher, ProviderInfo
from .fetchers.news import EastmoneyNewsFetcher


class EastmoneyProvider(BaseProvider):
    """
    东方财富数据源

    支持的数据类型:
    - news: 财经新闻
    """

    @property
    def info(self) -> ProviderInfo:
        return ProviderInfo(
            name="eastmoney",
            display_name="东方财富",
            description="东方财富股票新闻 (eastmoney.com)",
            website="https://stock.eastmoney.com/",
            requires_credentials=False,
            priority=4  # 第四优先级
        )

    @property
    def fetchers(self) -> Dict[str, Type[BaseFetcher]]:
        return {
            "news": EastmoneyNewsFetcher,
        }
