"""
Celery 爬取任务 - Phase 2: 实时监控升级版 + 多源支持
"""
import logging
import json
from datetime import datetime, timedelta
from typing import List, Dict, Any
from sqlalchemy import select, create_engine, text
from sqlalchemy.orm import Session
import asyncio

from ..core.celery_app import celery_app
from ..core.config import settings
from ..core.redis_client import redis_client
from ..models.crawl_task import CrawlTask, CrawlMode, TaskStatus
from ..models.news import News
from ..tools import (
    SinaCrawlerTool,
    TencentCrawlerTool,
    JwviewCrawlerTool,
    EeoCrawlerTool,
    CaijingCrawlerTool,
    Jingji21CrawlerTool,
    NbdCrawlerTool,
    YicaiCrawlerTool,
    Netease163CrawlerTool,
    EastmoneyCrawlerTool,
    bochaai_search,
    NewsItem,
)
from ..tools.crawler_enhanced import EnhancedCrawler, crawl_url

logger = logging.getLogger(__name__)


def get_crawler_tool(source: str):
    """
    爬虫工厂函数
    
    Args:
        source: 新闻源名称
        
    Returns:
        对应的爬虫实例
    """
    crawlers = {
        "sina": SinaCrawlerTool,
        "tencent": TencentCrawlerTool,
        "jwview": JwviewCrawlerTool,
        "eeo": EeoCrawlerTool,
        "caijing": CaijingCrawlerTool,
        "jingji21": Jingji21CrawlerTool,
        "nbd": NbdCrawlerTool,
        "yicai": YicaiCrawlerTool,
        "163": Netease163CrawlerTool,
        "eastmoney": EastmoneyCrawlerTool,
    }
    
    crawler_class = crawlers.get(source)
    if not crawler_class:
        raise ValueError(f"Unknown news source: {source}")
    
    return crawler_class()


def get_sync_db_session():
    """获取同步数据库会话（Celery任务中使用）"""
    engine = create_engine(settings.SYNC_DATABASE_URL)
    return Session(engine)


@celery_app.task(bind=True, name="app.tasks.crawl_tasks.realtime_crawl_task")
def realtime_crawl_task(self, source: str = "sina", force_refresh: bool = False):
    """
    实时爬取任务 (Phase 2 升级版)
    
    核心改进：
    1. Redis 缓存检查（避免频繁爬取）
    2. 智能时间过滤（基于配置的 NEWS_RETENTION_HOURS）
    3. 只爬取最新一页
    
    Args:
        source: 新闻源（sina, jrj等）
        force_refresh: 是否强制刷新（跳过缓存）
    """
    db = get_sync_db_session()
    task_record = None
    cache_key = f"news:{source}:latest"
    cache_time_key = f"{cache_key}:timestamp"
    
    try:
        # ===== Phase 2.1: 检查 Redis 缓存 =====
        if not force_refresh and redis_client.is_available():
            cache_metadata = redis_client.get_cache_metadata(cache_key)
            
            if cache_metadata:
                age_seconds = cache_metadata['age_seconds']
                # 根据不同源获取对应的爬取间隔
                interval_map = {
                    "sina": settings.CRAWL_INTERVAL_SINA,
                    "tencent": settings.CRAWL_INTERVAL_TENCENT,
                    "jwview": settings.CRAWL_INTERVAL_JWVIEW,
                    "eeo": settings.CRAWL_INTERVAL_EEO,
                    "caijing": settings.CRAWL_INTERVAL_CAIJING,
                    "jingji21": settings.CRAWL_INTERVAL_JINGJI21,
                    "nbd": 60,  # 每日经济新闻
                    "yicai": 60,  # 第一财经
                    "163": 60,  # 网易财经
                    "eastmoney": 60,  # 东方财富
                }
                interval = interval_map.get(source, 60)  # 默认60秒
                
                # 如果缓存时间 < 爬取间隔，使用缓存
                if age_seconds < interval:
                    logger.info(
                        f"[{source}] 使用缓存数据 (age: {age_seconds:.0f}s < {interval}s)"
                    )
                    return {
                        "status": "cached",
                        "source": source,
                        "cache_age": age_seconds,
                        "message": f"缓存数据仍然有效，距上次爬取 {age_seconds:.0f} 秒"
                    }
        
        # ===== 1. 创建任务记录 =====
        task_record = CrawlTask(
            celery_task_id=self.request.id,
            mode=CrawlMode.REALTIME,
            status=TaskStatus.RUNNING,
            source=source,
            config={
                "page_limit": 1, 
                "retention_hours": settings.NEWS_RETENTION_HOURS,
                "force_refresh": force_refresh
            },
            started_at=datetime.utcnow(),
        )
        db.add(task_record)
        db.commit()
        db.refresh(task_record)
        
        logger.info(f"[Task {task_record.id}] 🚀 开始实时爬取: {source}")
        
        # ===== 2. 创建爬虫（使用工厂函数） =====
        try:
            crawler = get_crawler_tool(source)
        except ValueError as e:
            logger.error(f"[Task {task_record.id}] ❌ {e}")
            raise
        
        # ===== 3. 执行爬取（只爬第一页） =====
        start_time = datetime.utcnow()
        news_list = crawler.crawl(start_page=1, end_page=1)
        
        logger.info(f"[Task {task_record.id}] 📰 爬取到 {len(news_list)} 条新闻")
        
        # ===== Phase 2.2: 智能时间过滤 =====
        cutoff_time = datetime.utcnow() - timedelta(hours=settings.NEWS_RETENTION_HOURS)
        recent_news = [
            news for news in news_list
            if news.publish_time and news.publish_time > cutoff_time
        ] if news_list else []
        
        logger.info(
            f"[Task {task_record.id}] ⏱️  过滤后剩余 {len(recent_news)} 条新闻 "
            f"(保留 {settings.NEWS_RETENTION_HOURS} 小时内)"
        )
        
        # ===== 4. 去重并保存 =====
        saved_count = 0
        duplicate_count = 0
        
        for news_item in recent_news:
            # 检查URL是否已存在
            existing = db.execute(
                select(News).where(News.url == news_item.url)
            ).scalar_one_or_none()
            
            if existing:
                duplicate_count += 1
                logger.debug(f"[Task {task_record.id}] ⏭️  跳过重复新闻: {news_item.title[:30]}...")
                continue
            
            # 创建新记录
            news = News(
                title=news_item.title,
                content=news_item.content,
                raw_html=news_item.raw_html,  # 保存原始 HTML
                url=news_item.url,
                source=news_item.source,
                publish_time=news_item.publish_time,
                author=news_item.author,
                keywords=news_item.keywords,
                stock_codes=news_item.stock_codes,
            )
            
            db.add(news)
            saved_count += 1
        
        db.commit()
        
        logger.info(
            f"[Task {task_record.id}] 💾 保存 {saved_count} 条新新闻 "
            f"(重复: {duplicate_count})"
        )
        
        # ===== Phase 2.3: 更新 Redis 缓存 =====
        if redis_client.is_available() and recent_news:
            # 将新闻列表序列化后存入缓存
            cache_data = [
                {
                    "title": n.title,
                    "url": n.url,
                    "publish_time": n.publish_time.isoformat() if n.publish_time else None,
                    "source": n.source,
                }
                for n in recent_news
            ]
            success = redis_client.set_with_metadata(
                cache_key, 
                cache_data, 
                ttl=settings.CACHE_TTL
            )
            if success:
                logger.info(f"[Task {task_record.id}] 💾 Redis 缓存已更新 (TTL: {settings.CACHE_TTL}s)")
        
        # ===== 5. 更新任务状态 =====
        end_time = datetime.utcnow()
        execution_time = (end_time - start_time).total_seconds()
        
        task_record.status = TaskStatus.COMPLETED
        task_record.completed_at = end_time
        task_record.execution_time = execution_time
        task_record.crawled_count = len(recent_news)
        task_record.saved_count = saved_count
        task_record.result = {
            "total_crawled": len(news_list),
            "filtered": len(recent_news),
            "saved": saved_count,
            "duplicates": duplicate_count,
            "retention_hours": settings.NEWS_RETENTION_HOURS,
        }
        db.commit()
        
        logger.info(
            f"[Task {task_record.id}] ✅ 完成! "
            f"爬取: {len(news_list)} → 过滤: {len(recent_news)} → 保存: {saved_count}, "
            f"耗时: {execution_time:.2f}s"
        )
        
        return {
            "task_id": task_record.id,
            "status": "completed",
            "source": source,
            "crawled": len(news_list),
            "filtered": len(recent_news),
            "saved": saved_count,
            "duplicates": duplicate_count,
            "execution_time": execution_time,
            "timestamp": datetime.utcnow().isoformat(),
        }
        
    except Exception as e:
        logger.error(f"[Task {task_record.id if task_record else 'unknown'}] 爬取失败: {e}", exc_info=True)
        
        if task_record:
            task_record.status = TaskStatus.FAILED
            task_record.completed_at = datetime.utcnow()
            task_record.error_message = str(e)[:1000]
            db.commit()
        
        # 重新抛出异常，让 Celery 记录
        raise
    
    finally:
        db.close()


@celery_app.task(bind=True, name="app.tasks.crawl_tasks.cold_start_crawl_task")
def cold_start_crawl_task(
    self,
    source: str = "sina",
    start_page: int = 1,
    end_page: int = 50,
):
    """
    冷启动批量爬取任务
    
    Args:
        source: 新闻源
        start_page: 起始页
        end_page: 结束页
    """
    db = get_sync_db_session()
    task_record = None
    
    try:
        # 1. 创建任务记录
        task_record = CrawlTask(
            celery_task_id=self.request.id,
            mode=CrawlMode.COLD_START,
            status=TaskStatus.RUNNING,
            source=source,
            config={
                "start_page": start_page,
                "end_page": end_page,
            },
            total_pages=end_page - start_page + 1,
            started_at=datetime.utcnow(),
        )
        db.add(task_record)
        db.commit()
        db.refresh(task_record)
        
        logger.info(f"[Task {task_record.id}] 开始冷启动爬取: {source}, 页码 {start_page}-{end_page}")
        
        # 2. 创建爬虫
        if source == "sina":
            crawler = SinaCrawlerTool()
        else:
            raise ValueError(f"不支持的新闻源: {source}")
        
        # 3. 分页爬取
        start_time = datetime.utcnow()
        total_crawled = 0
        total_saved = 0
        
        for page in range(start_page, end_page + 1):
            try:
                # 更新进度
                task_record.current_page = page
                task_record.progress = {
                    "current_page": page,
                    "total_pages": task_record.total_pages,
                    "percentage": round((page - start_page + 1) / task_record.total_pages * 100, 2),
                }
                db.commit()
                
                # 爬取单页
                news_list = crawler.crawl(start_page=page, end_page=page)
                total_crawled += len(news_list)
                
                # 保存新闻
                page_saved = 0
                for news_item in news_list:
                    existing = db.execute(
                        select(News).where(News.url == news_item.url)
                    ).scalar_one_or_none()
                    
                    if not existing:
                        news = News(
                            title=news_item.title,
                            content=news_item.content,
                            raw_html=news_item.raw_html,  # 保存原始 HTML
                            url=news_item.url,
                            source=news_item.source,
                            publish_time=news_item.publish_time,
                            author=news_item.author,
                            keywords=news_item.keywords,
                            stock_codes=news_item.stock_codes,
                        )
                        db.add(news)
                        page_saved += 1
                
                db.commit()
                total_saved += page_saved
                
                logger.info(
                    f"[Task {task_record.id}] 页 {page}/{end_page}: "
                    f"爬取 {len(news_list)} 条, 保存 {page_saved} 条"
                )
                
            except Exception as e:
                logger.error(f"[Task {task_record.id}] 页 {page} 爬取失败: {e}")
                continue
        
        # 4. 更新任务状态
        end_time = datetime.utcnow()
        execution_time = (end_time - start_time).total_seconds()
        
        task_record.status = TaskStatus.COMPLETED
        task_record.completed_at = end_time
        task_record.execution_time = execution_time
        task_record.crawled_count = total_crawled
        task_record.saved_count = total_saved
        task_record.result = {
            "pages_crawled": end_page - start_page + 1,
            "total_crawled": total_crawled,
            "total_saved": total_saved,
            "duplicates": total_crawled - total_saved,
        }
        db.commit()
        
        logger.info(
            f"[Task {task_record.id}] 冷启动完成! "
            f"页数: {end_page - start_page + 1}, 爬取: {total_crawled}, 保存: {total_saved}, "
            f"耗时: {execution_time:.2f}s"
        )
        
        return {
            "task_id": task_record.id,
            "status": "completed",
            "crawled": total_crawled,
            "saved": total_saved,
            "execution_time": execution_time,
        }
        
    except Exception as e:
        logger.error(f"[Task {task_record.id if task_record else 'unknown'}] 冷启动失败: {e}", exc_info=True)
        
        if task_record:
            task_record.status = TaskStatus.FAILED
            task_record.completed_at = datetime.utcnow()
            task_record.error_message = str(e)[:1000]
            db.commit()
        
        raise
    
    finally:
        db.close()


@celery_app.task(bind=True, name="app.tasks.crawl_tasks.targeted_stock_crawl_task")
def targeted_stock_crawl_task(
    self,
    stock_code: str,
    stock_name: str,
    days: int = 30,
    task_record_id: int = None
):
    """
    定向爬取某只股票的相关新闻（精简版 - 只使用 BochaAI）
    
    数据来源：BochaAI 搜索引擎 API
    
    图谱构建逻辑：
    - 有历史新闻数据 → 先构建/使用图谱 → 基于图谱扩展关键词搜索
    - 无历史新闻数据 → 先用 BochaAI 爬取 → 爬取完成后异步构建图谱
    
    Args:
        stock_code: 股票代码（如 SH600519）
        stock_name: 股票名称（如 贵州茅台）
        days: 搜索时间范围（天），默认30天
        task_record_id: 数据库中的任务记录ID（如果已创建）
    """
    db = get_sync_db_session()
    task_record = None
    
    try:
        # 标准化股票代码
        code = stock_code.upper()
        if code.startswith("SH") or code.startswith("SZ"):
            pure_code = code[2:]
        else:
            pure_code = code
            code = f"SH{code}" if code.startswith("6") else f"SZ{code}"
        
        # 1. 获取或创建任务记录
        if task_record_id:
            task_record = db.query(CrawlTask).filter(CrawlTask.id == task_record_id).first()
            if task_record:
                task_record.status = TaskStatus.RUNNING
                task_record.started_at = datetime.utcnow()
                db.commit()
                db.refresh(task_record)
            else:
                logger.warning(f"Task record {task_record_id} not found, creating new one")
                task_record_id = None
        
        if not task_record:
            task_record = CrawlTask(
                celery_task_id=self.request.id,
                mode=CrawlMode.TARGETED,
                status=TaskStatus.RUNNING,
                source="targeted",
                config={
                    "stock_code": code,
                    "stock_name": stock_name,
                    "days": days,
                },
                started_at=datetime.utcnow(),
            )
            db.add(task_record)
            db.commit()
            db.refresh(task_record)
        
        logger.info(f"[Task {task_record.id}] 🎯 开始定向爬取: {stock_name}({code}), 时间范围: {days}天")
        
        start_time = datetime.utcnow()
        all_news = []
        search_results = []
        
        # ========================================
        # 【核心逻辑】先用 akshare 获取股票基础信息，构建简单图谱
        # ========================================
        task_record.progress = {"current": 5, "total": 100, "message": "获取股票基础信息..."}
        db.commit()
        
        from ..knowledge.knowledge_extractor import AkshareKnowledgeExtractor
        
        # 1. 从 akshare 获取公司基础信息
        logger.info(f"[Task {task_record.id}] 🔍 从 akshare 获取 {stock_name}({pure_code}) 基础信息...")
        akshare_info = None
        try:
            akshare_info = AkshareKnowledgeExtractor.extract_company_info(pure_code)
            if akshare_info:
                logger.info(f"[Task {task_record.id}] ✅ akshare 返回: 行业={akshare_info.get('industry')}, 主营={akshare_info.get('main_business', '')[:50]}...")
            else:
                logger.warning(f"[Task {task_record.id}] ⚠️ akshare 未返回数据，将使用股票名称生成关键词")
        except Exception as e:
            logger.warning(f"[Task {task_record.id}] ⚠️ akshare 查询失败: {e}，将使用股票名称生成关键词")
        
        # 2. 构建简单图谱并生成搜索关键词
        task_record.progress = {"current": 10, "total": 100, "message": "构建知识图谱..."}
        db.commit()
        
        simple_graph = AkshareKnowledgeExtractor.build_simple_graph_from_info(
            stock_code=code,
            stock_name=stock_name,
            akshare_info=akshare_info
        )
        
        # 获取分层关键词
        core_keywords = simple_graph.get("core_keywords", [stock_name])
        extension_keywords = simple_graph.get("extension_keywords", [])
        
        logger.info(
            f"[Task {task_record.id}] 📋 关键词分层: "
            f"核心={len(core_keywords)}个{core_keywords[:4]}, "
            f"扩展={len(extension_keywords)}个{extension_keywords[:4]}"
        )
        logger.info(f"[Task {task_record.id}] 🔑 完整核心关键词列表: {core_keywords}")
        logger.info(f"[Task {task_record.id}] 🔑 完整扩展关键词列表: {extension_keywords}")
        
        # ========================================
        # 【搜索阶段】使用组合关键词调用 BochaAI 搜索
        # ========================================
        task_record.progress = {"current": 20, "total": 100, "message": "BochaAI 组合搜索中..."}
        db.commit()
        
        if not bochaai_search.is_available():
            logger.error(f"[Task {task_record.id}] ❌ BochaAI API Key 未配置，无法执行搜索")
            raise ValueError("BochaAI API Key 未配置")
        
        # ========================================
        # 【组合搜索策略】
        # 1. 必须搜索：核心关键词（公司名、代码）
        # 2. 可选组合：核心词 + 扩展词（行业、业务、人名）
        # ========================================
        all_search_results = []
        search_queries = []
        
        # 策略1：核心关键词单独搜索（取前3个最重要的）
        for core_kw in core_keywords[:3]:
            # 跳过纯数字代码（单独搜会很泛）
            if not (core_kw.isdigit() or core_kw.startswith("SH") or core_kw.startswith("SZ")):
                search_queries.append(core_kw)
        
        # 策略2：核心词 + 扩展词组合搜索（最多3个组合）
        if extension_keywords:
            # 取最主要的核心词（通常是股票简称）
            main_core = core_keywords[0] if core_keywords else stock_name
            
            for ext_kw in extension_keywords[:3]:
                # 组合搜索：如 "*ST国华 软件开发"
                combined_query = f"{main_core} {ext_kw}"
                search_queries.append(combined_query)
        
        # 限制总查询数（避免过多请求）
        search_queries = search_queries[:5]
        
        logger.info(f"[Task {task_record.id}] 🚀 生成 {len(search_queries)} 个搜索查询:")
        for i, q in enumerate(search_queries):
            logger.info(f"  [{i+1}] {q}")
        
        # 执行搜索
        for query in search_queries:
            try:
                logger.info(f"[Task {task_record.id}] 🔍 搜索: '{query}'")
                kw_results = bochaai_search.search_stock_news(
                    stock_name=query,  # 使用组合查询
                    stock_code=pure_code,
                    days=days,
                    count=50,  # 每个查询最多 50 条
                    max_age_days=365
                )
                logger.info(f"[Task {task_record.id}] 📰 查询 '{query}' 搜索到 {len(kw_results)} 条结果")
                all_search_results.extend(kw_results)
            except Exception as e:
                logger.warning(f"[Task {task_record.id}] ⚠️ 查询 '{query}' 搜索失败: {e}")
        
        # 去重（按 URL）
        seen_urls = set()
        search_results = []
        for r in all_search_results:
            if r.url not in seen_urls:
                seen_urls.add(r.url)
                search_results.append(r)
        
        logger.info(f"[Task {task_record.id}] 📊 合并 {len(all_search_results)} 条，去重后 {len(search_results)} 条")
        
        # ========================================
        # 【处理阶段】转换搜索结果为 NewsItem
        # ========================================
        task_record.progress = {"current": 50, "total": 100, "message": "处理搜索结果..."}
        db.commit()
        
        bochaai_matched = 0
        bochaai_filtered = 0
        
        # 检查是否应该启用宽松过滤模式
        # 如果核心关键词太少（<= 2个），或者搜索结果很少（<10条），使用宽松过滤
        use_relaxed_filter = len(core_keywords) <= 2 or len(search_results) < 10
        if use_relaxed_filter:
            logger.info(f"[Task {task_record.id}] 🔓 启用宽松过滤模式（核心词={len(core_keywords)}个, 结果={len(search_results)}条）")
        
        # 打印 BochaAI 返回的前 10 条数据用于调试
        logger.info(f"[Task {task_record.id}] 📋 BochaAI 返回数据预览 (前10条):")
        for i, r in enumerate(search_results[:10]):
            logger.info(f"  [{i+1}] 标题: {r.title[:60]}...")
            logger.info(f"      来源: {r.site_name}, 日期: {r.date_published}")
            logger.info(f"      URL: {r.url[:80]}...")
        
        for idx, result in enumerate(search_results):
            # 解析发布时间
            publish_time = None
            if result.date_published:
                try:
                    publish_time = datetime.fromisoformat(
                        result.date_published.replace('Z', '+00:00')
                    )
                except (ValueError, AttributeError):
                    pass
            
            # 【注意】不再二次爬取完整内容，直接使用摘要（提升速度）
            full_content = result.snippet
            
            # 相关性过滤：必须包含至少一个核心关键词
            text_to_check = result.title + " " + result.snippet
            text_to_check_lower = text_to_check.lower()
            
            # 检查是否匹配任何核心关键词
            is_match = False
            matched_keyword = None
            for kw in core_keywords:
                if not kw or len(kw) < 2:
                    continue
                
                kw_lower = kw.lower()
                
                # 宽松匹配策略：
                # 1. 完整匹配（大小写不敏感）
                if kw in text_to_check or kw_lower in text_to_check_lower:
                    is_match = True
                    matched_keyword = kw
                    break
                
                # 2. 去除特殊字符后匹配（处理 *ST 等情况）
                import re
                kw_clean = re.sub(r'[*\s]', '', kw)
                if len(kw_clean) >= 2 and kw_clean.lower() in text_to_check_lower:
                    is_match = True
                    matched_keyword = f"{kw} (cleaned: {kw_clean})"
                    break
            
            if not is_match:
                # 宽松模式下，如果标题包含股票代码数字，也认为相关
                if use_relaxed_filter and pure_code in text_to_check:
                    is_match = True
                    matched_keyword = f"{pure_code} (relaxed mode)"
                    logger.debug(f"[Task {task_record.id}] 🔓 宽松模式匹配: {result.title[:40]}... (包含代码)")
                else:
                    bochaai_filtered += 1
                    # 打印前 5 条被过滤的原因
                    if bochaai_filtered <= 5:
                        logger.info(f"[Task {task_record.id}] ❌ 过滤[{idx+1}]: 不包含核心关键词")
                        logger.info(f"      标题: {result.title[:80]}")
                        logger.info(f"      摘要: {result.snippet[:100]}...")
                        logger.info(f"      核心词: {core_keywords}")
                    continue
            
            # 如果宽松模式跳过了上面的 continue，需要确保 is_match 为 True
            if not is_match:
                continue
            
            logger.debug(f"[Task {task_record.id}] ✅ 匹配核心词 '{matched_keyword}': {result.title[:40]}...")
            
            bochaai_matched += 1
            news_item = NewsItem(
                title=result.title,
                content=full_content,
                url=result.url,
                source=result.site_name or "web_search",
                publish_time=publish_time,
                stock_codes=[pure_code, code],
                raw_html=None,
            )
            all_news.append(news_item)
            
            # 每处理 20 条更新一次进度
            if (idx + 1) % 20 == 0:
                progress_pct = 50 + int((idx + 1) / len(search_results) * 30)
                task_record.progress = {"current": progress_pct, "total": 100, "message": f"处理中 {idx+1}/{len(search_results)}..."}
                db.commit()
        
        logger.info(f"[Task {task_record.id}] 🔍 搜索到 {len(search_results)} 条，匹配 {bochaai_matched} 条，过滤 {bochaai_filtered} 条")
        
        # ========================================
        # 【交互式爬虫补充】如果相关性匹配结果太少，使用交互式爬虫补充
        # ========================================
        if bochaai_matched < 5:  # 匹配结果太少时启动交互式爬虫
            logger.info(f"[Task {task_record.id}] 🌐 相关结果较少({bochaai_matched}条)，启用交互式爬虫补充...")
            
            try:
                from ..tools.interactive_crawler import create_interactive_crawler
                
                # 使用核心关键词进行搜索
                # 取最主要的核心词（通常是股票简称）
                interactive_query = core_keywords[0] if core_keywords else stock_name
                
                logger.info(f"[Task {task_record.id}] 🔍 使用交互式爬虫搜索: '{interactive_query}'")
                
                crawler = create_interactive_crawler(headless=True)
                interactive_results = crawler.interactive_search(
                    interactive_query,
                    engines=["bing"],  # 优先 Bing（更稳定）
                    num_results=15,
                    headless=True
                )
                
                logger.info(f"[Task {task_record.id}] ✅ 交互式爬虫返回 {len(interactive_results)} 条结果")
                
                # 爬取页面内容
                interactive_crawled = crawler.crawl_search_results(
                    interactive_results,
                    max_results=5
                )
                
                logger.info(f"[Task {task_record.id}] 📄 交互式爬虫爬取成功: {len(interactive_crawled)} 个页面")
                
                # 添加到新闻列表
                for page in interactive_crawled:
                    if page['url'] not in {item.url for item in all_news}:
                        news_item = NewsItem(
                            title=page['title'],
                            content=page['content'][:500],  # 只取前 500 字作为摘要
                            url=page['url'],
                            source=page.get('source', 'web_search'),
                            publish_time=None,  # 交互爬虫没有发布时间
                            stock_codes=[pure_code, code],
                            raw_html=None,
                        )
                        all_news.append(news_item)
                        bochaai_matched += 1
                
                logger.info(f"[Task {task_record.id}] 📊 交互式爬虫补充后总计: {bochaai_matched} 条匹配结果")
                
            except ImportError:
                logger.warning(f"[Task {task_record.id}] ⚠️ 交互式爬虫模块不可用，跳过补充搜索")
            except Exception as e:
                logger.error(f"[Task {task_record.id}] ❌ 交互式爬虫补充失败: {e}", exc_info=True)
        
        # ========================================
        # 【保存阶段】去重并保存新闻
        # ========================================
        task_record.progress = {"current": 80, "total": 100, "message": "保存新闻..."}
        db.commit()
        saved_count = 0
        duplicate_count = 0
        
        logger.info(f"[Task {task_record.id}] 💾 开始保存 {len(all_news)} 条新闻...")
        
        for news_item in all_news:
            # 检查URL是否已存在
            existing = db.execute(
                select(News).where(News.url == news_item.url)
            ).scalar_one_or_none()
            
            if existing:
                duplicate_count += 1
                # 如果已存在但没有关联这个股票，更新关联
                if existing.stock_codes is None:
                    existing.stock_codes = []
                if pure_code not in existing.stock_codes:
                    existing.stock_codes = existing.stock_codes + [pure_code]
                    db.commit()
                continue
            
            # 创建新记录
            news = News(
                title=news_item.title,
                content=news_item.content,
                raw_html=news_item.raw_html,  # 保存原始 HTML
                url=news_item.url,
                source=news_item.source,
                publish_time=news_item.publish_time,
                author=news_item.author,
                keywords=news_item.keywords,
                stock_codes=news_item.stock_codes or [pure_code, code],
            )
            
            db.add(news)
            saved_count += 1
        
        db.commit()
        
        logger.info(
            f"[Task {task_record.id}] 💾 保存 {saved_count} 条新闻 "
            f"(重复: {duplicate_count})"
        )
        
        # ========================================
        # 【图谱更新阶段】异步构建完整图谱（基于 Neo4j）
        # ========================================
        task_record.progress = {"current": 90, "total": 100, "message": "触发异步图谱构建..."}
        db.commit()
        
        if saved_count > 0:
            # 有新闻保存成功后，触发异步图谱构建任务
            logger.info(f"[Task {task_record.id}] 🧠 触发异步图谱构建任务...")
            try:
                build_knowledge_graph_task.delay(code, stock_name)
                logger.info(f"[Task {task_record.id}] ✅ 异步图谱构建任务已触发")
            except Exception as e:
                logger.error(f"[Task {task_record.id}] ❌ 触发异步图谱构建失败: {e}")
        
        # ========================================
        # 【完成阶段】更新任务状态
        # ========================================
        end_time = datetime.utcnow()
        execution_time = (end_time - start_time).total_seconds()
        
        task_record.status = TaskStatus.COMPLETED
        task_record.completed_at = end_time
        task_record.execution_time = execution_time
        task_record.crawled_count = len(all_news)
        task_record.saved_count = saved_count
        task_record.result = {
            "stock_code": code,
            "stock_name": stock_name,
            "total_found": len(all_news),
            "saved": saved_count,
            "duplicates": duplicate_count,
            "akshare_info": bool(akshare_info),  # 是否获取到 akshare 数据
            "core_keywords": core_keywords[:5],  # 核心关键词
            "search_queries": search_queries,  # 实际搜索的查询
            "sources": {
                "bochaai": len(search_results),
            }
        }
        task_record.progress = {
            "current": 100,
            "total": 100,
            "message": f"完成！新增 {saved_count} 条新闻"
        }
        db.commit()
        
        logger.info(
            f"[Task {task_record.id}] ✅ 定向爬取完成! "
            f"股票: {stock_name}({code}), 找到: {len(all_news)}, 保存: {saved_count}, "
            f"耗时: {execution_time:.2f}s"
        )
        
        return {
            "task_id": task_record.id,
            "status": "completed",
            "stock_code": code,
            "stock_name": stock_name,
            "crawled": len(all_news),
            "saved": saved_count,
            "duplicates": duplicate_count,
            "execution_time": execution_time,
            "timestamp": datetime.utcnow().isoformat(),
        }
        
    except Exception as e:
        logger.error(f"[Task {task_record.id if task_record else 'unknown'}] 定向爬取失败: {e}", exc_info=True)
        
        if task_record:
            task_record.status = TaskStatus.FAILED
            task_record.completed_at = datetime.utcnow()
            task_record.error_message = str(e)[:1000]
            task_record.progress = {
                "current": 0,
                "total": 100,
                "message": f"失败: {str(e)[:100]}"
            }
            db.commit()
        
        raise
    
    finally:
        db.close()


@celery_app.task(bind=True, name="app.tasks.crawl_tasks.build_knowledge_graph_task")
def build_knowledge_graph_task(self, stock_code: str, stock_name: str):
    """
    异步构建知识图谱任务
    
    在无历史新闻数据的股票首次爬取完成后触发。
    从数据库中的新闻数据 + akshare 基础信息构建知识图谱。
    
    Args:
        stock_code: 股票代码（如 SH600519）
        stock_name: 股票名称（如 贵州茅台）
    """
    db = get_sync_db_session()
    
    try:
        code = stock_code.upper()
        if code.startswith("SH") or code.startswith("SZ"):
            pure_code = code[2:]
        else:
            pure_code = code
            code = f"SH{code}" if code.startswith("6") else f"SZ{code}"
        
        logger.info(f"[GraphTask] 🏗️ 开始异步构建知识图谱: {stock_name}({code})")
        
        from ..knowledge.graph_service import get_graph_service
        from ..knowledge.knowledge_extractor import (
            create_knowledge_extractor,
            AkshareKnowledgeExtractor
        )
        
        graph_service = get_graph_service()
        
        # 1. 检查图谱是否已存在（避免重复构建）
        existing_graph = graph_service.get_company_graph(code)
        if existing_graph:
            logger.info(f"[GraphTask] ✅ 图谱已存在，跳过构建")
            return {"status": "skipped", "reason": "graph_exists"}
        
        # 2. 从 akshare 获取基础公司信息
        akshare_info = AkshareKnowledgeExtractor.extract_company_info(code)
        
        if akshare_info:
            extractor = create_knowledge_extractor()
            base_graph = asyncio.run(
                extractor.extract_from_akshare(code, stock_name, akshare_info)
            )
            graph_service.build_company_graph(base_graph)
            logger.info(f"[GraphTask] ✅ 基础图谱构建完成")
        else:
            logger.warning(f"[GraphTask] ⚠️ akshare 未返回数据")
        
        # 3. 从数据库新闻中提取信息更新图谱
        recent_news = db.execute(
            text("""
                SELECT title, content FROM news 
                WHERE stock_codes @> ARRAY[:code]::varchar[] 
                ORDER BY publish_time DESC LIMIT 50
            """).bindparams(code=pure_code)
        ).fetchall()
        
        if recent_news:
            news_data = [{"title": n[0], "content": n[1]} for n in recent_news]
            extractor = create_knowledge_extractor()
            
            extracted_info = asyncio.run(
                extractor.extract_from_news(code, stock_name, news_data)
            )
            
            if any(extracted_info.values()):
                graph_service.update_from_news(code, "", extracted_info)
                logger.info(f"[GraphTask] ✅ 从新闻更新图谱完成")
        
        logger.info(f"[GraphTask] ✅ 知识图谱构建完成: {stock_name}({code})")
        
        return {
            "status": "completed",
            "stock_code": code,
            "stock_name": stock_name,
            "news_count": len(recent_news) if recent_news else 0,
        }
        
    except Exception as e:
        logger.error(f"[GraphTask] ❌ 知识图谱构建失败: {e}", exc_info=True)
        return {"status": "failed", "error": str(e)}
    
    finally:
        db.close()

