"""
新闻 API v2 - 使用新的 Financial Data Layer

新功能:
1. 多数据源支持：可指定 provider (sina, tencent, nbd...)
2. 自动降级：一个源失败自动切换另一个
3. 标准化数据：统一的 NewsData 格式
4. 实时获取：直接从数据源获取，不经过数据库

前端可通过对比 /api/v1/news (旧) vs /api/v1/news/v2 (新) 看到差异
"""
import logging
from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ...financial import get_registry, NewsQueryParams
from ...financial.tools import FinancialNewsTool, setup_default_providers

logger = logging.getLogger(__name__)

router = APIRouter()

# 确保 Provider 已注册
setup_default_providers()


class NewsDataResponse(BaseModel):
    """标准化新闻响应（使用 NewsData 模型）"""
    id: str
    title: str
    content: str
    summary: Optional[str] = None
    source: str
    source_url: str
    publish_time: datetime
    stock_codes: List[str] = []
    sentiment: Optional[str] = None
    sentiment_score: Optional[float] = None


class FetchNewsResponse(BaseModel):
    """获取新闻响应"""
    success: bool
    count: int
    provider: Optional[str] = None
    available_providers: Optional[List[str]] = None
    data: List[NewsDataResponse] = []
    error: Optional[str] = None


class ProviderInfoResponse(BaseModel):
    """Provider 信息响应"""
    name: str
    display_name: str
    description: str
    supported_types: List[str]
    priority: int


@router.get("/fetch", response_model=FetchNewsResponse)
async def fetch_news_realtime(
    stock_codes: Optional[str] = Query(
        None, 
        description="股票代码，多个用逗号分隔，如 '600519,000001'"
    ),
    keywords: Optional[str] = Query(
        None, 
        description="关键词，多个用逗号分隔"
    ),
    limit: int = Query(
        20, 
        ge=1, 
        le=100, 
        description="返回条数"
    ),
    provider: Optional[str] = Query(
        None, 
        description="指定数据源（sina, tencent, nbd），不指定则自动选择"
    )
):
    """
    实时获取新闻（使用新的 Provider-Fetcher 架构）
    
    特点:
    - 直接从数据源获取，不经过数据库
    - 支持指定数据源或自动选择
    - 返回标准化的 NewsData 格式
    
    示例:
    - GET /api/v1/news/v2/fetch?stock_codes=600519&limit=10
    - GET /api/v1/news/v2/fetch?keywords=茅台,白酒&provider=sina
    """
    tool = FinancialNewsTool()
    
    # 解析参数
    stock_code_list = stock_codes.split(",") if stock_codes else None
    keyword_list = keywords.split(",") if keywords else None
    
    try:
        result = await tool.aexecute(
            stock_codes=stock_code_list,
            keywords=keyword_list,
            limit=limit,
            provider=provider
        )
        
        if result["success"]:
            # 转换为响应格式
            news_list = [
                NewsDataResponse(
                    id=item["id"],
                    title=item["title"],
                    content=item["content"],
                    summary=item.get("summary"),
                    source=item["source"],
                    source_url=item["source_url"],
                    publish_time=item["publish_time"],
                    stock_codes=item.get("stock_codes", []),
                    sentiment=item.get("sentiment"),
                    sentiment_score=item.get("sentiment_score")
                )
                for item in result["data"]
            ]
            
            return FetchNewsResponse(
                success=True,
                count=result["count"],
                provider=result.get("provider"),
                data=news_list
            )
        else:
            return FetchNewsResponse(
                success=False,
                count=0,
                error=result.get("error"),
                available_providers=result.get("available_providers", [])
            )
            
    except Exception as e:
        logger.exception(f"Failed to fetch news: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/providers", response_model=List[ProviderInfoResponse])
async def list_providers():
    """
    列出所有可用的数据源 Provider
    
    返回:
    - 每个 Provider 的名称、描述、支持的数据类型、优先级
    """
    registry = get_registry()
    providers = []
    
    for name in registry.list_providers():
        provider = registry.get_provider(name)
        if provider:
            providers.append(ProviderInfoResponse(
                name=provider.info.name,
                display_name=provider.info.display_name,
                description=provider.info.description,
                supported_types=list(provider.fetchers.keys()),
                priority=provider.info.priority
            ))
    
    return providers


@router.get("/providers/{provider_name}/test")
async def test_provider(
    provider_name: str,
    limit: int = Query(5, ge=1, le=20)
):
    """
    测试指定的 Provider 是否工作正常
    
    返回:
    - 测试结果和获取到的样本数据
    """
    tool = FinancialNewsTool()
    
    try:
        result = await tool.aexecute(
            limit=limit,
            provider=provider_name
        )
        
        return {
            "provider": provider_name,
            "success": result["success"],
            "count": result.get("count", 0),
            "error": result.get("error"),
            "sample_titles": [
                item["title"][:50] for item in result.get("data", [])[:3]
            ]
        }
        
    except Exception as e:
        return {
            "provider": provider_name,
            "success": False,
            "error": str(e)
        }
