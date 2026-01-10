"""
FinnewsHunter 金融数据层

借鉴 OpenBB 的 Provider-Fetcher 架构，提供：
1. Standard Models: 统一的数据模型 (NewsData, StockPriceData 等)
2. Provider Registry: 多数据源管理与自动降级
3. AgenticX Tools: 封装为 Agent 可调用的工具

设计原则：
- 不修改 AgenticX 核心，所有金融特定逻辑内化在本模块
- TET Pipeline: Transform Query → Extract Data → Transform Data
- 多源降级: Provider 失败时自动切换到备用源
"""
from .registry import get_registry, ProviderRegistry
from .models.news import NewsQueryParams, NewsData, NewsSentiment
from .models.stock import (
    StockQueryParams,
    StockPriceData,
    KlineInterval,
    AdjustType
)

__all__ = [
    # Registry
    "get_registry",
    "ProviderRegistry",
    # News Models
    "NewsQueryParams",
    "NewsData",
    "NewsSentiment",
    # Stock Models
    "StockQueryParams",
    "StockPriceData",
    "KlineInterval",
    "AdjustType",
]
