"""
任务管理 API 路由
"""
import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from datetime import datetime

from ...core.database import get_db
from ...models.crawl_task import CrawlTask, CrawlMode, TaskStatus
from ...tasks.crawl_tasks import cold_start_crawl_task

logger = logging.getLogger(__name__)

router = APIRouter()


# Pydantic 模型
class TaskResponse(BaseModel):
    """任务响应模型"""
    model_config = {"from_attributes": True}
    
    id: int
    celery_task_id: Optional[str] = None
    mode: str
    status: str
    source: str
    config: Optional[dict] = None
    progress: Optional[dict] = None
    current_page: Optional[int] = None
    total_pages: Optional[int] = None
    result: Optional[dict] = None
    crawled_count: int
    saved_count: int
    error_message: Optional[str] = None
    execution_time: Optional[float] = None
    created_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None


class ColdStartRequest(BaseModel):
    """冷启动请求模型"""
    source: str = Field(default="sina", description="新闻源")
    start_page: int = Field(default=1, ge=1, description="起始页码")
    end_page: int = Field(default=50, ge=1, le=100, description="结束页码")


class ColdStartResponse(BaseModel):
    """冷启动响应模型"""
    success: bool
    message: str
    task_id: Optional[int] = None
    celery_task_id: Optional[str] = None


# API 端点
@router.get("/", response_model=List[TaskResponse])
async def get_tasks_list(
    skip: int = Query(0, ge=0, description="跳过的记录数"),
    limit: int = Query(20, ge=1, le=100, description="返回的记录数"),
    mode: Optional[str] = Query(None, description="按模式筛选"),
    status: Optional[str] = Query(None, description="按状态筛选"),
    db: AsyncSession = Depends(get_db)
):
    """
    获取任务列表
    
    - **skip**: 跳过的记录数（分页）
    - **limit**: 返回的记录数
    - **mode**: 按模式筛选（cold_start, realtime, targeted）
    - **status**: 按状态筛选（pending, running, completed, failed）
    """
    try:
        query = select(CrawlTask).order_by(desc(CrawlTask.created_at))
        
        if mode:
            query = query.where(CrawlTask.mode == mode)
        if status:
            query = query.where(CrawlTask.status == status)
        
        query = query.offset(skip).limit(limit)
        
        result = await db.execute(query)
        tasks = result.scalars().all()
        
        return [TaskResponse(**task.to_dict()) for task in tasks]
    
    except Exception as e:
        logger.error(f"Failed to get tasks list: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task_detail(
    task_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    获取任务详情
    
    - **task_id**: 任务ID
    """
    try:
        result = await db.execute(
            select(CrawlTask).where(CrawlTask.id == task_id)
        )
        task = result.scalar_one_or_none()
        
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        
        return TaskResponse(**task.to_dict())
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get task {task_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/cold-start", response_model=ColdStartResponse)
async def trigger_cold_start(
    request: ColdStartRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    触发冷启动批量爬取任务
    
    - **source**: 新闻源（sina, jrj等）
    - **start_page**: 起始页码
    - **end_page**: 结束页码
    """
    try:
        logger.info(
            f"触发冷启动任务: {request.source}, "
            f"页码 {request.start_page}-{request.end_page}"
        )
        
        # 触发 Celery 任务
        celery_task = cold_start_crawl_task.apply_async(
            args=(request.source, request.start_page, request.end_page)
        )
        
        # 等待任务记录创建（最多等待2秒）
        await db.commit()  # 确保之前的事务已提交
        
        return ColdStartResponse(
            success=True,
            message=f"冷启动任务已启动: {request.source}, 页码 {request.start_page}-{request.end_page}",
            celery_task_id=celery_task.id
        )
    
    except Exception as e:
        logger.error(f"Failed to trigger cold start: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats/summary")
async def get_task_stats(
    db: AsyncSession = Depends(get_db)
):
    """
    获取任务统计信息
    """
    try:
        # 统计各状态的任务数
        result = await db.execute(select(CrawlTask))
        all_tasks = result.scalars().all()
        
        stats = {
            "total": len(all_tasks),
            "by_status": {},
            "by_mode": {},
            "recent_completed": 0,
            "total_news_crawled": 0,
            "total_news_saved": 0,
        }
        
        for task in all_tasks:
            # 按状态统计
            stats["by_status"][task.status] = stats["by_status"].get(task.status, 0) + 1
            
            # 按模式统计
            stats["by_mode"][task.mode] = stats["by_mode"].get(task.mode, 0) + 1
            
            # 统计新闻数
            stats["total_news_crawled"] += task.crawled_count or 0
            stats["total_news_saved"] += task.saved_count or 0
            
            # 最近24小时完成的任务
            if task.status == TaskStatus.COMPLETED and task.completed_at:
                from datetime import timedelta
                if datetime.utcnow() - task.completed_at < timedelta(days=1):
                    stats["recent_completed"] += 1
        
        return stats
    
    except Exception as e:
        logger.error(f"Failed to get task stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{task_id}")
async def delete_task(
    task_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    删除任务记录
    
    - **task_id**: 任务ID
    """
    try:
        result = await db.execute(
            select(CrawlTask).where(CrawlTask.id == task_id)
        )
        task = result.scalar_one_or_none()
        
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        
        await db.delete(task)
        await db.commit()
        
        return {"success": True, "message": f"Task {task_id} deleted"}
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete task {task_id}: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

