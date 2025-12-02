"""
Celery 爬取任务
"""
import logging
from datetime import datetime, timedelta
from typing import List
from sqlalchemy import select, create_engine
from sqlalchemy.orm import Session

from ..core.celery_app import celery_app
from ..core.config import settings
from ..models.crawl_task import CrawlTask, CrawlMode, TaskStatus
from ..models.news import News
from ..tools import SinaCrawlerTool

logger = logging.getLogger(__name__)


def get_sync_db_session():
    """获取同步数据库会话（Celery任务中使用）"""
    engine = create_engine(settings.SYNC_DATABASE_URL)
    return Session(engine)


@celery_app.task(bind=True, name="app.tasks.crawl_tasks.realtime_crawl_task")
def realtime_crawl_task(self, source: str = "sina"):
    """
    实时爬取任务（每5分钟执行一次）
    
    Args:
        source: 新闻源（sina, jrj等）
    """
    db = get_sync_db_session()
    task_record = None
    
    try:
        # 1. 创建任务记录
        task_record = CrawlTask(
            celery_task_id=self.request.id,
            mode=CrawlMode.REALTIME,
            status=TaskStatus.RUNNING,
            source=source,
            config={"page_limit": 1, "time_window": 3600},  # 只爬1页，1小时内的新闻
            started_at=datetime.utcnow(),
        )
        db.add(task_record)
        db.commit()
        db.refresh(task_record)
        
        logger.info(f"[Task {task_record.id}] 开始实时爬取: {source}")
        
        # 2. 创建爬虫
        if source == "sina":
            crawler = SinaCrawlerTool()
        else:
            raise ValueError(f"不支持的新闻源: {source}")
        
        # 3. 执行爬取（只爬第一页）
        start_time = datetime.utcnow()
        news_list = crawler.crawl(start_page=1, end_page=1)
        
        logger.info(f"[Task {task_record.id}] 爬取到 {len(news_list)} 条新闻")
        
        # 4. 时间过滤（只要最近1小时的）
        one_hour_ago = datetime.utcnow() - timedelta(hours=1)
        recent_news = [
            news for news in news_list
            if news.publish_time and news.publish_time > one_hour_ago
        ] if news_list else []
        
        logger.info(f"[Task {task_record.id}] 过滤后剩余 {len(recent_news)} 条新闻")
        
        # 5. 去重并保存
        saved_count = 0
        for news_item in recent_news:
            # 检查URL是否已存在
            existing = db.execute(
                select(News).where(News.url == news_item.url)
            ).scalar_one_or_none()
            
            if existing:
                logger.debug(f"[Task {task_record.id}] 新闻已存在: {news_item.url}")
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
                summary=news_item.summary,
            )
            
            db.add(news)
            saved_count += 1
        
        db.commit()
        
        # 6. 更新任务状态
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
            "duplicates": len(recent_news) - saved_count,
        }
        db.commit()
        
        logger.info(
            f"[Task {task_record.id}] 完成! "
            f"爬取: {len(news_list)}, 过滤: {len(recent_news)}, 保存: {saved_count}, "
            f"耗时: {execution_time:.2f}s"
        )
        
        return {
            "task_id": task_record.id,
            "status": "completed",
            "crawled": len(recent_news),
            "saved": saved_count,
            "execution_time": execution_time,
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
                            url=news_item.url,
                            source=news_item.source,
                            publish_time=news_item.publish_time,
                            author=news_item.author,
                            keywords=news_item.keywords,
                            stock_codes=news_item.stock_codes,
                            summary=news_item.summary,
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

