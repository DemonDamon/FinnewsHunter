"""
金融数据工具 - 封装为 AgenticX BaseTool

这些工具可以直接被 Agent 调用，内部使用 Provider Registry 获取数据。

设计原则:
- 继承 AgenticX BaseTool，保持与框架兼容
- 内部使用 ProviderRegistry 实现多源降级
- 返回标准化的数据格式

来源参考:
- 设计文档: research/codedeepresearch/OpenBB/FinnewsHunter_improvement_plan.md
"""
from typing import List, Optional, Dict, Any
import asyncio
import logging

from agenticx import BaseTool
from agenticx.core import ToolMetadata, ToolCategory

from .registry import get_registry, FetcherNotFoundError, ProviderNotFoundError
from .models.news import NewsQueryParams, NewsData
from .models.stock import StockQueryParams, StockPriceData, KlineInterval, AdjustType

logger = logging.getLogger(__name__)


class FinancialNewsTool(BaseTool):
    """
    金融新闻获取工具

    支持多数据源自动切换，返回标准化的新闻数据。

    Example:
        >>> tool = FinancialNewsTool()
        >>> result = await tool.aexecute(stock_codes=["600519"], limit=10)
        >>> print(result["data"])  # List[NewsData.model_dump()]
    """

    def __init__(self):
        metadata = ToolMetadata(
            name="financial_news",
            description="获取金融新闻，支持多数据源自动切换",
            category=ToolCategory.DATA_ACCESS,
            version="1.0.0"
        )
        super().__init__(metadata=metadata)

    def _setup_parameters(self):
        """设置工具参数（AgenticX BaseTool 要求的抽象方法）"""
        pass

    async def aexecute(
        self,
        keywords: Optional[List[str]] = None,
        stock_codes: Optional[List[str]] = None,
        limit: int = 50,
        provider: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        异步执行新闻获取

        Args:
            keywords: 搜索关键词列表
            stock_codes: 关联股票代码列表
            limit: 返回条数
            provider: 指定数据源

        Returns:
            {
                "success": bool,
                "count": int,
                "provider": str,
                "data": List[dict]  # NewsData.model_dump()
            }
        """
        # 构建标准查询参数
        params = NewsQueryParams(
            keywords=keywords,
            stock_codes=stock_codes,
            limit=limit
        )

        try:
            # 获取 Fetcher（自动降级）
            registry = get_registry()
            fetcher = registry.get_fetcher("news", provider)

            # 执行 TET Pipeline
            results: List[NewsData] = await fetcher.fetch(params)

            # 获取实际使用的 provider 名称
            provider_name = fetcher.__class__.__module__.split(".")[-3]

            return {
                "success": True,
                "count": len(results),
                "provider": provider_name,
                "data": [r.model_dump() for r in results]
            }

        except (FetcherNotFoundError, ProviderNotFoundError) as e:
            logger.error(f"Provider error: {e}")
            registry = get_registry()
            return {
                "success": False,
                "error": str(e),
                "available_providers": registry.get_providers_for_type("news")
            }

        except Exception as e:
            logger.exception(f"Unexpected error in FinancialNewsTool: {e}")
            return {
                "success": False,
                "error": f"Unexpected error: {e}"
            }

    def execute(
        self,
        keywords: Optional[List[str]] = None,
        stock_codes: Optional[List[str]] = None,
        limit: int = 50,
        provider: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        同步执行（包装异步方法）
        """
        return asyncio.run(self.aexecute(
            keywords=keywords,
            stock_codes=stock_codes,
            limit=limit,
            provider=provider,
            **kwargs
        ))


class StockPriceTool(BaseTool):
    """
    股票价格获取工具（K线数据）

    Example:
        >>> tool = StockPriceTool()
        >>> result = await tool.aexecute(symbol="600519", interval="1d", limit=30)
        >>> print(result["data"])  # List[StockPriceData.model_dump()]
    """

    def __init__(self):
        metadata = ToolMetadata(
            name="stock_price",
            description="获取股票K线数据，支持多数据源自动切换",
            category=ToolCategory.DATA_ACCESS,
            version="1.0.0"
        )
        super().__init__(metadata=metadata)

    def _setup_parameters(self):
        """设置工具参数（AgenticX BaseTool 要求的抽象方法）"""
        pass

    async def aexecute(
        self,
        symbol: str,
        interval: str = "1d",
        limit: int = 90,
        adjust: str = "qfq",
        provider: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        异步执行价格获取

        Args:
            symbol: 股票代码
            interval: K线周期
            limit: 返回条数
            adjust: 复权类型
            provider: 指定数据源

        Returns:
            {
                "success": bool,
                "symbol": str,
                "count": int,
                "provider": str,
                "data": List[dict]  # StockPriceData.model_dump()
            }
        """
        try:
            params = StockQueryParams(
                symbol=symbol,
                interval=KlineInterval(interval),
                limit=limit,
                adjust=AdjustType(adjust)
            )
        except ValueError as e:
            return {
                "success": False,
                "error": f"Invalid parameter: {e}"
            }

        try:
            registry = get_registry()
            fetcher = registry.get_fetcher("stock_price", provider)
            results: List[StockPriceData] = await fetcher.fetch(params)

            provider_name = fetcher.__class__.__module__.split(".")[-3]

            return {
                "success": True,
                "symbol": symbol,
                "count": len(results),
                "provider": provider_name,
                "data": [r.model_dump() for r in results]
            }

        except (FetcherNotFoundError, ProviderNotFoundError) as e:
            logger.error(f"Provider error: {e}")
            registry = get_registry()
            return {
                "success": False,
                "error": str(e),
                "available_providers": registry.get_providers_for_type("stock_price")
            }

        except Exception as e:
            logger.exception(f"Unexpected error in StockPriceTool: {e}")
            return {
                "success": False,
                "error": f"Unexpected error: {e}"
            }

    def execute(
        self,
        symbol: str,
        interval: str = "1d",
        limit: int = 90,
        adjust: str = "qfq",
        provider: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """同步执行"""
        return asyncio.run(self.aexecute(
            symbol=symbol,
            interval=interval,
            limit=limit,
            adjust=adjust,
            provider=provider,
            **kwargs
        ))


# 便捷函数：自动注册默认 Provider
def setup_default_providers():
    """
    注册默认的 Provider

    在应用启动时调用，确保 Registry 中有可用的 Provider。
    
    当前支持的数据源（按优先级排序）:
    1. sina - 新浪财经
    2. tencent - 腾讯财经
    3. nbd - 每日经济新闻
    4. eastmoney - 东方财富
    5. yicai - 第一财经
    6. 163 - 网易财经
    """
    from .providers.sina import SinaProvider
    from .providers.tencent import TencentProvider
    from .providers.nbd import NbdProvider
    from .providers.eastmoney import EastmoneyProvider
    from .providers.yicai import YicaiProvider
    from .providers.netease import NeteaseProvider

    registry = get_registry()
    
    # 定义所有 Provider（按优先级顺序）
    providers = [
        ("sina", SinaProvider),
        ("tencent", TencentProvider),
        ("nbd", NbdProvider),
        ("eastmoney", EastmoneyProvider),
        ("yicai", YicaiProvider),
        ("163", NeteaseProvider),
    ]

    # 注册所有 Provider
    for name, provider_class in providers:
        if name not in registry.list_providers():
            try:
                registry.register(provider_class())
                logger.debug(f"Registered provider: {name}")
            except Exception as e:
                logger.warning(f"Failed to register provider {name}: {e}")

    logger.info(f"Registered {len(registry.list_providers())} providers: {registry.list_providers()}")
