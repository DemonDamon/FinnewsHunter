"""
新闻管理 API 路由
"""
import logging
from typing import List, Optional
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from ...core.database import get_db
from ...models.news import News
from ...tools import SinaCrawlerTool

logger = logging.getLogger(__name__)

router = APIRouter()


# Pydantic 模型
class NewsResponse(BaseModel):
    """新闻响应模型"""
    model_config = {"from_attributes": True}
    
    id: int
    title: str
    content: str
    url: str
    source: str
    publish_time: Optional[str] = None
    stock_codes: Optional[List[str]] = None
    sentiment_score: Optional[float] = None
    created_at: str


class CrawlRequest(BaseModel):
    """爬取请求模型"""
    source: str = Field(default="sina", description="新闻源（sina, jrj, cnstock）")
    start_page: int = Field(default=1, ge=1, description="起始页码")
    end_page: int = Field(default=1, ge=1, le=10, description="结束页码")


class CrawlResponse(BaseModel):
    """爬取响应模型"""
    success: bool
    message: str
    crawled_count: int
    saved_count: int
    source: str


class BatchDeleteRequest(BaseModel):
    """批量删除请求模型"""
    news_ids: List[int] = Field(..., description="要删除的新闻ID列表")


class BatchDeleteResponse(BaseModel):
    """批量删除响应模型"""
    success: bool
    message: str
    deleted_count: int


# 后台任务：爬取并保存新闻（使用同步方式）
def crawl_and_save_news_sync(
    source: str,
    start_page: int,
    end_page: int
):
    """
    后台任务：爬取新闻并保存到数据库（同步版本）
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from ...core.config import settings
    
    try:
        logger.info(f"Starting crawl task: {source}, pages {start_page}-{end_page}")
        
        # 创建爬虫
        if source == "sina":
            crawler = SinaCrawlerTool()
        else:
            logger.error(f"Unsupported source: {source}")
            return
        
        # 执行爬取
        news_list = crawler.crawl(start_page, end_page)
        logger.info(f"Crawled {len(news_list)} news items")
        
        # 创建新的数据库连接（同步）
        engine = create_engine(settings.SYNC_DATABASE_URL)
        db = Session(engine)
        
        try:
            # 时间过滤：只保存最近7天内的新闻（避免保存太旧的新闻）
            cutoff_time = datetime.utcnow() - timedelta(days=7)
            
            # 保存到数据库
            saved_count = 0
            skipped_old_count = 0
            skipped_existing_count = 0
            
            for news_item in news_list:
                # 时间过滤：跳过太旧的新闻
                if news_item.publish_time and news_item.publish_time < cutoff_time:
                    skipped_old_count += 1
                    logger.debug(f"Skipping old news: {news_item.title[:50]} (published: {news_item.publish_time})")
                    continue
                
                # 检查URL是否已存在
                existing = db.execute(
                    select(News).where(News.url == news_item.url)
                ).scalar_one_or_none()
                
                if existing:
                    skipped_existing_count += 1
                    logger.debug(f"News already exists: {news_item.url}")
                    continue
                
                # 创建新记录
                news = News(
                    title=news_item.title,
                    content=news_item.content,
                    url=news_item.url,
                    source=news_item.source,
                    publish_time=news_item.publish_time,
                    author=news_item.author,
                    keywords=news_item.keywords,
                    stock_codes=news_item.stock_codes,
                    # summary 字段已移除，content 包含完整内容
                )
                
                db.add(news)
                saved_count += 1
                logger.info(f"Saved new news: {news_item.title[:50]} (published: {news_item.publish_time})")
            
            db.commit()
            logger.info(
                f"Crawl summary: crawled={len(news_list)}, "
                f"saved={saved_count}, "
                f"skipped_old={skipped_old_count}, "
                f"skipped_existing={skipped_existing_count}"
            )
        
        finally:
            db.close()
    
    except Exception as e:
        logger.error(f"Crawl task failed: {e}", exc_info=True)


# API 端点
@router.post("/crawl", response_model=CrawlResponse)
async def crawl_news(
    request: CrawlRequest,
    background_tasks: BackgroundTasks
):
    """
    触发新闻爬取任务（异步后台任务）
    
    - **source**: 新闻源（sina, jrj, cnstock）
    - **start_page**: 起始页码
    - **end_page**: 结束页码
    
    注意：这是简单的后台任务版本。如需更强大的任务管理，
    请使用 POST /api/v1/tasks/cold-start 触发 Celery 任务。
    """
    # 添加到后台任务（同步版本）
    background_tasks.add_task(
        crawl_and_save_news_sync,
        request.source,
        request.start_page,
        request.end_page
    )
    
    logger.info(f"Background crawl task added: {request.source}, pages {request.start_page}-{request.end_page}")
    
    return CrawlResponse(
        success=True,
        message=f"Crawl task started for {request.source}, pages {request.start_page}-{request.end_page}",
        crawled_count=0,  # 后台任务还未完成
        saved_count=0,
        source=request.source
    )


@router.post("/refresh", response_model=CrawlResponse)
async def refresh_news(
    source: str = Query("sina", description="新闻源"),
    pages: int = Query(1, ge=1, le=5, description="爬取页数"),
    background_tasks: BackgroundTasks = None
):
    """
    刷新新闻（前端刷新按钮调用）
    
    - **source**: 新闻源（sina, tencent, nbd, eastmoney, yicai, 163）
    - **pages**: 爬取页数（1-5）
    """
    background_tasks.add_task(
        crawl_and_save_news_sync,
        source,
        1,  # start_page
        pages  # end_page
    )
    
    logger.info(f"Refresh task started: {source}, {pages} pages")
    
    return CrawlResponse(
        success=True,
        message=f"刷新任务已启动：{source}，{pages} 页",
        crawled_count=0,
        saved_count=0,
        source=source
    )


@router.get("/", response_model=List[NewsResponse])
async def get_news_list(
    skip: int = Query(0, ge=0, description="跳过的记录数"),
    limit: int = Query(20, ge=1, le=100, description="返回的记录数"),
    source: Optional[str] = Query(None, description="按来源筛选"),
    db: AsyncSession = Depends(get_db)
):
    """
    获取新闻列表
    
    - **skip**: 跳过的记录数（分页）
    - **limit**: 返回的记录数
    - **source**: 按来源筛选（可选）
    """
    try:
        query = select(News).order_by(desc(News.created_at))
        
        if source:
            query = query.where(News.source == source)
        
        query = query.offset(skip).limit(limit)
        
        result = await db.execute(query)
        news_list = result.scalars().all()
        
        return [NewsResponse(**news.to_dict()) for news in news_list]
    
    except Exception as e:
        logger.error(f"Failed to get news list: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/latest", response_model=List[NewsResponse])
async def get_latest_news(
    limit: int = Query(20, ge=1, le=500, description="返回的记录数"),
    source: Optional[str] = Query(None, description="按来源筛选"),
    db: AsyncSession = Depends(get_db)
):
    """
    获取最新新闻（按发布时间排序）
    
    - **limit**: 返回的记录数（最多500条）
    - **source**: 按来源筛选（可选）
    """
    try:
        query = select(News).order_by(desc(News.publish_time))
        
        if source:
            query = query.where(News.source == source)
        
        query = query.limit(limit)
        
        result = await db.execute(query)
        news_list = result.scalars().all()
        
        return [NewsResponse(**news.to_dict()) for news in news_list]
    
    except Exception as e:
        logger.error(f"Failed to get latest news: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{news_id}", response_model=NewsResponse)
async def get_news_detail(
    news_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    获取新闻详情
    
    - **news_id**: 新闻ID
    """
    try:
        result = await db.execute(
            select(News).where(News.id == news_id)
        )
        news = result.scalar_one_or_none()
        
        if not news:
            raise HTTPException(status_code=404, detail="News not found")
        
        return NewsResponse(**news.to_dict())
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get news {news_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/batch/delete", response_model=BatchDeleteResponse)
async def batch_delete_news(
    request: BatchDeleteRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    批量删除新闻
    
    - **news_ids**: 要删除的新闻ID列表
    """
    try:
        if not request.news_ids:
            raise HTTPException(status_code=400, detail="news_ids cannot be empty")
        
        # 查询要删除的新闻
        result = await db.execute(
            select(News).where(News.id.in_(request.news_ids))
        )
        news_list = result.scalars().all()
        
        deleted_count = len(news_list)
        
        if deleted_count == 0:
            return BatchDeleteResponse(
                success=True,
                message="No news found to delete",
                deleted_count=0
            )
        
        # 批量删除
        for news in news_list:
            await db.delete(news)
        
        await db.commit()
        
        logger.info(f"Batch deleted {deleted_count} news items: {request.news_ids}")
        
        return BatchDeleteResponse(
            success=True,
            message=f"Successfully deleted {deleted_count} news items",
            deleted_count=deleted_count
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to batch delete news: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{news_id}")
async def delete_news(
    news_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    删除新闻
    
    - **news_id**: 新闻ID
    """
    try:
        result = await db.execute(
            select(News).where(News.id == news_id)
        )
        news = result.scalar_one_or_none()
        
        if not news:
            raise HTTPException(status_code=404, detail="News not found")
        
        await db.delete(news)
        await db.commit()
        
        return {"success": True, "message": f"News {news_id} deleted"}
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete news {news_id}: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

