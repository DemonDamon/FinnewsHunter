"""
腾讯财经 Provider
"""
from typing import Dict, Type

from ..base import BaseProvider, BaseFetcher, ProviderInfo
from .fetchers.news import TencentNewsFetcher


class TencentProvider(BaseProvider):
    """
    腾讯财经数据源

    支持的数据类型:
    - news: 财经新闻
    """

    @property
    def info(self) -> ProviderInfo:
        return ProviderInfo(
            name="tencent",
            display_name="腾讯财经",
            description="腾讯财经新闻 (news.qq.com)",
            website="https://news.qq.com/ch/finance/",
            requires_credentials=False,
            priority=2  # 第二优先级
        )

    @property
    def fetchers(self) -> Dict[str, Type[BaseFetcher]]:
        return {
            "news": TencentNewsFetcher,
        }
