"""
冒烟测试: Standard Models (P0-1, P0-2)

验证:
- NewsQueryParams, NewsData 模型可正常实例化
- StockQueryParams, StockPriceData 模型可正常实例化
- 字段验证逻辑正确
- to_legacy_dict 兼容方法正常工作

运行:
    pytest -q -k "smoke_openbb_models"
"""
import pytest
from datetime import datetime


class TestNewsModels:
    """测试新闻相关模型"""

    def test_news_query_params_basic(self):
        """测试 NewsQueryParams 基本实例化"""
        from app.financial.models.news import NewsQueryParams

        # 默认参数
        params = NewsQueryParams()
        assert params.limit == 50
        assert params.keywords is None
        assert params.stock_codes is None

        # 自定义参数
        params = NewsQueryParams(
            keywords=["茅台", "白酒"],
            stock_codes=["600519"],
            limit=20
        )
        assert params.keywords == ["茅台", "白酒"]
        assert params.stock_codes == ["600519"]
        assert params.limit == 20

    def test_news_query_params_validation(self):
        """测试 NewsQueryParams 字段验证"""
        from app.financial.models.news import NewsQueryParams
        from pydantic import ValidationError

        # limit 边界测试
        params = NewsQueryParams(limit=1)
        assert params.limit == 1

        params = NewsQueryParams(limit=500)
        assert params.limit == 500

        # limit 超出范围应报错
        with pytest.raises(ValidationError):
            NewsQueryParams(limit=0)

        with pytest.raises(ValidationError):
            NewsQueryParams(limit=501)

    def test_news_data_basic(self):
        """测试 NewsData 基本实例化"""
        from app.financial.models.news import NewsData, NewsSentiment

        news = NewsData(
            id="test123",
            title="测试新闻标题",
            content="这是测试新闻的正文内容...",
            source="sina",
            source_url="https://finance.sina.com.cn/test",
            publish_time=datetime(2024, 1, 1, 10, 30)
        )

        assert news.id == "test123"
        assert news.title == "测试新闻标题"
        assert news.source == "sina"
        assert news.sentiment is None  # 可选字段默认 None
        assert news.stock_codes == []  # 默认空列表

    def test_news_data_with_sentiment(self):
        """测试 NewsData 带情感标签"""
        from app.financial.models.news import NewsData, NewsSentiment

        news = NewsData(
            id="test456",
            title="利好消息",
            content="公司业绩超预期...",
            source="sina",
            source_url="https://example.com",
            publish_time=datetime.now(),
            sentiment=NewsSentiment.POSITIVE,
            sentiment_score=0.85
        )

        assert news.sentiment == NewsSentiment.POSITIVE
        assert news.sentiment_score == 0.85

    def test_news_data_generate_id(self):
        """测试 NewsData.generate_id 方法"""
        from app.financial.models.news import NewsData

        url1 = "https://finance.sina.com.cn/news/123"
        url2 = "https://finance.sina.com.cn/news/456"

        id1 = NewsData.generate_id(url1)
        id2 = NewsData.generate_id(url2)

        # 相同 URL 生成相同 ID
        assert id1 == NewsData.generate_id(url1)
        # 不同 URL 生成不同 ID
        assert id1 != id2
        # ID 长度为 16
        assert len(id1) == 16

    def test_news_data_to_legacy_dict(self):
        """测试 NewsData.to_legacy_dict 兼容方法"""
        from app.financial.models.news import NewsData

        news = NewsData(
            id="test789",
            title="测试标题",
            content="测试内容",
            source="sina",
            source_url="https://example.com/news",
            publish_time=datetime(2024, 6, 15, 14, 30),
            author="记者",
            stock_codes=["SH600519"]
        )

        legacy = news.to_legacy_dict()

        # 验证字段映射
        assert legacy["title"] == "测试标题"
        assert legacy["url"] == "https://example.com/news"  # source_url → url
        assert legacy["source"] == "sina"
        assert legacy["author"] == "记者"
        assert "SH600519" in legacy["stock_codes"]


class TestStockModels:
    """测试股票相关模型"""

    def test_stock_query_params_basic(self):
        """测试 StockQueryParams 基本实例化"""
        from app.financial.models.stock import (
            StockQueryParams, KlineInterval, AdjustType
        )

        # 最小参数
        params = StockQueryParams(symbol="600519")
        assert params.symbol == "600519"
        assert params.interval == KlineInterval.DAILY
        assert params.adjust == AdjustType.QFQ
        assert params.limit == 90

        # 自定义参数
        params = StockQueryParams(
            symbol="SH600519",
            interval=KlineInterval.MIN_5,
            adjust=AdjustType.HFQ,
            limit=30
        )
        assert params.interval == KlineInterval.MIN_5
        assert params.adjust == AdjustType.HFQ

    def test_stock_price_data_basic(self):
        """测试 StockPriceData 基本实例化"""
        from app.financial.models.stock import StockPriceData

        price = StockPriceData(
            symbol="600519",
            date=datetime(2024, 6, 15),
            open=1500.0,
            high=1520.0,
            low=1490.0,
            close=1510.0,
            volume=1000000
        )

        assert price.symbol == "600519"
        assert price.close == 1510.0
        assert price.turnover is None  # 可选字段

    def test_stock_price_data_to_legacy_dict(self):
        """测试 StockPriceData.to_legacy_dict 兼容方法"""
        from app.financial.models.stock import StockPriceData

        price = StockPriceData(
            symbol="600519",
            date=datetime(2024, 6, 15, 10, 0, 0),
            open=1500.0,
            high=1520.0,
            low=1490.0,
            close=1510.0,
            volume=1000000,
            change_percent=0.67
        )

        legacy = price.to_legacy_dict()

        # 验证字段
        assert legacy["date"] == "2024-06-15"
        assert legacy["close"] == 1510.0
        assert legacy["change_percent"] == 0.67
        assert "timestamp" in legacy  # 应包含毫秒时间戳

    def test_kline_interval_enum(self):
        """测试 KlineInterval 枚举"""
        from app.financial.models.stock import KlineInterval

        assert KlineInterval.MIN_1.value == "1m"
        assert KlineInterval.DAILY.value == "1d"
        assert KlineInterval("1d") == KlineInterval.DAILY

    def test_adjust_type_enum(self):
        """测试 AdjustType 枚举"""
        from app.financial.models.stock import AdjustType

        assert AdjustType.QFQ.value == "qfq"
        assert AdjustType.HFQ.value == "hfq"
        assert AdjustType("none") == AdjustType.NONE
