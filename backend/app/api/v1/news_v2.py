"""
新闻管理 API 路由 - Phase 2 升级版
移除 start_page/end_page，改为自动刷新机制
"""
import logging
from typing import List, Optional
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, and_

from ...core.database import get_db
from ...core.redis_client import redis_client
from ...core.config import settings
from ...models.news import News
from ...tasks.crawl_tasks import realtime_crawl_task

logger = logging.getLogger(__name__)

router = APIRouter()


# ========== 爬虫源配置 ==========

AVAILABLE_SOURCES = {
    "sina": {"name": "新浪财经", "url": "https://finance.sina.com.cn/"},
    "tencent": {"name": "腾讯财经", "url": "https://finance.qq.com/"},
    "jwview": {"name": "金融界", "url": "http://www.jrj.com.cn/"},
    "eeo": {"name": "经济观察网", "url": "https://www.eeo.com.cn/jg/jinrong/zhengquan/"},
    "caijing": {"name": "财经网", "url": "https://finance.caijing.com.cn/"},
    "jingji21": {"name": "21经济网", "url": "https://www.21jingji.com/channel/capital/"},
    "nbd": {"name": "每日经济新闻", "url": "https://www.nbd.com.cn/columns/3/"},
    "yicai": {"name": "第一财经", "url": "https://www.yicai.com/news/gushi/"},
    "163": {"name": "网易财经", "url": "https://money.163.com/"},
    "eastmoney": {"name": "东方财富", "url": "https://stock.eastmoney.com/"},
}


# ========== Pydantic Models ==========

class NewsResponse(BaseModel):
    """新闻响应模型"""
    model_config = {"from_attributes": True}
    
    id: int
    title: str
    content: str
    url: str
    source: str
    publish_time: Optional[datetime] = None
    stock_codes: Optional[List[str]] = None
    sentiment_score: Optional[float] = None
    created_at: datetime
    has_raw_html: bool = False  # 是否有原始 HTML


class NewsHtmlResponse(BaseModel):
    """新闻原始 HTML 响应"""
    id: int
    title: str
    url: str
    raw_html: Optional[str] = None
    has_raw_html: bool = False


class LatestNewsResponse(BaseModel):
    """最新新闻列表响应"""
    success: bool
    data: List[NewsResponse]
    total: int
    from_cache: bool
    cache_age: Optional[float] = None
    message: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class ForceRefreshResponse(BaseModel):
    """强制刷新响应"""
    success: bool
    message: str
    task_id: Optional[str] = None
    new_count: int = 0


# ========== API Endpoints ==========

@router.get("/sources", summary="获取所有可用的爬虫源")
async def get_available_sources():
    """
    获取所有可用的新闻爬虫源
    
    返回所有已配置的新闻源列表，包括：
    - 源标识（source key）
    - 显示名称
    - 目标URL
    """
    return {
        "success": True,
        "data": [
            {
                "key": key,
                "name": info["name"],
                "url": info["url"]
            }
            for key, info in AVAILABLE_SOURCES.items()
        ],
        "total": len(AVAILABLE_SOURCES),
        "message": f"返回 {len(AVAILABLE_SOURCES)} 个可用新闻源"
    }


@router.get("/latest", response_model=LatestNewsResponse, summary="获取最新新闻（智能缓存）")
async def get_latest_news(
    source: Optional[str] = Query(None, description="新闻源（不传则返回所有来源）"),
    limit: int = Query(50, le=200, description="返回数量"),
    force_refresh: bool = Query(False, description="是否强制刷新（跳过缓存）"),
    db: AsyncSession = Depends(get_db)
):
    """
    获取最新新闻列表 (Phase 2 核心接口)
    
    **工作流程**：
    1. 默认从数据库查询最新新闻
    2. force_refresh=true 时触发异步爬取任务
    3. 前端通过 TanStack Query 自动轮询此接口（3分钟间隔）
    
    **新增功能**：
    - source参数可选，不传则返回所有来源的新闻
    - limit上限提升至200
    
    **优势**：
    - 无需手动输入页码，自动展示最新内容
    - 后台 Celery 定时爬取，前端只负责展示
    - 支持强制刷新（适用于需要即时数据的场景）
    """
    try:
        # 1. 如果强制刷新，触发 Celery 任务（异步）
        if force_refresh and source:
            logger.info(f"触发强制刷新: {source}")
            task = realtime_crawl_task.delay(source=source, force_refresh=True)
            logger.info(f"Celery Task ID: {task.id}")
            # 不等待任务完成，直接返回数据库中的数据
        
        # 2. 从数据库查询最新新闻
        cutoff_time = datetime.utcnow() - timedelta(hours=settings.NEWS_RETENTION_HOURS)
        
        # 构建查询条件
        conditions = [News.publish_time >= cutoff_time]
        if source:
            # 如果指定了来源，只查询该来源
            conditions.append(News.source == source)
        
        query = (
            select(News)
            .where(and_(*conditions))
            .order_by(desc(News.publish_time))
            .limit(limit)
        )
        
        result = await db.execute(query)
        news_list = result.scalars().all()
        
        # 3. 检查 Redis 缓存元数据（用于显示"最后更新时间"）
        cache_key = f"news:{source if source else 'all'}:latest"
        cache_metadata = redis_client.get_cache_metadata(cache_key) if source else None
        cache_age = cache_metadata['age_seconds'] if cache_metadata else None
        
        source_desc = f"来源 {source}" if source else "所有来源"
        
        return LatestNewsResponse(
            success=True,
            data=[NewsResponse.model_validate(news) for news in news_list],
            total=len(news_list),
            from_cache=False,  # 数据来自数据库，不是 Redis
            cache_age=cache_age,
            message=f"返回 {len(news_list)} 条最新新闻（{source_desc}，最近 {settings.NEWS_RETENTION_HOURS} 小时）"
        )
        
    except Exception as e:
        logger.error(f"获取最新新闻失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/refresh", response_model=ForceRefreshResponse, summary="强制刷新新闻")
async def force_refresh_news(
    source: str = Query("sina", description="新闻源")
):
    """
    强制刷新新闻（触发即时爬取）
    
    **使用场景**：
    - 用户点击"立即刷新"按钮
    - 需要最新数据时
    
    **注意**：
    - 异步执行，不会阻塞响应
    - 建议前端在3秒后自动刷新列表
    """
    try:
        # 触发 Celery 任务
        task = realtime_crawl_task.delay(source=source, force_refresh=True)
        
        logger.info(f"强制刷新任务已触发: {source}, Task ID: {task.id}")
        
        return ForceRefreshResponse(
            success=True,
            message=f"正在刷新 {source} 新闻，请稍后查看",
            task_id=str(task.id),
            new_count=0
        )
        
    except Exception as e:
        logger.error(f"触发刷新失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{news_id}/html", response_model=NewsHtmlResponse, summary="获取新闻原始HTML")
async def get_news_html(
    news_id: int,
    db: AsyncSession = Depends(get_db)
):
    """获取新闻的原始 HTML 内容（用于完整展示）"""
    try:
        query = select(News).where(News.id == news_id)
        result = await db.execute(query)
        news = result.scalar_one_or_none()
        
        if not news:
            raise HTTPException(status_code=404, detail="新闻不存在")
        
        return NewsHtmlResponse(
            id=news.id,
            title=news.title,
            url=news.url,
            raw_html=news.raw_html,
            has_raw_html=news.raw_html is not None and len(news.raw_html or '') > 0,
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取新闻HTML失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{news_id}", response_model=NewsResponse, summary="获取新闻详情")
async def get_news_detail(
    news_id: int,
    db: AsyncSession = Depends(get_db)
):
    """获取单条新闻详情"""
    try:
        query = select(News).where(News.id == news_id)
        result = await db.execute(query)
        news = result.scalar_one_or_none()
        
        if not news:
            raise HTTPException(status_code=404, detail="新闻不存在")
        
        # 添加 has_raw_html 字段
        response = NewsResponse.model_validate(news)
        response.has_raw_html = news.raw_html is not None and len(news.raw_html or '') > 0
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取新闻详情失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/", response_model=List[NewsResponse], summary="获取新闻列表（带筛选）")
async def get_news_list(
    source: Optional[str] = Query(None, description="新闻源筛选"),
    sentiment: Optional[str] = Query(None, description="情感筛选: positive/negative/neutral"),
    limit: int = Query(50, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db)
):
    """
    获取新闻列表（支持多种筛选）
    
    **筛选条件**：
    - source: 按新闻源筛选
    - sentiment: 按情感筛选
      - positive: 利好 (sentiment_score > 0.1)
      - negative: 利空 (sentiment_score < -0.1)
      - neutral: 中性 (其他)
    """
    try:
        query = select(News)
        
        # 时间过滤
        cutoff_time = datetime.utcnow() - timedelta(hours=settings.NEWS_RETENTION_HOURS)
        query = query.where(News.publish_time >= cutoff_time)
        
        # 新闻源筛选
        if source:
            query = query.where(News.source == source)
        
        # 情感筛选
        if sentiment:
            if sentiment == "positive":
                query = query.where(News.sentiment_score > 0.1)
            elif sentiment == "negative":
                query = query.where(News.sentiment_score < -0.1)
            elif sentiment == "neutral":
                query = query.where(
                    and_(
                        News.sentiment_score.isnot(None),
                        News.sentiment_score >= -0.1,
                        News.sentiment_score <= 0.1
                    )
                )
        
        # 排序和分页
        query = query.order_by(desc(News.publish_time)).offset(offset).limit(limit)
        
        result = await db.execute(query)
        news_list = result.scalars().all()
        
        return [NewsResponse.model_validate(news) for news in news_list]
        
    except Exception as e:
        logger.error(f"获取新闻列表失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ========== 兼容旧接口（标记为已废弃） ==========

@router.post("/crawl", deprecated=True, summary="【已废弃】手动触发爬取")
async def crawl_news_deprecated():
    """
    ⚠️ 此接口已废弃
    
    **原因**：
    - Phase 2 已改为 Celery 自动定时爬取
    - 无需手动输入页码
    
    **替代方案**：
    - 使用 `GET /api/v1/news/latest` 获取最新新闻
    - 使用 `POST /api/v1/news/refresh` 强制刷新
    """
    raise HTTPException(
        status_code=410,  # 410 Gone
        detail={
            "error": "接口已废弃",
            "message": "请使用 GET /api/v1/news/latest 获取最新新闻",
            "migration_guide": "Phase 2 已移除手动爬取，改为自动定时任务"
        }
    )

