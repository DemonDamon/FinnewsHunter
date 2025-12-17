"""
新闻数据模型 - Phase 2 索引优化
"""
from datetime import datetime
from typing import List, Optional
from sqlalchemy import Column, Integer, String, Text, DateTime, Float, ARRAY, Index
from sqlalchemy.orm import relationship

from .database import Base


class News(Base):
    """新闻表模型 - Phase 2 优化版"""
    
    __tablename__ = "news"
    
    # 主键
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    
    # 基本信息
    title = Column(String(500), nullable=False, index=True, comment="新闻标题")
    content = Column(Text, nullable=False, comment="新闻正文（解析后）")
    raw_html = Column(Text, nullable=True, comment="原始HTML内容")
    url = Column(String(1000), unique=True, nullable=False, index=True, comment="新闻URL")
    source = Column(String(100), nullable=False, index=True, comment="新闻来源（sina, jrj, cnstock等）")
    
    # 时间信息
    publish_time = Column(DateTime, nullable=True, index=True, comment="发布时间")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, comment="爬取时间")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")
    
    # 关联股票
    stock_codes = Column(ARRAY(String), nullable=True, comment="关联的股票代码列表")
    
    # 情感分析
    sentiment_score = Column(Float, nullable=True, comment="情感评分（-1到1，负面到正面）")
    
    # 其他元数据
    author = Column(String(200), nullable=True, comment="作者")
    keywords = Column(ARRAY(String), nullable=True, comment="关键词")
    
    # 向量化标识
    is_embedded = Column(Integer, default=0, comment="是否已向量化（0:否, 1:是）")
    
    # 关系
    analyses = relationship("Analysis", back_populates="news", cascade="all, delete-orphan")
    
    # Phase 2: 复合索引优化（提升常见查询性能）
    __table_args__ = (
        # 按来源+时间查询（最常用）
        Index('idx_source_publish_time', 'source', 'publish_time'),
        # 按情感+时间筛选
        Index('idx_sentiment_publish_time', 'sentiment_score', 'publish_time'),
    )
    
    def __repr__(self):
        return f"<News(id={self.id}, title='{self.title[:30]}...', source='{self.source}')>"
    
    def to_dict(self, include_html: bool = False):
        """转换为字典"""
        result = {
            "id": self.id,
            "title": self.title,
            "content": self.content,
            "url": self.url,
            "source": self.source,
            "publish_time": self.publish_time.isoformat() if self.publish_time else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "stock_codes": self.stock_codes,
            "sentiment_score": self.sentiment_score,
            "author": self.author,
            "keywords": self.keywords,
            "has_raw_html": self.raw_html is not None and len(self.raw_html or '') > 0,
        }
        if include_html and self.raw_html:
            result["raw_html"] = self.raw_html
        return result

