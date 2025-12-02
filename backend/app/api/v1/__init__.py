"""
API v1 模块
"""
from fastapi import APIRouter
from . import news, analysis, tasks

# 创建主路由器
api_router = APIRouter()

# 注册子路由
api_router.include_router(news.router, prefix="/news", tags=["news"])
api_router.include_router(analysis.router, prefix="/analysis", tags=["analysis"])
api_router.include_router(tasks.router, prefix="/tasks", tags=["tasks"])

__all__ = ["api_router"]

