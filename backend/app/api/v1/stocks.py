"""
股票分析 API 路由 - Phase 2
提供个股分析、关联新闻、情感趋势等接口
"""
import logging
from datetime import datetime, timedelta
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, desc

from ...core.database import get_db
from ...models.news import News
from ...models.stock import Stock
from ...models.analysis import Analysis

logger = logging.getLogger(__name__)

router = APIRouter()


# ============ Pydantic 模型 ============

class StockInfo(BaseModel):
    """股票信息"""
    model_config = {"from_attributes": True}
    
    code: str
    name: str
    full_code: Optional[str] = None
    industry: Optional[str] = None
    market: Optional[str] = None
    pe_ratio: Optional[float] = None
    market_cap: Optional[float] = None


class StockNewsItem(BaseModel):
    """股票关联新闻"""
    id: int
    title: str
    content: str
    url: str
    source: str
    publish_time: Optional[str] = None
    sentiment_score: Optional[float] = None
    has_analysis: bool = False


class SentimentTrendPoint(BaseModel):
    """情感趋势数据点"""
    date: str
    avg_sentiment: float
    news_count: int
    positive_count: int
    negative_count: int
    neutral_count: int


class StockOverview(BaseModel):
    """股票概览数据"""
    code: str
    name: Optional[str] = None
    total_news: int
    analyzed_news: int
    avg_sentiment: Optional[float] = None
    recent_sentiment: Optional[float] = None  # 最近7天
    sentiment_trend: str  # "up", "down", "stable"
    last_news_time: Optional[str] = None


class KLineDataPoint(BaseModel):
    """K线数据点（模拟数据）"""
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: int


# ============ API 端点 ============

@router.get("/{stock_code}", response_model=StockOverview)
async def get_stock_overview(
    stock_code: str,
    db: AsyncSession = Depends(get_db)
):
    """
    获取股票概览信息
    
    - **stock_code**: 股票代码（如 SH600519, 600519）
    """
    # 标准化股票代码（支持带前缀和不带前缀）
    code = stock_code.upper()
    if code.startswith("SH") or code.startswith("SZ"):
        short_code = code[2:]
    else:
        short_code = code
        code = f"SH{code}" if code.startswith("6") else f"SZ{code}"
    
    try:
        # 查询股票基本信息
        stock_query = select(Stock).where(
            (Stock.code == short_code) | (Stock.full_code == code)
        )
        result = await db.execute(stock_query)
        stock = result.scalar_one_or_none()
        
        stock_name = stock.name if stock else None
        
        # 统计关联新闻
        # 使用 PostgreSQL 的数组包含操作
        news_query = select(func.count(News.id)).where(
            News.stock_codes.any(short_code) | News.stock_codes.any(code)
        )
        result = await db.execute(news_query)
        total_news = result.scalar() or 0
        
        # 已分析的新闻数量
        analyzed_query = select(func.count(News.id)).where(
            and_(
                News.stock_codes.any(short_code) | News.stock_codes.any(code),
                News.sentiment_score.isnot(None)
            )
        )
        result = await db.execute(analyzed_query)
        analyzed_news = result.scalar() or 0
        
        # 计算平均情感
        avg_sentiment_query = select(func.avg(News.sentiment_score)).where(
            and_(
                News.stock_codes.any(short_code) | News.stock_codes.any(code),
                News.sentiment_score.isnot(None)
            )
        )
        result = await db.execute(avg_sentiment_query)
        avg_sentiment = result.scalar()
        
        # 最近7天的平均情感
        seven_days_ago = datetime.utcnow() - timedelta(days=7)
        recent_query = select(func.avg(News.sentiment_score)).where(
            and_(
                News.stock_codes.any(short_code) | News.stock_codes.any(code),
                News.sentiment_score.isnot(None),
                News.publish_time >= seven_days_ago
            )
        )
        result = await db.execute(recent_query)
        recent_sentiment = result.scalar()
        
        # 判断趋势
        if avg_sentiment is not None and recent_sentiment is not None:
            diff = recent_sentiment - avg_sentiment
            if diff > 0.1:
                sentiment_trend = "up"
            elif diff < -0.1:
                sentiment_trend = "down"
            else:
                sentiment_trend = "stable"
        else:
            sentiment_trend = "stable"
        
        # 最新新闻时间
        last_news_query = select(News.publish_time).where(
            News.stock_codes.any(short_code) | News.stock_codes.any(code)
        ).order_by(desc(News.publish_time)).limit(1)
        result = await db.execute(last_news_query)
        last_news_time = result.scalar()
        
        return StockOverview(
            code=code,
            name=stock_name,
            total_news=total_news,
            analyzed_news=analyzed_news,
            avg_sentiment=round(avg_sentiment, 3) if avg_sentiment else None,
            recent_sentiment=round(recent_sentiment, 3) if recent_sentiment else None,
            sentiment_trend=sentiment_trend,
            last_news_time=last_news_time.isoformat() if last_news_time else None
        )
    
    except Exception as e:
        logger.error(f"Failed to get stock overview for {stock_code}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{stock_code}/news", response_model=List[StockNewsItem])
async def get_stock_news(
    stock_code: str,
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    sentiment: Optional[str] = Query(None, description="筛选情感: positive, negative, neutral"),
    db: AsyncSession = Depends(get_db)
):
    """
    获取股票关联新闻列表
    
    - **stock_code**: 股票代码
    - **limit**: 返回数量限制
    - **offset**: 偏移量
    - **sentiment**: 情感筛选
    """
    # 标准化股票代码
    code = stock_code.upper()
    if code.startswith("SH") or code.startswith("SZ"):
        short_code = code[2:]
    else:
        short_code = code
        code = f"SH{code}" if code.startswith("6") else f"SZ{code}"
    
    try:
        # 构建查询
        query = select(News).where(
            News.stock_codes.any(short_code) | News.stock_codes.any(code)
        )
        
        # 情感筛选
        if sentiment:
            if sentiment == "positive":
                query = query.where(News.sentiment_score > 0.1)
            elif sentiment == "negative":
                query = query.where(News.sentiment_score < -0.1)
            elif sentiment == "neutral":
                query = query.where(
                    and_(
                        News.sentiment_score >= -0.1,
                        News.sentiment_score <= 0.1
                    )
                )
        
        # 排序和分页
        query = query.order_by(desc(News.publish_time)).offset(offset).limit(limit)
        
        result = await db.execute(query)
        news_list = result.scalars().all()
        
        # 检查每条新闻是否有分析
        response = []
        for news in news_list:
            # 检查是否有分析记录
            analysis_query = select(func.count(Analysis.id)).where(Analysis.news_id == news.id)
            analysis_result = await db.execute(analysis_query)
            has_analysis = (analysis_result.scalar() or 0) > 0
            
            response.append(StockNewsItem(
                id=news.id,
                title=news.title,
                content=news.content[:500] + "..." if len(news.content) > 500 else news.content,
                url=news.url,
                source=news.source,
                publish_time=news.publish_time.isoformat() if news.publish_time else None,
                sentiment_score=news.sentiment_score,
                has_analysis=has_analysis
            ))
        
        return response
    
    except Exception as e:
        logger.error(f"Failed to get news for stock {stock_code}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{stock_code}/sentiment-trend", response_model=List[SentimentTrendPoint])
async def get_sentiment_trend(
    stock_code: str,
    days: int = Query(30, le=90, ge=7, description="天数范围"),
    db: AsyncSession = Depends(get_db)
):
    """
    获取股票情感趋势（按天聚合）
    
    - **stock_code**: 股票代码
    - **days**: 查询天数范围（7-90天）
    """
    # 标准化股票代码
    code = stock_code.upper()
    if code.startswith("SH") or code.startswith("SZ"):
        short_code = code[2:]
    else:
        short_code = code
        code = f"SH{code}" if code.startswith("6") else f"SZ{code}"
    
    try:
        start_date = datetime.utcnow() - timedelta(days=days)
        
        # 按天聚合情感数据
        # 使用原生 SQL 进行日期聚合
        from sqlalchemy import text
        
        query = text("""
            SELECT 
                DATE(publish_time) as date,
                AVG(sentiment_score) as avg_sentiment,
                COUNT(*) as news_count,
                SUM(CASE WHEN sentiment_score > 0.1 THEN 1 ELSE 0 END) as positive_count,
                SUM(CASE WHEN sentiment_score < -0.1 THEN 1 ELSE 0 END) as negative_count,
                SUM(CASE WHEN sentiment_score >= -0.1 AND sentiment_score <= 0.1 THEN 1 ELSE 0 END) as neutral_count
            FROM news
            WHERE (
                :short_code = ANY(stock_codes) 
                OR :full_code = ANY(stock_codes)
            )
            AND publish_time >= :start_date
            AND sentiment_score IS NOT NULL
            GROUP BY DATE(publish_time)
            ORDER BY date ASC
        """)
        
        result = await db.execute(query, {
            "short_code": short_code,
            "full_code": code,
            "start_date": start_date
        })
        rows = result.fetchall()
        
        trend_data = []
        for row in rows:
            trend_data.append(SentimentTrendPoint(
                date=row.date.isoformat() if row.date else "",
                avg_sentiment=round(row.avg_sentiment, 3) if row.avg_sentiment else 0,
                news_count=row.news_count or 0,
                positive_count=row.positive_count or 0,
                negative_count=row.negative_count or 0,
                neutral_count=row.neutral_count or 0
            ))
        
        return trend_data
    
    except Exception as e:
        logger.error(f"Failed to get sentiment trend for {stock_code}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{stock_code}/kline", response_model=List[KLineDataPoint])
async def get_kline_data(
    stock_code: str,
    days: int = Query(30, le=90, ge=7),
    db: AsyncSession = Depends(get_db)
):
    """
    获取K线数据（模拟数据，用于展示）
    
    注意：这是模拟数据，实际生产环境应对接真实行情接口（如 Tushare）
    
    - **stock_code**: 股票代码
    - **days**: 天数范围
    """
    import random
    
    # 生成模拟K线数据
    kline_data = []
    base_price = 100.0  # 基准价格
    
    # 根据股票代码生成不同的基准价格（模拟）
    if "600519" in stock_code:
        base_price = 1800.0  # 茅台
    elif "000001" in stock_code:
        base_price = 15.0  # 平安银行
    elif "601318" in stock_code:
        base_price = 50.0  # 中国平安
    
    current_price = base_price
    
    for i in range(days):
        date = (datetime.utcnow() - timedelta(days=days-i-1)).strftime("%Y-%m-%d")
        
        # 随机波动
        change_percent = random.uniform(-0.03, 0.03)
        open_price = current_price
        close_price = current_price * (1 + change_percent)
        high_price = max(open_price, close_price) * (1 + random.uniform(0, 0.02))
        low_price = min(open_price, close_price) * (1 - random.uniform(0, 0.02))
        volume = random.randint(100000, 500000)
        
        kline_data.append(KLineDataPoint(
            date=date,
            open=round(open_price, 2),
            high=round(high_price, 2),
            low=round(low_price, 2),
            close=round(close_price, 2),
            volume=volume
        ))
        
        current_price = close_price
    
    return kline_data


@router.get("/search/code", response_model=List[StockInfo])
async def search_stocks(
    q: str = Query(..., min_length=1, description="搜索关键词"),
    limit: int = Query(10, le=50),
    db: AsyncSession = Depends(get_db)
):
    """
    搜索股票
    
    - **q**: 搜索关键词（代码或名称）
    """
    try:
        query = select(Stock).where(
            (Stock.code.ilike(f"%{q}%")) | 
            (Stock.name.ilike(f"%{q}%")) |
            (Stock.full_code.ilike(f"%{q}%"))
        ).limit(limit)
        
        result = await db.execute(query)
        stocks = result.scalars().all()
        
        return [StockInfo.model_validate(stock) for stock in stocks]
    
    except Exception as e:
        logger.error(f"Failed to search stocks: {e}")
        raise HTTPException(status_code=500, detail=str(e))

