"""
API v1 模块
"""
from fastapi import APIRouter
from . import analysis, tasks, llm_config, stocks, agents, debug, knowledge_graph
from . import news  # 原有的新闻 API（数据库操作）
from . import news_v2  # 新版 API（Provider-Fetcher 实时获取）

# 创建主路由器
api_router = APIRouter()

# 注册子路由
api_router.include_router(news.router, prefix="/news", tags=["news"])  # 原有端点
api_router.include_router(news_v2.router, prefix="/news/v2", tags=["news-v2"])  # 新版端点
api_router.include_router(analysis.router, prefix="/analysis", tags=["analysis"])
api_router.include_router(tasks.router, prefix="/tasks", tags=["tasks"])
api_router.include_router(llm_config.router, prefix="/llm", tags=["llm"])
api_router.include_router(stocks.router, prefix="/stocks", tags=["stocks"])  # Phase 2: 个股分析
api_router.include_router(agents.router, prefix="/agents", tags=["agents"])  # Phase 2: 智能体监控
api_router.include_router(debug.router, prefix="/debug", tags=["debug"])  # 调试工具
api_router.include_router(knowledge_graph.router, prefix="/knowledge-graph", tags=["knowledge-graph"])  # 知识图谱

__all__ = ["api_router"]

