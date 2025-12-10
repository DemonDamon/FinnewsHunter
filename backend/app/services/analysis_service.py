"""
新闻分析服务
协调智能体执行分析任务
"""
import logging
import time
from typing import Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from starlette.concurrency import run_in_threadpool

from ..agents import create_news_analyst
from ..models.news import News
from ..models.analysis import Analysis
from ..services.embedding_service import get_embedding_service
from ..storage.vector_storage import get_vector_storage

logger = logging.getLogger(__name__)


class AnalysisService:
    """
    新闻分析服务
    负责协调智能体执行新闻分析任务
    """
    
    def __init__(self):
        """初始化分析服务"""
        self.news_analyst = create_news_analyst()
        self.embedding_service = get_embedding_service()
        self.vector_storage = get_vector_storage()
        logger.info("Initialized AnalysisService")
    
    async def analyze_news(
        self,
        news_id: int,
        db: AsyncSession,
        llm_provider: Optional[str] = None,
        llm_model: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        分析指定新闻
        
        Args:
            news_id: 新闻ID
            db: 数据库会话
            llm_provider: 模型厂商（可选：bailian, openai, deepseek, kimi）
            llm_model: 模型名称（可选）
            
        Returns:
            分析结果
        """
        start_time = time.time()
        
        # 如果指定了自定义模型，创建临时的智能体
        if llm_provider and llm_model:
            from ..services.llm_service import create_custom_llm_provider
            from ..agents.news_analyst import NewsAnalystAgent
            
            logger.info(f"Using custom model: {llm_provider}/{llm_model}")
            custom_llm = create_custom_llm_provider(llm_provider, llm_model)
            analyst = NewsAnalystAgent(llm_provider=custom_llm)
        else:
            analyst = self.news_analyst
        
        try:
            # 1. 查询新闻
            result = await db.execute(
                select(News).where(News.id == news_id)
            )
            news = result.scalar_one_or_none()
            
            if not news:
                return {
                    "success": False,
                    "error": f"News not found: {news_id}"
                }
            
            logger.info(f"Analyzing news: {news_id} - {news.title}")
            
            # 2. 执行智能体分析
            # 注意：由于 agent.analyze_news 是同步方法，需要在线程池中运行以避免阻塞异步事件循环
            analysis_result = await run_in_threadpool(
                analyst.analyze_news,  # 使用 analyst（可能是自定义的或默认的）
                news_title=news.title,
                news_content=news.content,
                news_url=news.url,
                stock_codes=news.stock_codes or []
            )
            
            if not analysis_result.get("success"):
                return analysis_result
            
            # 3. 保存分析结果到数据库
            structured_data = analysis_result.get("structured_data", {})
            
            analysis = Analysis(
                news_id=news_id,
                agent_name=analysis_result.get("agent_name"),
                agent_role=analysis_result.get("agent_role"),
                analysis_result=analysis_result.get("analysis_result", ""),
                summary=structured_data.get("market_impact", "")[:500],
                sentiment=structured_data.get("sentiment"),
                sentiment_score=structured_data.get("sentiment_score"),
                confidence=structured_data.get("confidence"),
                structured_data=structured_data,
                execution_time=time.time() - start_time,
                llm_model=f"{llm_provider}/{llm_model}" if llm_provider and llm_model else (analyst._llm_provider.model if hasattr(analyst, '_llm_provider') and hasattr(analyst._llm_provider, 'model') else None),
            )
            
            db.add(analysis)
            
            # 4. 更新新闻的情感评分
            news.sentiment_score = structured_data.get("sentiment_score")
            
            # 5. 向量化新闻内容（如果尚未向量化）
            if not news.is_embedded:
                try:
                    # 组合标题和内容进行向量化
                    text_to_embed = f"{news.title}\n{news.content[:1000]}"
                    embedding = self.embedding_service.embed_text(text_to_embed)
                    
                    # 存储到 Milvus
                    self.vector_storage.store_embedding(
                        news_id=news_id,
                        embedding=embedding,
                        text=text_to_embed
                    )
                    
                    news.is_embedded = 1
                    logger.info(f"Vectorized news: {news_id}")
                
                except Exception as e:
                    logger.warning(f"Failed to vectorize news {news_id}: {e}")
            
            await db.commit()
            await db.refresh(analysis)
            
            logger.info(f"Analysis completed for news {news_id}, execution time: {analysis.execution_time:.2f}s")
            
            return {
                "success": True,
                "analysis_id": analysis.id,
                "news_id": news_id,
                "sentiment": analysis.sentiment,
                "sentiment_score": analysis.sentiment_score,
                "confidence": analysis.confidence,
                "summary": analysis.summary,
                "execution_time": analysis.execution_time,
            }
        
        except Exception as e:
            logger.error(f"Analysis failed for news {news_id}: {e}")
            await db.rollback()
            return {
                "success": False,
                "error": str(e)
            }
    
    async def get_analysis_by_id(
        self,
        analysis_id: int,
        db: AsyncSession
    ) -> Optional[Dict[str, Any]]:
        """
        获取分析结果
        
        Args:
            analysis_id: 分析ID
            db: 数据库会话
            
        Returns:
            分析结果或None
        """
        try:
            result = await db.execute(
                select(Analysis).where(Analysis.id == analysis_id)
            )
            analysis = result.scalar_one_or_none()
            
            if analysis:
                return analysis.to_dict()
            return None
        
        except Exception as e:
            logger.error(f"Failed to get analysis {analysis_id}: {e}")
            return None
    
    async def get_analyses_by_news_id(
        self,
        news_id: int,
        db: AsyncSession
    ) -> list:
        """
        获取指定新闻的所有分析结果（按时间倒序，最新的在前）
        
        Args:
            news_id: 新闻ID
            db: 数据库会话
            
        Returns:
            分析结果列表（最新的在前）
        """
        try:
            from sqlalchemy import desc
            
            result = await db.execute(
                select(Analysis)
                .where(Analysis.news_id == news_id)
                .order_by(desc(Analysis.created_at))  # 按创建时间倒序，最新的在前
            )
            analyses = result.scalars().all()
            
            return [analysis.to_dict() for analysis in analyses]
        
        except Exception as e:
            logger.error(f"Failed to get analyses for news {news_id}: {e}")
            return []


# 全局实例
_analysis_service: Optional[AnalysisService] = None


def get_analysis_service() -> AnalysisService:
    """
    获取分析服务实例（单例模式）
    
    Returns:
        AnalysisService 实例
    """
    global _analysis_service
    if _analysis_service is None:
        _analysis_service = AnalysisService()
    return _analysis_service

