"""
分析结果数据模型
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, Float, ForeignKey, JSON
from sqlalchemy.orm import relationship

from .database import Base


class Analysis(Base):
    """智能体分析结果表"""
    
    __tablename__ = "analyses"
    
    # 主键
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    
    # 关联新闻
    news_id = Column(Integer, ForeignKey("news.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # 智能体信息
    agent_name = Column(String(100), nullable=False, comment="执行分析的智能体名称")
    agent_role = Column(String(100), nullable=True, comment="智能体角色")
    
    # 分析结果
    analysis_result = Column(Text, nullable=False, comment="分析结果（完整文本）")
    summary = Column(Text, nullable=True, comment="分析摘要")
    
    # 情感分析
    sentiment = Column(String(20), nullable=True, comment="情感倾向（positive, negative, neutral）")
    sentiment_score = Column(Float, nullable=True, comment="情感评分（-1到1）")
    confidence = Column(Float, nullable=True, comment="置信度（0到1）")
    
    # 结构化数据
    structured_data = Column(JSON, nullable=True, comment="结构化分析数据（JSON格式）")
    
    # 元数据
    execution_time = Column(Float, nullable=True, comment="执行时间（秒）")
    llm_model = Column(String(100), nullable=True, comment="使用的LLM模型")
    tokens_used = Column(Integer, nullable=True, comment="消耗的Token数")
    
    # 时间戳
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # 关系
    news = relationship("News", back_populates="analyses")
    
    def __repr__(self):
        return f"<Analysis(id={self.id}, news_id={self.news_id}, agent='{self.agent_name}')>"
    
    def to_dict(self):
        """转换为字典"""
        return {
            "id": self.id,
            "news_id": self.news_id,
            "agent_name": self.agent_name,
            "agent_role": self.agent_role,
            "analysis_result": self.analysis_result,
            "summary": self.summary,
            "sentiment": self.sentiment,
            "sentiment_score": self.sentiment_score,
            "confidence": self.confidence,
            "structured_data": self.structured_data,
            "execution_time": self.execution_time,
            "llm_model": self.llm_model,
            "tokens_used": self.tokens_used,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

