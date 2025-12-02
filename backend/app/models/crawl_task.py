"""
爬取任务数据模型
"""
from datetime import datetime
from typing import Optional
from sqlalchemy import Column, Integer, String, DateTime, JSON, Float
from enum import Enum

from .database import Base


class CrawlMode(str, Enum):
    """爬取模式枚举"""
    COLD_START = "cold_start"      # 冷启动（批量历史）
    REALTIME = "realtime"           # 实时监控
    TARGETED = "targeted"           # 定向分析


class TaskStatus(str, Enum):
    """任务状态枚举"""
    PENDING = "pending"             # 待执行
    RUNNING = "running"             # 执行中
    COMPLETED = "completed"         # 已完成
    FAILED = "failed"               # 失败
    CANCELLED = "cancelled"         # 已取消


class CrawlTask(Base):
    """爬取任务表"""
    
    __tablename__ = "crawl_tasks"
    
    # 主键
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    
    # 任务信息
    celery_task_id = Column(String(255), unique=True, nullable=True, index=True, comment="Celery任务ID")
    mode = Column(String(20), nullable=False, index=True, comment="爬取模式")
    status = Column(String(20), nullable=False, default=TaskStatus.PENDING, index=True, comment="任务状态")
    
    # 任务配置
    source = Column(String(100), nullable=False, comment="新闻源")
    config = Column(JSON, nullable=True, comment="任务配置（JSON）")
    
    # 执行进度
    progress = Column(JSON, nullable=True, comment="进度信息")
    current_page = Column(Integer, nullable=True, comment="当前页码")
    total_pages = Column(Integer, nullable=True, comment="总页数")
    
    # 执行结果
    result = Column(JSON, nullable=True, comment="结果统计（JSON）")
    crawled_count = Column(Integer, default=0, comment="爬取到的新闻数")
    saved_count = Column(Integer, default=0, comment="保存到数据库的新闻数")
    error_message = Column(String(1000), nullable=True, comment="错误信息")
    
    # 性能指标
    execution_time = Column(Float, nullable=True, comment="执行时间（秒）")
    
    # 时间戳
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, comment="创建时间")
    started_at = Column(DateTime, nullable=True, comment="开始时间")
    completed_at = Column(DateTime, nullable=True, comment="完成时间")
    
    def __repr__(self):
        return f"<CrawlTask(id={self.id}, mode='{self.mode}', source='{self.source}', status='{self.status}')>"
    
    def to_dict(self):
        """转换为字典"""
        return {
            "id": self.id,
            "celery_task_id": self.celery_task_id,
            "mode": self.mode,
            "status": self.status,
            "source": self.source,
            "config": self.config,
            "progress": self.progress,
            "current_page": self.current_page,
            "total_pages": self.total_pages,
            "result": self.result,
            "crawled_count": self.crawled_count,
            "saved_count": self.saved_count,
            "error_message": self.error_message,
            "execution_time": self.execution_time,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }

