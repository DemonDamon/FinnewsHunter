"""
股票分析 API 路由 - Phase 2
提供个股分析、关联新闻、情感趋势等接口
支持 akshare 真实股票数据
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
from ...models.crawl_task import CrawlTask, CrawlMode, TaskStatus
from ...services.stock_data_service import stock_data_service
from ...tasks.crawl_tasks import targeted_stock_crawl_task

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
    """K线数据点（akshare 真实数据）"""
    timestamp: int  # 时间戳（毫秒）
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: int
    turnover: Optional[float] = None  # 成交额
    change_percent: Optional[float] = None  # 涨跌幅
    change_amount: Optional[float] = None  # 涨跌额
    amplitude: Optional[float] = None  # 振幅
    turnover_rate: Optional[float] = None  # 换手率


# ============ API 端点 ============

# ⚠️ 注意：具体路径的路由必须放在动态路由 /{stock_code} 之前！

class StockSearchResult(BaseModel):
    """股票搜索结果"""
    code: str
    name: str
    full_code: str
    market: Optional[str] = None
    industry: Optional[str] = None


@router.get("/search/realtime", response_model=List[StockSearchResult])
async def search_stocks_realtime(
    q: str = Query(..., min_length=1, description="搜索关键词（代码或名称）"),
    limit: int = Query(20, le=50),
    db: AsyncSession = Depends(get_db)
):
    """
    搜索股票（从数据库，支持代码和名称模糊匹配）
    
    - **q**: 搜索关键词（如 "600519" 或 "茅台"）
    - **limit**: 返回数量限制
    """
    try:
        # 从数据库搜索
        query = select(Stock).where(
            (Stock.code.ilike(f"%{q}%")) | 
            (Stock.name.ilike(f"%{q}%")) |
            (Stock.full_code.ilike(f"%{q}%"))
        ).limit(limit)
        
        result = await db.execute(query)
        stocks = result.scalars().all()
        
        if stocks:
            return [
                StockSearchResult(
                    code=stock.code,
                    name=stock.name,
                    full_code=stock.full_code or f"{'SH' if stock.code.startswith('6') else 'SZ'}{stock.code}",
                    market=stock.market,
                    industry=stock.industry,
                )
                for stock in stocks
            ]
        
        return []
    
    except Exception as e:
        logger.error(f"Failed to search stocks: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class StockInitResponse(BaseModel):
    """股票数据初始化响应"""
    success: bool
    message: str
    count: int = 0


@router.post("/init", response_model=StockInitResponse)
async def init_stock_data(
    db: AsyncSession = Depends(get_db)
):
    """
    初始化股票数据（从 akshare 获取全部 A 股并存入数据库）
    """
    try:
        import akshare as ak
        from datetime import datetime
        from sqlalchemy import delete
        
        logger.info("Starting stock data initialization...")
        
        df = ak.stock_zh_a_spot_em()
        
        if df is None or df.empty:
            return StockInitResponse(success=False, message="Failed to fetch stocks from akshare", count=0)
        
        await db.execute(delete(Stock))
        
        count = 0
        for _, row in df.iterrows():
            code = str(row['代码'])
            name = str(row['名称'])
            
            if not code or not name or name in ['N/A', 'nan', '']:
                continue
            
            if code.startswith('6'):
                market = "SH"
                full_code = f"SH{code}"
            elif code.startswith('0') or code.startswith('3'):
                market = "SZ"
                full_code = f"SZ{code}"
            else:
                market = "OTHER"
                full_code = code
            
            stock = Stock(
                code=code,
                name=name,
                full_code=full_code,
                market=market,
                status="active",
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            db.add(stock)
            count += 1
        
        await db.commit()
        
        return StockInitResponse(success=True, message=f"Successfully initialized {count} stocks", count=count)
        
    except ImportError:
        return StockInitResponse(success=False, message="akshare not installed", count=0)
    except Exception as e:
        logger.error(f"Failed to init stocks: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/count")
async def get_stock_count(db: AsyncSession = Depends(get_db)):
    """获取数据库中的股票数量"""
    from sqlalchemy import func as sql_func
    
    result = await db.execute(select(sql_func.count(Stock.id)))
    count = result.scalar() or 0
    
    return {"count": count, "message": f"Database has {count} stocks"}


# ============ 动态路由（必须放在最后） ============

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
    period: str = Query("daily", description="周期: daily, 1m, 5m, 15m, 30m, 60m"),
    limit: int = Query(90, le=500, ge=10, description="数据条数"),
    adjust: str = Query("qfq", description="复权类型: qfq=前复权, hfq=后复权, 空=不复权（仅日线有效）"),
    db: AsyncSession = Depends(get_db)
):
    """
    获取K线数据（真实数据，使用 akshare）
    
    - **stock_code**: 股票代码（支持 600519, SH600519, sh600519 等格式）
    - **period**: 周期类型
      - daily: 日线（默认）
      - 1m: 1分钟
      - 5m: 5分钟
      - 15m: 15分钟
      - 30m: 30分钟
      - 60m: 60分钟/1小时
    - **limit**: 返回数据条数（10-500，默认90）
    - **adjust**: 复权类型 (qfq=前复权, hfq=后复权, ""=不复权)，仅对日线有效
    """
    try:
        kline_data = await stock_data_service.get_kline_data(
            stock_code=stock_code,
            period=period,
            limit=limit,
            adjust=adjust
        )
        
        if not kline_data:
            logger.warning(f"No kline data for {stock_code} period={period}")
            return []
        
        return [KLineDataPoint(**item) for item in kline_data]
    
    except Exception as e:
        logger.error(f"Failed to get kline data for {stock_code}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class RealtimeQuote(BaseModel):
    """实时行情"""
    code: str
    name: str
    price: float
    change_percent: float
    change_amount: float
    volume: int
    turnover: float
    high: float
    low: float
    open: float
    prev_close: float


@router.get("/{stock_code}/realtime", response_model=Optional[RealtimeQuote])
async def get_realtime_quote(
    stock_code: str,
    db: AsyncSession = Depends(get_db)
):
    """
    获取实时行情（使用 akshare）
    
    - **stock_code**: 股票代码
    """
    try:
        quote = await stock_data_service.get_realtime_quote(stock_code)
        if quote:
            return RealtimeQuote(**quote)
        return None
    except Exception as e:
        logger.error(f"Failed to get realtime quote for {stock_code}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/search/code", response_model=List[StockInfo])
async def search_stocks_db(
    q: str = Query(..., min_length=1, description="搜索关键词"),
    limit: int = Query(10, le=50),
    db: AsyncSession = Depends(get_db)
):
    """
    从数据库搜索股票
    
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


# ============ 定向爬取 API ============

class TargetedCrawlRequest(BaseModel):
    """定向爬取请求"""
    stock_name: str = Field(..., description="股票名称")
    days: int = Field(default=30, ge=1, le=90, description="搜索时间范围（天）")


class TargetedCrawlResponse(BaseModel):
    """定向爬取响应"""
    success: bool
    message: str
    task_id: Optional[int] = None
    celery_task_id: Optional[str] = None


class TargetedCrawlStatus(BaseModel):
    """定向爬取状态"""
    task_id: Optional[int] = None
    status: str  # idle, pending, running, completed, failed
    celery_task_id: Optional[str] = None
    progress: Optional[dict] = None
    crawled_count: Optional[int] = None
    saved_count: Optional[int] = None
    error_message: Optional[str] = None
    execution_time: Optional[float] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None


@router.post("/{stock_code}/targeted-crawl", response_model=TargetedCrawlResponse)
async def start_targeted_crawl(
    stock_code: str,
    request: TargetedCrawlRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    触发定向爬取任务
    
    - **stock_code**: 股票代码（如 SH600519）
    - **stock_name**: 股票名称（如 贵州茅台）
    - **days**: 搜索时间范围（默认30天）
    """
    try:
        # 标准化股票代码
        code = stock_code.upper()
        if not (code.startswith("SH") or code.startswith("SZ")):
            code = f"SH{code}" if code.startswith("6") else f"SZ{code}"
        
        # 检查是否有正在运行的任务
        running_task = await db.execute(
            select(CrawlTask).where(
                and_(
                    CrawlTask.mode == CrawlMode.TARGETED,
                    CrawlTask.status.in_([TaskStatus.PENDING, TaskStatus.RUNNING]),
                    CrawlTask.config['stock_code'].astext == code
                )
            ).order_by(desc(CrawlTask.created_at)).limit(1)
        )
        existing_task = running_task.scalar_one_or_none()
        
        if existing_task:
            return TargetedCrawlResponse(
                success=False,
                message=f"该股票已有正在进行的爬取任务 (ID: {existing_task.id})",
                task_id=existing_task.id,
                celery_task_id=existing_task.celery_task_id
            )
        
        logger.info(f"触发定向爬取任务: {request.stock_name}({code}), 时间范围: {request.days}天")
        
        # 触发 Celery 任务
        celery_task = targeted_stock_crawl_task.apply_async(
            args=(code, request.stock_name, request.days)
        )
        
        return TargetedCrawlResponse(
            success=True,
            message=f"定向爬取任务已启动: {request.stock_name}({code})",
            celery_task_id=celery_task.id
        )
    
    except Exception as e:
        logger.error(f"Failed to start targeted crawl for {stock_code}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{stock_code}/targeted-crawl/status", response_model=TargetedCrawlStatus)
async def get_targeted_crawl_status(
    stock_code: str,
    db: AsyncSession = Depends(get_db)
):
    """
    查询定向爬取任务状态
    
    - **stock_code**: 股票代码
    """
    try:
        # 标准化股票代码
        code = stock_code.upper()
        if not (code.startswith("SH") or code.startswith("SZ")):
            code = f"SH{code}" if code.startswith("6") else f"SZ{code}"
        
        # 查询最近的定向爬取任务
        task_query = select(CrawlTask).where(
            and_(
                CrawlTask.mode == CrawlMode.TARGETED,
                CrawlTask.config['stock_code'].astext == code
            )
        ).order_by(desc(CrawlTask.created_at)).limit(1)
        
        result = await db.execute(task_query)
        task = result.scalar_one_or_none()
        
        if not task:
            return TargetedCrawlStatus(
                status="idle",
                progress=None
            )
        
        return TargetedCrawlStatus(
            task_id=task.id,
            status=task.status,
            celery_task_id=task.celery_task_id,
            progress=task.progress,
            crawled_count=task.crawled_count,
            saved_count=task.saved_count,
            error_message=task.error_message,
            execution_time=task.execution_time,
            started_at=task.started_at.isoformat() if task.started_at else None,
            completed_at=task.completed_at.isoformat() if task.completed_at else None
        )
    
    except Exception as e:
        logger.error(f"Failed to get targeted crawl status for {stock_code}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
