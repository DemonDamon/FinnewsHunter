"""
知识图谱管理 API
提供图谱的查询、构建、更新、删除接口
"""
import logging
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter()


# ============ Pydantic 模型 ============

class CompanyGraphResponse(BaseModel):
    """公司图谱响应"""
    stock_code: str
    stock_name: str
    graph_exists: bool
    stats: Optional[Dict[str, int]] = None
    name_variants: List[str] = Field(default_factory=list)
    businesses: List[Dict[str, Any]] = Field(default_factory=list)
    industries: List[str] = Field(default_factory=list)
    products: List[str] = Field(default_factory=list)
    concepts: List[str] = Field(default_factory=list)
    search_queries: List[str] = Field(default_factory=list, description="生成的检索查询")


class BuildGraphRequest(BaseModel):
    """构建图谱请求"""
    force_rebuild: bool = Field(default=False, description="是否强制重建")


class BuildGraphResponse(BaseModel):
    """构建图谱响应"""
    success: bool
    message: str
    graph_stats: Optional[Dict[str, int]] = None


class UpdateGraphRequest(BaseModel):
    """更新图谱请求"""
    update_from_news: bool = Field(default=True, description="是否从新闻更新")
    news_limit: int = Field(default=20, description="分析的新闻数量")


class GraphStatsResponse(BaseModel):
    """图谱统计响应"""
    total_companies: int
    total_nodes: int
    total_relationships: int
    companies: List[Dict[str, str]] = Field(default_factory=list)


# ============ API 路由 ============

@router.get("/{stock_code}", response_model=CompanyGraphResponse)
async def get_company_graph(stock_code: str):
    """
    获取公司知识图谱
    
    - **stock_code**: 股票代码
    """
    try:
        from ...knowledge.graph_service import get_graph_service
        
        # 标准化股票代码
        code = stock_code.upper()
        if not (code.startswith("SH") or code.startswith("SZ")):
            code = f"SH{code}" if code.startswith("6") else f"SZ{code}"
        
        graph_service = get_graph_service()
        
        # 获取图谱
        graph = graph_service.get_company_graph(code)
        
        if not graph:
            return CompanyGraphResponse(
                stock_code=code,
                stock_name=stock_code,
                graph_exists=False
            )
        
        # 获取统计信息
        stats = graph_service.get_graph_stats(code)
        
        # 获取检索关键词
        keyword_set = graph_service.get_search_keywords(code)
        search_queries = keyword_set.combined_queries if keyword_set else []
        
        return CompanyGraphResponse(
            stock_code=code,
            stock_name=graph.company.stock_name,
            graph_exists=True,
            stats=stats,
            name_variants=[v.variant for v in graph.name_variants],
            businesses=[
                {
                    "name": b.business_name,
                    "type": b.business_type,
                    "status": b.status,
                    "description": b.description
                }
                for b in graph.businesses
            ],
            industries=[i.industry_name for i in graph.industries],
            products=[p.product_name for p in graph.products],
            concepts=[c.concept_name for c in graph.concepts],
            search_queries=search_queries
        )
    
    except Exception as e:
        logger.error(f"Failed to get company graph for {stock_code}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{stock_code}/build", response_model=BuildGraphResponse)
async def build_company_graph(
    stock_code: str,
    request: BuildGraphRequest,
    background_tasks: BackgroundTasks
):
    """
    构建或重建公司知识图谱
    
    - **stock_code**: 股票代码
    - **force_rebuild**: 是否强制重建（删除现有图谱）
    """
    try:
        from ...knowledge.graph_service import get_graph_service
        from ...knowledge.knowledge_extractor import (
            create_knowledge_extractor,
            AkshareKnowledgeExtractor
        )
        
        # 标准化股票代码
        code = stock_code.upper()
        if not (code.startswith("SH") or code.startswith("SZ")):
            code = f"SH{code}" if code.startswith("6") else f"SZ{code}"
        
        graph_service = get_graph_service()
        
        # 检查是否已存在
        existing = graph_service.get_company_graph(code)
        
        if existing and not request.force_rebuild:
            return BuildGraphResponse(
                success=False,
                message=f"图谱已存在，如需重建请设置 force_rebuild=true",
                graph_stats=graph_service.get_graph_stats(code)
            )
        
        # 强制重建：先删除
        if existing and request.force_rebuild:
            graph_service.delete_company_graph(code)
            logger.info(f"已删除现有图谱: {code}")
        
        # 从 akshare 获取信息
        akshare_info = AkshareKnowledgeExtractor.extract_company_info(code)
        
        if not akshare_info:
            return BuildGraphResponse(
                success=False,
                message=f"无法从 akshare 获取公司信息: {code}"
            )
        
        # 获取股票名称
        stock_name = akshare_info.get('raw_data', {}).get('股票简称', code)
        
        # 使用 LLM 提取详细信息
        extractor = create_knowledge_extractor()
        
        # 在后台任务中执行（避免阻塞）
        import asyncio
        graph = await extractor.extract_from_akshare(code, stock_name, akshare_info)
        
        # 构建图谱
        success = graph_service.build_company_graph(graph)
        
        if success:
            stats = graph_service.get_graph_stats(code)
            return BuildGraphResponse(
                success=True,
                message=f"图谱构建成功: {stock_name}",
                graph_stats=stats
            )
        else:
            return BuildGraphResponse(
                success=False,
                message="图谱构建失败"
            )
    
    except Exception as e:
        logger.error(f"Failed to build graph for {stock_code}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{stock_code}/update", response_model=BuildGraphResponse)
async def update_company_graph(
    stock_code: str,
    request: UpdateGraphRequest
):
    """
    更新公司知识图谱
    
    - **stock_code**: 股票代码
    - **update_from_news**: 是否从新闻更新
    - **news_limit**: 分析的新闻数量
    """
    try:
        from ...knowledge.graph_service import get_graph_service
        from ...knowledge.knowledge_extractor import create_knowledge_extractor
        from ...core.database import get_db
        from sqlalchemy.ext.asyncio import AsyncSession
        from ...models.news import News
        from sqlalchemy import select, text
        
        # 标准化股票代码
        code = stock_code.upper()
        if not (code.startswith("SH") or code.startswith("SZ")):
            code = f"SH{code}" if code.startswith("6") else f"SZ{code}"
        
        pure_code = code[2:] if code.startswith(("SH", "SZ")) else code
        
        graph_service = get_graph_service()
        
        # 检查图谱是否存在
        if not graph_service.get_company_graph(code):
            return BuildGraphResponse(
                success=False,
                message="图谱不存在，请先构建图谱"
            )
        
        if request.update_from_news:
            # 从数据库获取最新新闻
            from ...core.database import get_sync_db_session
            db = get_sync_db_session()
            
            recent_news = db.execute(
                text("""
                    SELECT title, content FROM news 
                    WHERE stock_codes @> ARRAY[:code]::varchar[] 
                    ORDER BY publish_time DESC LIMIT :limit
                """).bindparams(code=pure_code, limit=request.news_limit)
            ).fetchall()
            
            if not recent_news:
                return BuildGraphResponse(
                    success=False,
                    message="没有可用的新闻数据"
                )
            
            news_data = [
                {"title": n[0], "content": n[1]}
                for n in recent_news
            ]
            
            # 提取信息
            extractor = create_knowledge_extractor()
            extracted_info = await extractor.extract_from_news(code, "", news_data)
            
            # 更新图谱
            if any(extracted_info.values()):
                success = graph_service.update_from_news(code, "", extracted_info)
                
                if success:
                    stats = graph_service.get_graph_stats(code)
                    return BuildGraphResponse(
                        success=True,
                        message=f"图谱已更新: 新增业务{len(extracted_info.get('new_businesses', []))}个, 概念{len(extracted_info.get('new_concepts', []))}个",
                        graph_stats=stats
                    )
                else:
                    return BuildGraphResponse(
                        success=False,
                        message="图谱更新失败"
                    )
            else:
                return BuildGraphResponse(
                    success=True,
                    message="未提取到新信息",
                    graph_stats=graph_service.get_graph_stats(code)
                )
        
        return BuildGraphResponse(
            success=False,
            message="未指定更新方式"
        )
    
    except Exception as e:
        logger.error(f"Failed to update graph for {stock_code}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{stock_code}")
async def delete_company_graph(stock_code: str):
    """
    删除公司知识图谱
    
    - **stock_code**: 股票代码
    """
    try:
        from ...knowledge.graph_service import get_graph_service
        
        # 标准化股票代码
        code = stock_code.upper()
        if not (code.startswith("SH") or code.startswith("SZ")):
            code = f"SH{code}" if code.startswith("6") else f"SZ{code}"
        
        graph_service = get_graph_service()
        success = graph_service.delete_company_graph(code)
        
        if success:
            return {"success": True, "message": f"图谱已删除: {code}"}
        else:
            return {"success": False, "message": "删除失败"}
    
    except Exception as e:
        logger.error(f"Failed to delete graph for {stock_code}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/", response_model=GraphStatsResponse)
async def get_graph_stats():
    """
    获取所有图谱统计信息
    """
    try:
        from ...knowledge.graph_service import get_graph_service
        
        graph_service = get_graph_service()
        companies = graph_service.list_all_companies()
        
        # 获取总体统计
        total_companies = len(companies)
        
        # 查询总节点数和关系数（简化版）
        return GraphStatsResponse(
            total_companies=total_companies,
            total_nodes=total_companies * 10,  # 估算
            total_relationships=total_companies * 15,  # 估算
            companies=companies
        )
    
    except Exception as e:
        logger.error(f"Failed to get graph stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))

