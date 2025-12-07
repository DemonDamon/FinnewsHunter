"""
清空数据库并重新开始
用于重置系统数据
"""
import asyncio
import sys
from sqlalchemy import text
from app.core.database import get_async_engine
from app.core.redis_client import redis_client
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def reset_database():
    """清空所有数据"""
    engine = get_async_engine()
    
    try:
        async with engine.begin() as conn:
            logger.info("=" * 60)
            logger.info("开始清空数据库...")
            logger.info("=" * 60)
            
            # 1. 清空新闻表
            logger.info("清空新闻表 (news)...")
            result = await conn.execute(text("DELETE FROM news"))
            logger.info(f"✅ 已删除 {result.rowcount} 条新闻记录")
            
            # 2. 清空爬取任务表
            logger.info("清空爬取任务表 (crawl_tasks)...")
            result = await conn.execute(text("DELETE FROM crawl_tasks"))
            logger.info(f"✅ 已删除 {result.rowcount} 条任务记录")
            
            # 3. 清空分析表（如果存在）
            try:
                logger.info("清空分析表 (analyses)...")
                result = await conn.execute(text("DELETE FROM analyses"))
                logger.info(f"✅ 已删除 {result.rowcount} 条分析记录")
            except Exception as e:
                logger.warning(f"清空分析表失败（表可能不存在）: {e}")
            
            # 4. 重置自增ID
            logger.info("重置表自增ID...")
            try:
                await conn.execute(text("ALTER SEQUENCE news_id_seq RESTART WITH 1"))
                await conn.execute(text("ALTER SEQUENCE crawl_tasks_id_seq RESTART WITH 1"))
                await conn.execute(text("ALTER SEQUENCE analyses_id_seq RESTART WITH 1"))
                logger.info("✅ 自增ID已重置")
            except Exception as e:
                logger.warning(f"重置自增ID失败: {e}")
            
            logger.info("=" * 60)
            logger.info("数据库清空完成！")
            logger.info("=" * 60)
        
        # 5. 清空Redis缓存
        if redis_client.is_available():
            logger.info("清空Redis缓存...")
            try:
                # 删除所有news相关的缓存键
                redis_client.client.flushdb()
                logger.info("✅ Redis缓存已清空")
            except Exception as e:
                logger.error(f"清空Redis失败: {e}")
        else:
            logger.warning("⚠️  Redis不可用，跳过缓存清理")
        
        logger.info("=" * 60)
        logger.info("✨ 数据重置完成！")
        logger.info("=" * 60)
        logger.info("下一步：")
        logger.info("1. 重启 Celery Worker 和 Beat")
        logger.info("2. 系统将自动开始爬取最新新闻")
        logger.info("3. 约5-10分钟后可在前端查看新数据")
        logger.info("=" * 60)
        
    except Exception as e:
        logger.error(f"❌ 清空数据失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    # 确认操作
    print("⚠️  警告：此操作将删除所有新闻和任务数据！")
    print("⚠️  此操作不可恢复！")
    confirm = input("确认要清空所有数据吗？(yes/no): ")
    
    if confirm.lower() in ['yes', 'y']:
        asyncio.run(reset_database())
    else:
        print("❌ 操作已取消")
        sys.exit(0)

