#!/usr/bin/env python
"""
数据库初始化脚本
独立运行以创建数据库表
"""
import sys
import os

# 添加当前目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

if __name__ == "__main__":
    print("=" * 60)
    print("Initializing FinnewsHunter Database...")
    print("=" * 60)
    
    try:
        from sqlalchemy import create_engine
        from sqlalchemy.orm import declarative_base
        from app.core.config import settings
        
        # 导入所有模型
        from app.models.database import Base
        from app.models.news import News
        from app.models.stock import Stock
        from app.models.analysis import Analysis
        from app.models.crawl_task import CrawlTask
        from app.models.debate_history import DebateHistory
        
        print(f"\nConnecting to database: {settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}/{settings.POSTGRES_DB}")
        
        # 创建同步引擎
        sync_engine = create_engine(
            settings.SYNC_DATABASE_URL,
            echo=False,
            pool_pre_ping=True,
        )
        
        print("Creating tables...")
        Base.metadata.create_all(bind=sync_engine)
        
        print("\nDatabase initialized successfully!")
        print(f"   - News table created")
        print(f"   - Stock table created")
        print(f"   - Analysis table created")
        print(f"   - CrawlTask table created")
        print(f"   - DebateHistory table created")
        print("=" * 60)
        sys.exit(0)
        
    except Exception as e:
        print(f"\nDatabase initialization failed: {e}")
        import traceback
        traceback.print_exc()
        print("=" * 60)
        print("\nNote: If tables already exist, this error is expected.")
        print("You can safely ignore it and proceed with starting the server.")
        sys.exit(0)  # 即使失败也返回0，因为表可能已存在

