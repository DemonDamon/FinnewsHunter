"""
金融数据标准模型

借鉴 OpenBB Standard Models 设计:
- QueryParams: 定义标准输入参数
- Data: 定义标准输出字段

所有 Provider 的 Fetcher 都使用这些标准模型，确保数据格式一致。
"""
from .news import NewsQueryParams, NewsData, NewsSentiment
from .stock import StockQueryParams, StockPriceData, KlineInterval, AdjustType

__all__ = [
    "NewsQueryParams",
    "NewsData",
    "NewsSentiment",
    "StockQueryParams",
    "StockPriceData",
    "KlineInterval",
    "AdjustType",
]
