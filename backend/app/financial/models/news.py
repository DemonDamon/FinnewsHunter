"""
金融新闻标准模型

借鉴 OpenBB Standard Models 设计:
- NewsQueryParams: 新闻查询参数标准模型
- NewsData: 新闻数据标准模型

所有 NewsProvider 的 Fetcher 都接收 NewsQueryParams 作为输入，
返回 List[NewsData] 作为输出，确保不同数据源返回的数据格式一致。

来源参考:
- OpenBB: openbb_core.provider.standard_models
- 设计文档: research/codedeepresearch/OpenBB/FinnewsHunter_improvement_plan.md
"""
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List
from enum import Enum
import hashlib


class NewsSentiment(str, Enum):
    """新闻情感标签"""
    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"


class NewsQueryParams(BaseModel):
    """
    新闻查询参数标准模型

    所有 NewsProvider 的 Fetcher 都接收此模型作为输入，
    内部再转换为各自 API 的参数格式 (transform_query)。

    Example:
        >>> params = NewsQueryParams(stock_codes=["600519"], limit=10)
        >>> fetcher.fetch(params)  # 返回 List[NewsData]
    """
    keywords: Optional[List[str]] = Field(
        default=None,
        description="搜索关键词列表"
    )
    stock_codes: Optional[List[str]] = Field(
        default=None,
        description="关联股票代码列表，如 ['600519', '000001']"
    )
    start_date: Optional[datetime] = Field(
        default=None,
        description="新闻发布时间起始"
    )
    end_date: Optional[datetime] = Field(
        default=None,
        description="新闻发布时间截止"
    )
    limit: int = Field(
        default=50,
        ge=1,
        le=500,
        description="返回条数上限"
    )
    source_filter: Optional[List[str]] = Field(
        default=None,
        description="数据源过滤，如 ['sina', 'tencent']"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "stock_codes": ["600519", "000001"],
                "limit": 20,
                "keywords": ["茅台", "白酒"]
            }
        }


class NewsData(BaseModel):
    """
    新闻数据标准模型

    所有 Provider 返回的数据都必须转换为此模型，
    确保上层 Agent 处理逻辑一致。

    设计原则:
    - 必填字段: id, title, content, source, source_url, publish_time
    - 可选字段: summary, sentiment 等 (可由 LLM 后续填充)
    - extra 字段: 存储 Provider 特有的额外数据
    """
    id: str = Field(..., description="新闻唯一标识 (建议用 URL 的 MD5)")
    title: str = Field(..., description="新闻标题")
    content: str = Field(..., description="新闻正文")
    summary: Optional[str] = Field(default=None, description="摘要（可由 LLM 生成）")
    source: str = Field(..., description="来源网站名称，如 'sina', 'tencent'")
    source_url: str = Field(..., description="原文链接")
    publish_time: datetime = Field(..., description="发布时间")
    crawl_time: Optional[datetime] = Field(
        default_factory=datetime.now,
        description="抓取时间"
    )

    # 关联信息
    stock_codes: List[str] = Field(
        default_factory=list,
        description="关联股票代码，如 ['SH600519', 'SZ000001']"
    )
    stock_names: List[str] = Field(
        default_factory=list,
        description="关联股票名称，如 ['贵州茅台', '平安银行']"
    )

    # 情感分析（可选，由 Agent 或 LLM 填充）
    sentiment: Optional[NewsSentiment] = Field(
        default=None,
        description="情感标签"
    )
    sentiment_score: Optional[float] = Field(
        default=None,
        ge=-1,
        le=1,
        description="情感分数：-1(极度负面) ~ 1(极度正面)"
    )

    # 原始数据（可选）
    keywords: List[str] = Field(
        default_factory=list,
        description="关键词列表"
    )
    author: Optional[str] = Field(default=None, description="作者")

    # 元数据
    extra: dict = Field(
        default_factory=dict,
        description="Provider 特有的额外字段"
    )

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
        json_schema_extra = {
            "example": {
                "id": "a1b2c3d4e5f6",
                "title": "贵州茅台2024年三季度业绩超预期",
                "content": "贵州茅台发布2024年三季度报告...",
                "source": "sina",
                "source_url": "https://finance.sina.com.cn/stock/...",
                "publish_time": "2024-10-30T10:30:00",
                "stock_codes": ["SH600519"],
                "sentiment": "positive",
                "sentiment_score": 0.8
            }
        }

    @staticmethod
    def generate_id(url: str) -> str:
        """根据 URL 生成唯一 ID"""
        return hashlib.md5(url.encode()).hexdigest()[:16]

    def to_legacy_dict(self) -> dict:
        """
        转换为旧版 NewsItem 格式 (兼容现有代码)

        Returns:
            与旧版 NewsItem.to_dict() 格式一致的字典
        """
        return {
            "title": self.title,
            "content": self.content,
            "url": self.source_url,
            "source": self.source,
            "publish_time": self.publish_time.isoformat() if self.publish_time else None,
            "author": self.author,
            "keywords": self.keywords,
            "stock_codes": self.stock_codes,
            "summary": self.summary,
            "raw_html": self.extra.get("raw_html"),
        }
