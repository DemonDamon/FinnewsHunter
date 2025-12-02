"""
数据库连接和依赖注入
"""
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.database import (
    AsyncSessionLocal,
    init_db as create_tables,
    Base,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI 依赖注入：获取数据库会话
    
    Usage:
        @app.get("/items")
        async def get_items(db: AsyncSession = Depends(get_db)):
            ...
    
    Yields:
        AsyncSession: 数据库会话
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


def init_database():
    """
    初始化数据库
    创建所有表结构
    """
    print("=" * 50)
    print("Initializing FinnewsHunter Database...")
    print("=" * 50)
    
    try:
        create_tables()
        print("\n✓ Database initialization completed successfully!")
    except Exception as e:
        print(f"\n✗ Database initialization failed: {e}")
        raise


if __name__ == "__main__":
    # 直接运行此文件以初始化数据库
    init_database()

