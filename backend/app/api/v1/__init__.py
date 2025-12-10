"""
API v1 模块
"""
from fastapi import APIRouter
from . import analysis, tasks, llm_config
from . import news_v2 as news  # Phase 2: 使用升级版 API

# 创建主路由器
api_router = APIRouter()

# 注册子路由
api_router.include_router(news.router, prefix="/news", tags=["news"])
api_router.include_router(analysis.router, prefix="/analysis", tags=["analysis"])
api_router.include_router(tasks.router, prefix="/tasks", tags=["tasks"])
api_router.include_router(llm_config.router, prefix="/llm", tags=["llm"])

__all__ = ["api_router"]

