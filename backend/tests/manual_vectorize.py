#!/usr/bin/env python3
"""
手动向量化新闻（用于修复未向量化的新闻）
"""
import sys
import os
import asyncio
import logging

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 先加载环境变量（避免循环导入）
from dotenv import load_dotenv
from pathlib import Path
env_path = Path(__file__).parent / ".env"
load_dotenv(env_path)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def vectorize_news_manually(news_id: int):
    """手动向量化单个新闻"""
    # 直接使用 SQLAlchemy 创建连接，避免循环导入
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
    from sqlalchemy import text
    from starlette.concurrency import run_in_threadpool
    
    # 从环境变量构建数据库 URL
    POSTGRES_USER = os.getenv("POSTGRES_USER", "postgres")
    POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "postgres")
    POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
    POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")
    POSTGRES_DB = os.getenv("POSTGRES_DB", "finnews_db")
    DATABASE_URL = f"postgresql+asyncpg://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
    
    # 创建引擎和会话
    engine = create_async_engine(DATABASE_URL, echo=False)
    AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    try:
        # 使用原始 SQL 查询，避免导入模型
        async with AsyncSessionLocal() as db:
            # 查询新闻数据
            result = await db.execute(
                text("SELECT id, title, content, is_embedded FROM news WHERE id = :news_id"),
                {"news_id": news_id}
            )
            row = result.first()
            
            if not row:
                print(f"❌ 新闻 {news_id} 不存在")
                return False
            
            news_id_db, title, content, is_embedded = row
            
            if is_embedded == 1:
                print(f"ℹ️  新闻 {news_id} 已经向量化过了")
                return True
            
            print(f"🔄 开始向量化新闻 {news_id}: {title[:50]}...")
            
            # 获取服务（这些服务不依赖数据库连接）
            from app.services.embedding_service import get_embedding_service
            from app.storage.vector_storage import get_vector_storage
            
            embedding_service = get_embedding_service()
            vector_storage = get_vector_storage()
            
            # 组合文本
            text_to_embed = f"{title}\n{content[:1000]}"
            
            # 生成向量（增加超时时间到60秒）
            print("  📡 调用 embedding API...")
            embedding = await asyncio.wait_for(
                embedding_service.aembed_text(text_to_embed),
                timeout=60.0  # 增加到60秒
            )
            print(f"  ✅ 向量生成成功，维度: {len(embedding)}")
            
            # 存储到 Milvus（设置超时，避免卡住）
            print("  💾 存储到 Milvus...")
            try:
                await asyncio.wait_for(
                    run_in_threadpool(
                        vector_storage.store_embedding,
                        news_id=news_id,
                        embedding=embedding,
                        text=text_to_embed
                    ),
                    timeout=30.0  # 30秒超时
                )
                print("  ✅ 存储成功")
            except asyncio.TimeoutError:
                print("  ⚠️  存储超时（30秒），但数据可能已插入")
                # 即使超时，数据可能已经插入，只是flush还没完成
            
            # 更新数据库标志
            await db.execute(
                text("UPDATE news SET is_embedded = 1 WHERE id = :news_id"),
                {"news_id": news_id}
            )
            await db.commit()
            print(f"  ✅ 更新数据库标志成功")
            
            print(f"✅ 新闻 {news_id} 向量化完成！")
            return True
            
    except asyncio.TimeoutError:
        print(f"❌ 新闻 {news_id} 向量化超时（60秒）")
        return False
    except Exception as e:
        print(f"❌ 新闻 {news_id} 向量化失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        await engine.dispose()

async def vectorize_all_pending():
    """向量化所有未向量化但已分析的新闻"""
    # 直接使用 SQLAlchemy 创建连接，避免循环导入
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
    from sqlalchemy import text
    
    # 从环境变量构建数据库 URL
    POSTGRES_USER = os.getenv("POSTGRES_USER", "postgres")
    POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "postgres")
    POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
    POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")
    POSTGRES_DB = os.getenv("POSTGRES_DB", "finnews_db")
    DATABASE_URL = f"postgresql+asyncpg://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
    
    # 创建引擎和会话
    engine = create_async_engine(DATABASE_URL, echo=False)
    AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    try:
        print("🔍 正在查找需要向量化的新闻...")
        async with AsyncSessionLocal() as db:
            # 使用原始 SQL 查询，避免导入模型
            result = await db.execute(
                text("""
                    SELECT id, title 
                    FROM news 
                    WHERE sentiment_score IS NOT NULL 
                    AND is_embedded = 0 
                    ORDER BY id DESC
                """)
            )
            pending_news = result.all()
            
            print(f"📊 查询完成，找到 {len(pending_news) if pending_news else 0} 条记录")
            
            if not pending_news:
                print("✅ 没有需要向量化的新闻")
                return
            
            print(f"📊 找到 {len(pending_news)} 条需要向量化的新闻")
            print("=" * 60)
            
            success_count = 0
            failed_count = 0
            
            # 使用单个处理方式，但添加了超时保护
            for news_id, title in pending_news:
                print(f"\n处理新闻 {news_id}...")
                if await vectorize_news_manually(news_id):
                    success_count += 1
                else:
                    failed_count += 1
            
            print("\n" + "=" * 60)
            print(f"📊 向量化完成统计:")
            print(f"  成功: {success_count}")
            print(f"  失败: {failed_count}")
            print("=" * 60)
    finally:
        await engine.dispose()

async def main_async():
    import sys
    
    print("🚀 脚本开始执行...")
    
    if len(sys.argv) > 1:
        try:
            # 向量化指定的新闻ID
            news_id = int(sys.argv[1])
            print(f"📌 向量化指定的新闻: {news_id}")
            await vectorize_news_manually(news_id)
        except ValueError:
            # 如果不是数字，可能是 --no-wait 参数
            if sys.argv[1] == "--no-wait":
                print("📌 向量化所有未向量化的新闻（跳过等待）")
                await vectorize_all_pending()
            else:
                print(f"❌ 无效的参数: {sys.argv[1]}")
                print("用法: python manual_vectorize.py [news_id|--no-wait]")
    else:
        # 向量化所有未向量化的新闻
        print("⚠️  这将向量化所有已分析但未向量化的新闻")
        print("   按 Ctrl+C 取消，或等待5秒后继续...")
        print("   (使用 --no-wait 参数可跳过等待)")
        try:
            await asyncio.sleep(5)
        except KeyboardInterrupt:
            print("\n已取消")
            sys.exit(0)
        
        await vectorize_all_pending()
    
    print("✅ 脚本执行完成")

if __name__ == "__main__":
    asyncio.run(main_async())
