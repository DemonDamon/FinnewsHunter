"""
分析任务 API 路由
"""
import logging
import asyncio
import json
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Body, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.database import get_db
from ...models.database import AsyncSessionLocal
from ...services.analysis_service import get_analysis_service

logger = logging.getLogger(__name__)

router = APIRouter()


# Pydantic 模型
class AnalysisRequest(BaseModel):
    """分析请求模型"""
    provider: Optional[str] = Field(default=None, description="LLM提供商 (bailian/openai/deepseek/kimi/zhipu)")
    model: Optional[str] = Field(default=None, description="模型名称")


class AnalysisResponse(BaseModel):
    """分析响应模型"""
    success: bool
    analysis_id: Optional[int] = None
    news_id: int
    sentiment: Optional[str] = None
    sentiment_score: Optional[float] = None
    confidence: Optional[float] = None
    summary: Optional[str] = None
    execution_time: Optional[float] = None
    error: Optional[str] = None


class AnalysisDetailResponse(BaseModel):
    """分析详情响应模型"""
    model_config = {"from_attributes": True}
    
    id: int
    news_id: int
    agent_name: str
    agent_role: Optional[str] = None
    analysis_result: str
    summary: Optional[str] = None
    sentiment: Optional[str] = None
    sentiment_score: Optional[float] = None
    confidence: Optional[float] = None
    execution_time: Optional[float] = None
    created_at: str


class BatchAnalyzeRequest(BaseModel):
    """批量分析请求模型"""
    news_ids: List[int] = Field(..., description="要分析的新闻ID列表")
    provider: Optional[str] = Field(default=None, description="LLM提供商")
    model: Optional[str] = Field(default=None, description="模型名称")


class BatchAnalyzeResponse(BaseModel):
    """批量分析响应模型"""
    success: bool
    message: str
    total_count: int
    success_count: int
    failed_count: int
    results: List[AnalysisResponse]


# 后台任务：执行分析
async def run_analysis_task(news_id: int, db: AsyncSession):
    """
    后台任务：执行新闻分析
    """
    try:
        analysis_service = get_analysis_service()
        result = await analysis_service.analyze_news(news_id, db)
        logger.info(f"Analysis task completed for news {news_id}: {result}")
    except Exception as e:
        logger.error(f"Analysis task failed for news {news_id}: {e}")


# API 端点
# 注意：具体路径（如 /news/batch）必须在参数路径（如 /news/{news_id}）之前定义
# 否则 FastAPI 会把 "batch" 当作 news_id 参数

@router.post("/news/batch", response_model=BatchAnalyzeResponse)
async def batch_analyze_news(
    request_body: BatchAnalyzeRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    批量分析新闻（并发）
    
    - **news_ids**: 要分析的新闻ID列表
    - **provider**: LLM提供商（可选）
    - **model**: 模型名称（可选）
    """
    try:
        logger.info(f"Received batch analyze request: news_ids={request_body.news_ids}, provider={request_body.provider}, model={request_body.model}")
        
        if not request_body.news_ids:
            raise HTTPException(status_code=400, detail="news_ids cannot be empty")
        
        analysis_service = get_analysis_service()
        
        # 准备LLM provider参数
        llm_provider = request_body.provider
        llm_model = request_body.model
        
        # 定义单个新闻的分析任务
        # 注意：每个任务需要独立的数据库会话，因为SQLAlchemy异步会话不支持并发操作
        async def analyze_single_news(news_id: int) -> AnalysisResponse:
            # 为每个任务创建独立的数据库会话
            async with AsyncSessionLocal() as task_db:
                try:
                    result = await analysis_service.analyze_news(
                        news_id,
                        task_db,
                        llm_provider=llm_provider,
                        llm_model=llm_model
                    )
                    
                    # 提交事务
                    await task_db.commit()
                    
                    if result.get("success"):
                        return AnalysisResponse(
                            success=True,
                            analysis_id=result.get("analysis_id"),
                            news_id=news_id,
                            sentiment=result.get("sentiment"),
                            sentiment_score=result.get("sentiment_score"),
                            confidence=result.get("confidence"),
                            summary=result.get("summary"),
                            execution_time=result.get("execution_time"),
                        )
                    else:
                        return AnalysisResponse(
                            success=False,
                            news_id=news_id,
                            error=result.get("error")
                        )
                except Exception as e:
                    # 发生错误时回滚事务
                    await task_db.rollback()
                    logger.error(f"Failed to analyze news {news_id}: {e}", exc_info=True)
                    return AnalysisResponse(
                        success=False,
                        news_id=news_id,
                        error=str(e)
                    )
        
        # 并发执行所有分析任务
        logger.info(f"Starting batch analysis for {len(request_body.news_ids)} news items")
        results = await asyncio.gather(*[analyze_single_news(news_id) for news_id in request_body.news_ids])
        
        # 统计结果
        success_count = sum(1 for r in results if r.success)
        failed_count = len(results) - success_count
        
        logger.info(f"Batch analysis completed: {success_count} succeeded, {failed_count} failed")
        
        return BatchAnalyzeResponse(
            success=True,
            message=f"批量分析完成：成功 {success_count} 条，失败 {failed_count} 条",
            total_count=len(request_body.news_ids),
            success_count=success_count,
            failed_count=failed_count,
            results=results
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to batch analyze news: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/news/{news_id}", response_model=AnalysisResponse)
async def analyze_news(
    news_id: int,
    request: Optional[AnalysisRequest] = Body(None),
    background_tasks: BackgroundTasks = None,
    db: AsyncSession = Depends(get_db)
):
    """
    触发新闻分析任务
    
    - **news_id**: 新闻ID
    - **provider**: LLM提供商（可选）
    - **model**: 模型名称（可选）
    
    Returns:
        分析任务状态
    """
    try:
        analysis_service = get_analysis_service()
        
        # 准备LLM provider参数
        llm_provider = None
        llm_model = None
        if request:
            llm_provider = request.provider
            llm_model = request.model
            if llm_provider or llm_model:
                logger.info(f"Using custom LLM config: provider={llm_provider}, model={llm_model}")
        
        # 执行分析（同步，便于快速验证MVP）
        # 在生产环境中，应该使用后台任务
        result = await analysis_service.analyze_news(
            news_id, 
            db, 
            llm_provider=llm_provider,
            llm_model=llm_model
        )
        
        if result.get("success"):
            return AnalysisResponse(
                success=True,
                analysis_id=result.get("analysis_id"),
                news_id=news_id,
                sentiment=result.get("sentiment"),
                sentiment_score=result.get("sentiment_score"),
                confidence=result.get("confidence"),
                summary=result.get("summary"),
                execution_time=result.get("execution_time"),
            )
        else:
            return AnalysisResponse(
                success=False,
                news_id=news_id,
                error=result.get("error")
            )
    
    except Exception as e:
        logger.error(f"Failed to analyze news {news_id}: {e}", exc_info=True)
        return AnalysisResponse(
            success=False,
            news_id=news_id,
            error=str(e)
        )


@router.get("/news/{news_id}/all", response_model=List[AnalysisDetailResponse])
async def get_news_analyses(
    news_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    获取指定新闻的所有分析结果
    
    - **news_id**: 新闻ID
    """
    try:
        analysis_service = get_analysis_service()
        results = await analysis_service.get_analyses_by_news_id(news_id, db)
        
        return [AnalysisDetailResponse(**result) for result in results]
    
    except Exception as e:
        logger.error(f"Failed to get analyses for news {news_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{analysis_id}", response_model=AnalysisDetailResponse)
async def get_analysis_detail(
    analysis_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    获取分析结果详情
    
    - **analysis_id**: 分析ID
    """
    try:
        analysis_service = get_analysis_service()
        result = await analysis_service.get_analysis_by_id(analysis_id, db)
        
        if not result:
            raise HTTPException(status_code=404, detail="Analysis not found")
        
        return AnalysisDetailResponse(**result)
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get analysis {analysis_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

