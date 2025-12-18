"""
Celery 爬取任务 - Phase 2: 实时监控升级版 + 多源支持
"""
import logging
import json
from datetime import datetime, timedelta
from typing import List, Dict, Any
from sqlalchemy import select, create_engine
from sqlalchemy.orm import Session

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
    days: int = 30
):
    """
    定向爬取某只股票的相关新闻
    
    数据来源：
    1. BochaAI 搜索引擎 API
    2. 东方财富等财经网站（可扩展）
    
    Args:
        stock_code: 股票代码（如 SH600519）
        stock_name: 股票名称（如 贵州茅台）
        days: 搜索时间范围（天），默认30天
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
        
        # 1. 创建任务记录
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
        filtered_news = []
        
        # 2. 使用 BochaAI 搜索引擎搜索新闻
        if bochaai_search.is_available():
            logger.info(f"[Task {task_record.id}] 🔍 使用 BochaAI 搜索...")
            
            search_results = bochaai_search.search_stock_news(
                stock_name=stock_name,
                stock_code=pure_code,
                days=days,
                count=100,  # 获取100条新闻
                max_age_days=90  # 只获取最近3个月的新闻
            )
            
            logger.info(f"[Task {task_record.id}] 📰 BochaAI 搜索到 {len(search_results)} 条结果")
            
            # 创建增强爬虫实例，用于二次爬取完整内容
            enhanced_crawler = EnhancedCrawler(use_cache=True)
            
            # 转换搜索结果为 NewsItem，并二次爬取完整内容
            for idx, result in enumerate(search_results):
                # 解析发布时间
                publish_time = None
                if result.date_published:
                    try:
                        # 尝试解析 ISO 格式
                        publish_time = datetime.fromisoformat(
                            result.date_published.replace('Z', '+00:00')
                        )
                    except (ValueError, AttributeError):
                        pass
                
                # 二次爬取完整内容
                full_content = result.snippet  # 默认使用摘要
                raw_html = None  # 原始 HTML
                try:
                    logger.info(f"[Task {task_record.id}] 🔗 [{idx+1}/{len(search_results)}] 爬取完整内容: {result.url[:60]}...")
                    article = enhanced_crawler.crawl(result.url, engine='auto')
                    if article and article.content and len(article.content) > len(result.snippet):
                        full_content = article.content
                        raw_html = article.html_content  # 保存原始 HTML
                        logger.info(f"[Task {task_record.id}] ✅ 获取完整内容: {len(full_content)} 字符, HTML: {len(raw_html) if raw_html else 0} 字符")
                    else:
                        logger.warning(f"[Task {task_record.id}] ⚠️ 完整内容获取失败或内容更短，使用摘要")
                except Exception as e:
                    logger.warning(f"[Task {task_record.id}] ⚠️ 二次爬取失败: {e}, 使用摘要")
                
                news_item = NewsItem(
                    title=result.title,
                    content=full_content,  # 使用完整内容
                    url=result.url,
                    source=result.site_name or "web_search",
                    publish_time=publish_time,
                    stock_codes=[pure_code, code],  # 关联股票代码
                    raw_html=raw_html,  # 原始 HTML
                )
                all_news.append(news_item)
        else:
            logger.warning(f"[Task {task_record.id}] ⚠️ BochaAI API Key 未配置，跳过搜索引擎搜索")
        
        # 3. 使用多个爬虫作为补充来源
        # 定义要使用的爬虫列表（爬虫名称, 爬取页数, 图标）
        crawler_configs = [
            ("eastmoney", 3, "💎"),  # 东方财富
            ("sina", 2, "🌐"),       # 新浪财经
            ("tencent", 2, "🐧"),    # 腾讯财经
            ("163", 2, "📧"),        # 网易财经
            ("nbd", 2, "📰"),        # 每日经济新闻
            ("yicai", 2, "🎯"),      # 第一财经
            ("caijing", 2, "📈"),    # 财经网
            ("jingji21", 2, "📉"),   # 21经济网
            ("eeo", 2, "📊"),        # 经济观察网
            ("jwview", 2, "💰"),     # 金融界
        ]
        
        total_crawlers = len(crawler_configs)
        for idx, (crawler_name, pages, icon) in enumerate(crawler_configs):
            try:
                logger.info(f"[Task {task_record.id}] {icon} [{idx+1}/{total_crawlers}] 使用 {crawler_name} 爬虫...")
                
                # 更新进度
                task_record.progress = {
                    "current": idx + 1,
                    "total": total_crawlers,
                    "message": f"正在爬取 {crawler_name}..."
                }
                db.commit()
                
                crawler = get_crawler_tool(crawler_name)
                crawler_news = crawler.crawl(start_page=1, end_page=pages)
                
                # 过滤包含股票名称或代码的新闻
                matched_count = 0
                for news in crawler_news:
                    # 检查标题或内容是否包含股票名称或代码
                    title_match = (stock_name in news.title or pure_code in news.title)
                    content_match = (stock_name in (news.content or '') or pure_code in (news.content or ''))
                    
                    if title_match or content_match:
                        # 添加股票代码关联
                        if not news.stock_codes:
                            news.stock_codes = []
                        if pure_code not in news.stock_codes:
                            news.stock_codes.append(pure_code)
                        if code not in news.stock_codes:
                            news.stock_codes.append(code)
                        filtered_news.append(news)
                        matched_count += 1
                
                logger.info(f"[Task {task_record.id}] {icon} {crawler_name} 爬取 {len(crawler_news)} 条，匹配 {matched_count} 条")
                
            except Exception as e:
                logger.warning(f"[Task {task_record.id}] ⚠️ {crawler_name} 爬取失败: {e}")
                continue
        
        # 合并所有爬虫获取的新闻
        all_news.extend(filtered_news)
        logger.info(f"[Task {task_record.id}] 📰 多爬虫共过滤出 {len(filtered_news)} 条相关新闻")
        
        # 4. 去重并保存
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
        
        # 5. 更新任务状态
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
            "sources": {
                "bochaai": len(search_results),
                "eastmoney": len(filtered_news),
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

