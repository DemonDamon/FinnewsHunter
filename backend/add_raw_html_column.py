"""
数据库迁移：添加 raw_html 字段
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# 加载环境变量
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

def add_raw_html_column():
    """添加 raw_html 字段到 news 表"""
    print("🔧 正在添加 raw_html 字段...")
    
    engine = create_engine(DATABASE_URL)
    
    with engine.connect() as conn:
        # 检查字段是否已存在
        result = conn.execute(text("""
            SELECT column_name FROM information_schema.columns 
            WHERE table_name = 'news' AND column_name = 'raw_html'
        """))
        
        if result.fetchone():
            print("✅ raw_html 字段已存在，无需迁移")
            return
        
        # 添加字段
        conn.execute(text("""
            ALTER TABLE news ADD COLUMN raw_html TEXT
        """))
        conn.commit()
        
        print("✅ raw_html 字段已添加成功！")

if __name__ == "__main__":
    print("=" * 50)
    print("📦 数据库迁移：添加 raw_html 字段")
    print("=" * 50)
    add_raw_html_column()

