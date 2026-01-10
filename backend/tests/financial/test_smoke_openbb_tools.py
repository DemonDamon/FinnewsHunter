"""
冒烟测试: Financial Tools (P1-2)

验证:
- FinancialNewsTool 可正常实例化
- Tool 在无 Provider 时返回错误而非崩溃
- Tool 正确调用 Registry

运行:
    pytest -q -k "smoke_openbb_tools"
"""
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from datetime import datetime


class TestFinancialNewsTool:
    """测试 FinancialNewsTool"""

    def test_tool_instantiation(self):
        """测试工具实例化"""
        from app.financial.tools import FinancialNewsTool

        tool = FinancialNewsTool()

        assert tool.name == "financial_news"
        assert "金融新闻" in tool.description or "news" in tool.description.lower()

    def test_tool_has_required_methods(self):
        """测试工具具有必要方法"""
        from app.financial.tools import FinancialNewsTool

        tool = FinancialNewsTool()

        assert hasattr(tool, "execute")
        assert hasattr(tool, "aexecute")
        assert callable(tool.execute)
        assert callable(tool.aexecute)

    @pytest.mark.asyncio
    async def test_tool_returns_error_when_no_provider(self):
        """测试无 Provider 时返回错误"""
        from app.financial.tools import FinancialNewsTool
        from app.financial.registry import reset_registry

        # 清空 Registry
        reset_registry()

        tool = FinancialNewsTool()
        result = await tool.aexecute(limit=10)

        # 应返回错误而非崩溃
        assert result["success"] is False
        assert "error" in result

    @pytest.mark.asyncio
    async def test_tool_with_mocked_fetcher(self):
        """测试工具与 Mock Fetcher 集成"""
        from app.financial.tools import FinancialNewsTool
        from app.financial.registry import reset_registry, get_registry
        from app.financial.providers.base import BaseProvider, ProviderInfo, BaseFetcher
        from app.financial.models.news import NewsQueryParams, NewsData

        registry = reset_registry()

        # 创建 Mock Fetcher
        class MockFetcher(BaseFetcher[NewsQueryParams, NewsData]):
            query_model = NewsQueryParams
            data_model = NewsData

            def transform_query(self, params):
                return {"limit": params.limit}

            async def extract_data(self, query):
                return [
                    {"title": "Mock News 1", "content": "Content 1", "url": "http://mock1.com"},
                    {"title": "Mock News 2", "content": "Content 2", "url": "http://mock2.com"},
                ]

            def transform_data(self, raw_data, query):
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

        class MockProvider(BaseProvider):
            @property
            def info(self):
                return ProviderInfo(name="mock", display_name="Mock", description="")

            @property
            def fetchers(self):
                return {"news": MockFetcher}

        registry.register(MockProvider())

        tool = FinancialNewsTool()
        result = await tool.aexecute(limit=10)

        assert result["success"] is True
        assert result["count"] == 2
        assert len(result["data"]) == 2
        assert result["data"][0]["title"] == "Mock News 1"


class TestStockPriceTool:
    """测试 StockPriceTool"""

    def test_tool_instantiation(self):
        """测试工具实例化"""
        from app.financial.tools import StockPriceTool

        tool = StockPriceTool()

        assert tool.name == "stock_price"
        assert "K线" in tool.description or "price" in tool.description.lower()

    @pytest.mark.asyncio
    async def test_tool_returns_error_for_invalid_interval(self):
        """测试无效参数时返回错误"""
        from app.financial.tools import StockPriceTool

        tool = StockPriceTool()
        result = await tool.aexecute(symbol="600519", interval="invalid_interval")

        assert result["success"] is False
        assert "error" in result

    @pytest.mark.asyncio
    async def test_tool_returns_error_when_no_provider(self):
        """测试无 Provider 时返回错误"""
        from app.financial.tools import StockPriceTool
        from app.financial.registry import reset_registry

        reset_registry()

        tool = StockPriceTool()
        result = await tool.aexecute(symbol="600519")

        assert result["success"] is False
        assert "error" in result


class TestSetupDefaultProviders:
    """测试默认 Provider 设置"""

    def test_setup_registers_sina(self):
        """测试 setup_default_providers 注册 SinaProvider"""
        from app.financial.registry import reset_registry, get_registry
        from app.financial.tools import setup_default_providers

        registry = reset_registry()
        assert "sina" not in registry.list_providers()

        setup_default_providers()

        assert "sina" in registry.list_providers()

    def test_setup_idempotent(self):
        """测试 setup_default_providers 幂等性"""
        from app.financial.registry import reset_registry, get_registry
        from app.financial.tools import setup_default_providers

        reset_registry()

        # 多次调用不应报错
        setup_default_providers()
        setup_default_providers()
        setup_default_providers()

        registry = get_registry()
        assert registry.list_providers().count("sina") == 1
