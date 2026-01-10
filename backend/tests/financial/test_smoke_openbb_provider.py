"""
冒烟测试: Provider & Registry (P0-3, P0-4)

验证:
- BaseFetcher 抽象类可被正确继承
- BaseProvider 抽象类可被正确继承
- ProviderRegistry 注册/获取/降级逻辑
- SinaProvider 正确注册

运行:
    pytest -q -k "smoke_openbb_provider"
"""
import pytest
from typing import Dict, Any, List, Type
from datetime import datetime


class TestBaseFetcherAbstraction:
    """测试 BaseFetcher 抽象"""

    def test_fetcher_subclass_implementation(self):
        """测试 Fetcher 子类实现"""
        from app.financial.providers.base import BaseFetcher
        from app.financial.models.news import NewsQueryParams, NewsData

        class MockNewsFetcher(BaseFetcher[NewsQueryParams, NewsData]):
            query_model = NewsQueryParams
            data_model = NewsData

            def transform_query(self, params: NewsQueryParams) -> Dict[str, Any]:
                return {"limit": params.limit, "keywords": params.keywords}

            async def extract_data(self, query: Dict[str, Any]) -> List[Dict]:
                return [
                    {"title": "Test News", "content": "Content", "url": "http://test.com"}
                ]

            def transform_data(self, raw_data: List[Dict], query: NewsQueryParams) -> List[NewsData]:
                return [
                    NewsData(
                        id=f"mock_{i}",
                        title=item["title"],
                        content=item["content"],
                        source="mock",
                        source_url=item["url"],
                        publish_time=datetime.now()
                    )
                    for i, item in enumerate(raw_data)
                ]

        fetcher = MockNewsFetcher()

        # 测试 transform_query
        params = NewsQueryParams(limit=10, keywords=["test"])
        query = fetcher.transform_query(params)
        assert query["limit"] == 10
        assert query["keywords"] == ["test"]

    @pytest.mark.asyncio
    async def test_fetcher_fetch_pipeline(self):
        """测试 Fetcher 完整 TET Pipeline"""
        from app.financial.providers.base import BaseFetcher
        from app.financial.models.news import NewsQueryParams, NewsData

        class MockFetcher(BaseFetcher[NewsQueryParams, NewsData]):
            query_model = NewsQueryParams
            data_model = NewsData

            def transform_query(self, params):
                return {"count": params.limit}

            async def extract_data(self, query):
                return [{"title": f"News {i}"} for i in range(query["count"])]

            def transform_data(self, raw_data, query):
                return [
                    NewsData(
                        id=f"id_{i}",
                        title=item["title"],
                        content="content",
                        source="mock",
                        source_url="http://mock.com",
                        publish_time=datetime.now()
                    )
                    for i, item in enumerate(raw_data)
                ]

        fetcher = MockFetcher()
        params = NewsQueryParams(limit=5)
        results = await fetcher.fetch(params)

        assert len(results) == 5
        assert all(isinstance(r, NewsData) for r in results)


class TestBaseProviderAbstraction:
    """测试 BaseProvider 抽象"""

    def test_provider_subclass_implementation(self):
        """测试 Provider 子类实现"""
        from app.financial.providers.base import BaseProvider, BaseFetcher, ProviderInfo
        from app.financial.models.news import NewsQueryParams, NewsData

        class MockFetcher(BaseFetcher[NewsQueryParams, NewsData]):
            query_model = NewsQueryParams
            data_model = NewsData

            def transform_query(self, params):
                return {}

            async def extract_data(self, query):
                return []

            def transform_data(self, raw_data, query):
                return []

        class MockProvider(BaseProvider):
            @property
            def info(self) -> ProviderInfo:
                return ProviderInfo(
                    name="mock",
                    display_name="Mock Provider",
                    description="For testing",
                    priority=99
                )

            @property
            def fetchers(self) -> Dict[str, Type[BaseFetcher]]:
                return {"news": MockFetcher}

        provider = MockProvider()

        assert provider.info.name == "mock"
        assert provider.supports("news") is True
        assert provider.supports("stock_price") is False

        fetcher = provider.get_fetcher("news")
        assert fetcher is not None
        assert isinstance(fetcher, MockFetcher)


class TestProviderRegistry:
    """测试 ProviderRegistry"""

    def test_registry_singleton(self):
        """测试 Registry 单例模式"""
        from app.financial.registry import ProviderRegistry

        r1 = ProviderRegistry()
        r2 = ProviderRegistry()
        assert r1 is r2

    def test_registry_register_and_list(self):
        """测试注册和列出 Provider"""
        from app.financial.registry import reset_registry
        from app.financial.providers.base import BaseProvider, ProviderInfo, BaseFetcher
        from typing import Dict, Type

        registry = reset_registry()

        class MockProvider1(BaseProvider):
            @property
            def info(self):
                return ProviderInfo(name="p1", display_name="P1", description="", priority=2)

            @property
            def fetchers(self):
                return {}

        class MockProvider2(BaseProvider):
            @property
            def info(self):
                return ProviderInfo(name="p2", display_name="P2", description="", priority=1)

            @property
            def fetchers(self):
                return {}

        registry.register(MockProvider1())
        registry.register(MockProvider2())

        providers = registry.list_providers()
        assert "p1" in providers
        assert "p2" in providers
        # p2 优先级更高，应该在前面
        assert providers.index("p2") < providers.index("p1")

    def test_registry_get_fetcher_auto_fallback(self):
        """测试获取 Fetcher 自动降级"""
        from app.financial.registry import reset_registry, FetcherNotFoundError
        from app.financial.providers.base import BaseProvider, ProviderInfo, BaseFetcher
        from app.financial.models.news import NewsQueryParams, NewsData
        from typing import Dict, Type
        from datetime import datetime

        registry = reset_registry()

        class MockFetcher(BaseFetcher[NewsQueryParams, NewsData]):
            query_model = NewsQueryParams
            data_model = NewsData

            def transform_query(self, params):
                return {}

            async def extract_data(self, query):
                return []

            def transform_data(self, raw_data, query):
                return []

        class ProviderA(BaseProvider):
            @property
            def info(self):
                return ProviderInfo(name="a", display_name="A", description="", priority=1)

            @property
            def fetchers(self):
                return {"news": MockFetcher}

        class ProviderB(BaseProvider):
            @property
            def info(self):
                return ProviderInfo(name="b", display_name="B", description="", priority=2)

            @property
            def fetchers(self):
                return {"news": MockFetcher, "stock": MockFetcher}

        registry.register(ProviderA())
        registry.register(ProviderB())

        # 获取 news：应该返回 ProviderA 的 (优先级更高)
        fetcher = registry.get_fetcher("news")
        assert fetcher is not None

        # 获取 stock：只有 ProviderB 支持
        fetcher = registry.get_fetcher("stock")
        assert fetcher is not None

        # 获取不存在的类型
        with pytest.raises(FetcherNotFoundError):
            registry.get_fetcher("nonexistent")

    def test_registry_get_fetcher_by_name(self):
        """测试指定 Provider 名称获取 Fetcher"""
        from app.financial.registry import reset_registry, ProviderNotFoundError
        from app.financial.providers.base import BaseProvider, ProviderInfo, BaseFetcher
        from app.financial.models.news import NewsQueryParams, NewsData

        registry = reset_registry()

        class MockFetcher(BaseFetcher[NewsQueryParams, NewsData]):
            query_model = NewsQueryParams
            data_model = NewsData

            def transform_query(self, params):
                return {}

            async def extract_data(self, query):
                return []

            def transform_data(self, raw_data, query):
                return []

        class MyProvider(BaseProvider):
            @property
            def info(self):
                return ProviderInfo(name="my", display_name="My", description="")

            @property
            def fetchers(self):
                return {"news": MockFetcher}

        registry.register(MyProvider())

        # 指定存在的 Provider
        fetcher = registry.get_fetcher("news", provider="my")
        assert fetcher is not None

        # 指定不存在的 Provider
        with pytest.raises(ProviderNotFoundError):
            registry.get_fetcher("news", provider="nonexistent")


class TestSinaProvider:
    """测试 SinaProvider"""

    def test_sina_provider_info(self):
        """测试 SinaProvider 元信息"""
        from app.financial.providers.sina import SinaProvider

        provider = SinaProvider()

        assert provider.info.name == "sina"
        assert provider.info.display_name == "新浪财经"
        assert provider.supports("news") is True

    def test_sina_provider_get_news_fetcher(self):
        """测试获取 SinaNewsFetcher"""
        from app.financial.providers.sina import SinaProvider
        from app.financial.providers.sina.fetchers.news import SinaNewsFetcher

        provider = SinaProvider()
        fetcher = provider.get_fetcher("news")

        assert fetcher is not None
        assert isinstance(fetcher, SinaNewsFetcher)

    def test_sina_news_fetcher_transform_query(self):
        """测试 SinaNewsFetcher.transform_query"""
        from app.financial.providers.sina.fetchers.news import SinaNewsFetcher
        from app.financial.models.news import NewsQueryParams

        fetcher = SinaNewsFetcher()

        # 无股票代码
        params = NewsQueryParams(limit=10)
        query = fetcher.transform_query(params)
        assert query["limit"] == 10
        assert "base_url" in query

        # 有股票代码
        params = NewsQueryParams(stock_codes=["600519"], limit=20)
        query = fetcher.transform_query(params)
        assert "stock_urls" in query
        assert len(query["stock_urls"]) == 1
        assert "sh600519" in query["stock_urls"][0].lower()
