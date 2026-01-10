"""
数据源 Provider 模块

每个 Provider 代表一个数据源（如 Sina, Tencent, AkShare），
每个 Provider 下可以有多个 Fetcher，每个 Fetcher 对应一种数据类型。

架构:
    Provider (数据源)
    └── Fetcher (数据获取器，实现 TET Pipeline)
        ├── transform_query: 将标准参数转换为 Provider 特定参数
        ├── extract_data: 执行实际的数据获取
        └── transform_data: 将原始数据转换为标准模型
"""
from .base import BaseProvider, BaseFetcher, ProviderInfo

__all__ = [
    "BaseProvider",
    "BaseFetcher",
    "ProviderInfo",
]
