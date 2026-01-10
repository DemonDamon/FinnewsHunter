"""
辩论历史数据模型
"""
from datetime import datetime
from typing import List, Optional
from sqlalchemy import Column, Integer, String, Text, DateTime, JSON, Index

from .database import Base


class DebateHistory(Base):
    """辩论历史表模型"""
    
    __tablename__ = "debate_histories"
    
    # 主键
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    
    # 会话标识
    session_id = Column(String(100), unique=True, nullable=False, index=True, comment="会话ID")
    
    # 股票信息
    stock_code = Column(String(20), nullable=False, index=True, comment="股票代码")
    stock_name = Column(String(100), nullable=True, comment="股票名称")
    
    # 辩论模式
    mode = Column(String(50), nullable=True, comment="辩论模式(parallel/realtime_debate/quick_analysis)")
    
    # 聊天消息（JSON数组）
    messages = Column(JSON, nullable=False, default=list, comment="聊天消息数组")
    
    # 时间信息
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")
    
    # 索引
    __table_args__ = (
        # 按股票+时间查询
        Index('idx_debate_stock_updated', 'stock_code', 'updated_at'),
    )
    
    def __repr__(self):
        return f"<DebateHistory(id={self.id}, stock_code='{self.stock_code}', session_id='{self.session_id}')>"
    
    def to_dict(self):
        """转换为字典"""
        return {
            "id": self.id,
            "session_id": self.session_id,
            "stock_code": self.stock_code,
            "stock_name": self.stock_name,
            "mode": self.mode,
            "messages": self.messages,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

