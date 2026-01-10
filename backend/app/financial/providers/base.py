"""
Provider & Fetcher 基础抽象

借鉴 OpenBB 的 TET (Transform-Extract-Transform) Pipeline:
1. Transform Query: 将标准参数转换为 Provider 特定参数
2. Extract Data: 执行实际的数据获取 (HTTP/爬虫/SDK)
3. Transform Data: 将原始数据转换为标准模型

来源参考:
- OpenBB: openbb_core.provider.abstract.fetcher.Fetcher
- 设计文档: research/codedeepresearch/OpenBB/FinnewsHunter_improvement_plan.md
"""
from abc import ABC, abstractmethod
from typing import TypeVar, Generic, Dict, Any, List, Type, Optional
from pydantic import BaseModel
from dataclasses import dataclass, field
import logging

# 泛型类型变量
QueryT = TypeVar("QueryT", bound=BaseModel)
DataT = TypeVar("DataT", bound=BaseModel)


@dataclass
class ProviderInfo:
    """
    Provider 元信息

    Attributes:
        name: 唯一标识，如 'sina', 'akshare'
        display_name: 显示名称，如 '新浪财经'
        description: 描述
        website: 官网 URL
        requires_credentials: 是否需要 API Key
        credential_keys: 需要的凭证 key 列表
        priority: 降级优先级，数字越小越优先
    """
    name: str
    display_name: str
    description: str
    website: Optional[str] = None
    requires_credentials: bool = False
    credential_keys: List[str] = field(default_factory=list)
    priority: int = 0  # 数字越小，优先级越高


class BaseFetcher(ABC, Generic[QueryT, DataT]):
    """
    数据获取器基类 - 实现 TET (Transform-Extract-Transform) Pipeline

    子类必须:
    1. 声明 query_model 和 data_model 类属性
    2. 实现 transform_query, extract_data, transform_data 三个抽象方法

    Example:
        >>> class SinaNewsFetcher(BaseFetcher[NewsQueryParams, NewsData]):
        ...     query_model = NewsQueryParams
        ...     data_model = NewsData
        ...
        ...     def transform_query(self, params):
        ...         return {"url": "...", "limit": params.limit}
        ...
        ...     async def extract_data(self, query):
        ...         return await self._fetch_html(query["url"])
        ...
        ...     def transform_data(self, raw_data, query):
        ...         return [NewsData(...) for item in raw_data]
    """

    # 子类必须声明这两个类属性
    query_model: Type[QueryT]
    data_model: Type[DataT]

    def __init__(self):
        self.logger = logging.getLogger(
            f"{self.__class__.__module__}.{self.__class__.__name__}"
        )

    @abstractmethod
    def transform_query(self, params: QueryT) -> Dict[str, Any]:
        """
        [T]ransform Query: 将标准参数转换为 Provider 特定参数

        Args:
            params: 标准查询参数 (NewsQueryParams, StockQueryParams 等)

        Returns:
            Provider 特定的参数字典

        Example:
            NewsQueryParams(stock_codes=['600519'], limit=10)
            → {'url': 'https://...', 'symbol': 'sh600519', 'count': 10}
        """
        pass

    @abstractmethod
    async def extract_data(self, query: Dict[str, Any]) -> Any:
        """
        [E]xtract Data: 执行实际的数据获取

        可以是:
        - HTTP 请求
        - 网页爬虫
        - SDK 调用
        - 数据库查询

        Args:
            query: transform_query 返回的参数字典

        Returns:
            原始数据 (任意格式，由 transform_data 处理)
        """
        pass

    @abstractmethod
    def transform_data(self, raw_data: Any, query: QueryT) -> List[DataT]:
        """
        [T]ransform Data: 将原始数据转换为标准模型

        Args:
            raw_data: extract_data 返回的原始数据
            query: 原始查询参数 (可用于补充信息)

        Returns:
            标准模型列表 (List[NewsData], List[StockPriceData] 等)
        """
        pass

    async def fetch(self, params: QueryT) -> List[DataT]:
        """
        完整的 TET 执行流程

        Args:
            params: 标准查询参数

        Returns:
            标准模型列表

        Raises:
            Exception: 任何阶段失败时抛出异常
        """
        self.logger.info(f"Fetching with params: {params.model_dump()}")

        # T: Transform Query
        query = self.transform_query(params)
        self.logger.debug(f"Transformed query: {query}")

        # E: Extract Data
        raw = await self.extract_data(query)
        raw_count = len(raw) if isinstance(raw, (list, tuple)) else 1
        self.logger.debug(f"Extracted {raw_count} raw records")

        # T: Transform Data
        results = self.transform_data(raw, params)
        self.logger.info(f"Transformed to {len(results)} standard records")

        return results

    def fetch_sync(self, params: QueryT) -> List[DataT]:
        """
        同步版本的 fetch (用于非异步环境)

        Args:
            params: 标准查询参数

        Returns:
            标准模型列表
        """
        import asyncio
        return asyncio.run(self.fetch(params))


class BaseProvider(ABC):
    """
    Provider 基类 - 定义数据源能力

    每个 Provider 可以有多个 Fetcher，每个 Fetcher 对应一种数据类型。

    Example:
        >>> class SinaProvider(BaseProvider):
        ...     @property
        ...     def info(self):
        ...         return ProviderInfo(name="sina", ...)
        ...
        ...     @property
        ...     def fetchers(self):
        ...         return {"news": SinaNewsFetcher}
    """

    @property
    @abstractmethod
    def info(self) -> ProviderInfo:
        """返回 Provider 元信息"""
        pass

    @property
    @abstractmethod
    def fetchers(self) -> Dict[str, Type[BaseFetcher]]:
        """
        返回支持的 Fetcher 映射

        Returns:
            格式: {data_type: FetcherClass}
            例如: {'news': SinaNewsFetcher, 'stock_price': SinaStockFetcher}
        """
        pass

    def get_fetcher(self, data_type: str) -> Optional[BaseFetcher]:
        """
        获取指定类型的 Fetcher 实例

        Args:
            data_type: 数据类型，如 'news', 'stock_price'

        Returns:
            Fetcher 实例，如果不支持该类型则返回 None
        """
        fetcher_cls = self.fetchers.get(data_type)
        if fetcher_cls:
            return fetcher_cls()
        return None

    def supports(self, data_type: str) -> bool:
        """
        检查是否支持某种数据类型

        Args:
            data_type: 数据类型

        Returns:
            是否支持
        """
        return data_type in self.fetchers

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name='{self.info.name}' types={list(self.fetchers.keys())}>"
