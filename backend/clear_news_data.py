"""
清除所有新闻相关数据
"""
import os
import sys
from pathlib import Path

# 加载环境变量
from dotenv import load_dotenv
env_path = Path(__file__).parent / ".env"
load_dotenv(env_path)

# 构建数据库 URL
POSTGRES_USER = os.getenv("POSTGRES_USER", "postgres")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "postgres")
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")
POSTGRES_DB = os.getenv("POSTGRES_DB", "finnews_db")

DATABASE_URL = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"

from sqlalchemy import create_engine, text

def clear_all_news_data():
    """清除所有新闻相关数据"""
    print("🗑️  正在清除所有新闻数据...")
    
    engine = create_engine(DATABASE_URL)
    
    with engine.connect() as conn:
        # 查询存在的表
        result = conn.execute(text("""
            SELECT table_name FROM information_schema.tables 
            WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
        """))
        existing_tables = [row[0] for row in result.fetchall()]
        print(f"   数据库中的表: {existing_tables}")
        
        # 清除 news 表
        if 'news' in existing_tables:
            result = conn.execute(text("SELECT COUNT(*) FROM news"))
            news_count = result.scalar()
            print(f"   当前新闻数量: {news_count}")
            conn.execute(text("TRUNCATE TABLE news RESTART IDENTITY CASCADE"))
            print("   ✅ news 表已清除")
        else:
            print("   ⚠️ news 表不存在")
        
        # 清除 news_analysis 表（如果存在）
        if 'news_analysis' in existing_tables:
            result = conn.execute(text("SELECT COUNT(*) FROM news_analysis"))
            analysis_count = result.scalar()
            print(f"   当前分析数量: {analysis_count}")
            conn.execute(text("TRUNCATE TABLE news_analysis RESTART IDENTITY CASCADE"))
            print("   ✅ news_analysis 表已清除")
        
        # 清除 analysis 表（如果存在）
        if 'analysis' in existing_tables:
            result = conn.execute(text("SELECT COUNT(*) FROM analysis"))
            analysis_count = result.scalar()
            print(f"   当前 analysis 数量: {analysis_count}")
            conn.execute(text("TRUNCATE TABLE analysis RESTART IDENTITY CASCADE"))
            print("   ✅ analysis 表已清除")
        
        conn.commit()
        print("\n✅ 所有新闻数据已清除！")

if __name__ == "__main__":
    print("=" * 50)
    print("📰 FinnewsHunter - 清除新闻数据")
    print("=" * 50)
    
    # 确认操作
    if len(sys.argv) > 1 and sys.argv[1] == "--yes":
        confirm = "y"
    else:
        confirm = input("\n⚠️  确定要清除所有新闻数据吗？(y/N): ").strip().lower()
    
    if confirm == "y":
        clear_all_news_data()
        print("\n🎉 完成！")
    else:
        print("❌ 已取消操作")

