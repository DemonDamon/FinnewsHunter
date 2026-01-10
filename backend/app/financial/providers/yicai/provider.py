"""
第一财经 Provider
"""
from typing import Dict, Type

from ..base import BaseProvider, BaseFetcher, ProviderInfo
from .fetchers.news import YicaiNewsFetcher


class YicaiProvider(BaseProvider):
    """
    第一财经数据源

    支持的数据类型:
    - news: 财经新闻
    """

    @property
    def info(self) -> ProviderInfo:
        return ProviderInfo(
            name="yicai",
            display_name="第一财经",
            description="第一财经股市新闻 (yicai.com)",
            website="https://www.yicai.com/",
            requires_credentials=False,
            priority=5  # 第五优先级
        )

    @property
    def fetchers(self) -> Dict[str, Type[BaseFetcher]]:
        return {
            "news": YicaiNewsFetcher,
        }
