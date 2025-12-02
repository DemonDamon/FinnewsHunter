"""
股票数据模型
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Float

from .database import Base


class Stock(Base):
    """股票基本信息表"""
    
    __tablename__ = "stocks"
    
    # 主键
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    
    # 股票基本信息
    code = Column(String(20), unique=True, nullable=False, index=True, comment="股票代码（如：600519）")
    name = Column(String(100), nullable=False, comment="股票名称（如：贵州茅台）")
    full_code = Column(String(20), nullable=True, comment="完整代码（如：SH600519）")
    
    # 分类信息
    industry = Column(String(100), nullable=True, comment="所属行业")
    market = Column(String(20), nullable=True, comment="所属市场（SH:上海, SZ:深圳）")
    area = Column(String(50), nullable=True, comment="所属地区")
    
    # 财务指标（可选，后续扩展）
    pe_ratio = Column(Float, nullable=True, comment="市盈率")
    market_cap = Column(Float, nullable=True, comment="总市值")
    
    # 状态
    status = Column(String(20), default="active", comment="状态（active, suspended, delisted）")
    
    # 时间戳
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f"<Stock(code='{self.code}', name='{self.name}')>"
    
    def to_dict(self):
        """转换为字典"""
        return {
            "id": self.id,
            "code": self.code,
            "name": self.name,
            "full_code": self.full_code,
            "industry": self.industry,
            "market": self.market,
            "area": self.area,
            "pe_ratio": self.pe_ratio,
            "market_cap": self.market_cap,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

