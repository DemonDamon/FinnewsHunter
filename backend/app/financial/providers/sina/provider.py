"""
新浪财经 Provider
"""
from typing import Dict, Type

from ..base import BaseProvider, BaseFetcher, ProviderInfo
from .fetchers.news import SinaNewsFetcher


class SinaProvider(BaseProvider):
    """
    新浪财经数据源

    支持的数据类型:
    - news: 财经新闻
    """

    @property
    def info(self) -> ProviderInfo:
        return ProviderInfo(
            name="sina",
            display_name="新浪财经",
            description="新浪财经新闻和股票数据",
            website="https://finance.sina.com.cn",
            requires_credentials=False,
            priority=1  # 第一优先级
        )

    @property
    def fetchers(self) -> Dict[str, Type[BaseFetcher]]:
        return {
            "news": SinaNewsFetcher,
            # 可扩展: "stock_price": SinaStockFetcher
        }
