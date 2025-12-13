"""
初始化股票数据脚本
从 akshare 获取全部 A 股信息并存入 PostgreSQL

使用方法:
    cd backend
    python -m app.scripts.init_stocks
"""
import asyncio
import logging
import os
from datetime import datetime
from pathlib import Path

# ⚠️ 禁用代理（akshare 需要直连国内网站）
for proxy_var in ['http_proxy', 'https_proxy', 'HTTP_PROXY', 'HTTPS_PROXY', 'all_proxy', 'ALL_PROXY']:
    os.environ.pop(proxy_var, None)

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 加载 .env
from dotenv import load_dotenv
env_path = Path(__file__).parent.parent.parent / ".env"
load_dotenv(env_path)
logger.info(f"Loaded .env from: {env_path}")

# 构建数据库 URL
DATABASE_URL = os.getenv("DATABASE_URL", "")

if not DATABASE_URL:
    # 从分开的变量构建 DATABASE_URL
    pg_user = os.getenv("POSTGRES_USER", "finnews")
    pg_password = os.getenv("POSTGRES_PASSWORD", "finnews_dev_password")
    pg_host = os.getenv("POSTGRES_HOST", "localhost")
    pg_port = os.getenv("POSTGRES_PORT", "5432")
    pg_db = os.getenv("POSTGRES_DB", "finnews_db")
    
    DATABASE_URL = f"postgresql+asyncpg://{pg_user}:{pg_password}@{pg_host}:{pg_port}/{pg_db}"
    logger.info(f"Built DATABASE_URL from individual variables")

elif DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

logger.info(f"Database: {DATABASE_URL.split('@')[-1] if '@' in DATABASE_URL else DATABASE_URL[:30]}...")

# 导入依赖
try:
    import akshare as ak
    import pandas as pd
    AKSHARE_AVAILABLE = True
    logger.info("akshare loaded successfully")
except ImportError:
    AKSHARE_AVAILABLE = False
    logger.error("akshare not installed! Run: pip install akshare")
    exit(1)

from sqlalchemy import Column, Integer, String, DateTime, Float, text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base

Base = declarative_base()


class Stock(Base):
    """股票基本信息表"""
    __tablename__ = "stocks"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    code = Column(String(20), unique=True, nullable=False, index=True)
    name = Column(String(100), nullable=False)
    full_code = Column(String(20), nullable=True)
    industry = Column(String(100), nullable=True)
    market = Column(String(20), nullable=True)
    area = Column(String(50), nullable=True)
    pe_ratio = Column(Float, nullable=True)
    market_cap = Column(Float, nullable=True)
    status = Column(String(20), default="active")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow)


def get_fallback_stocks() -> list:
    """备用股票列表（如果 akshare 失败时使用）"""
    return [
        {"code": "600519", "name": "贵州茅台", "full_code": "SH600519", "market": "SH", "status": "active"},
        {"code": "000001", "name": "平安银行", "full_code": "SZ000001", "market": "SZ", "status": "active"},
        {"code": "601318", "name": "中国平安", "full_code": "SH601318", "market": "SH", "status": "active"},
        {"code": "000858", "name": "五粮液", "full_code": "SZ000858", "market": "SZ", "status": "active"},
        {"code": "002594", "name": "比亚迪", "full_code": "SZ002594", "market": "SZ", "status": "active"},
        {"code": "600036", "name": "招商银行", "full_code": "SH600036", "market": "SH", "status": "active"},
        {"code": "601166", "name": "兴业银行", "full_code": "SH601166", "market": "SH", "status": "active"},
        {"code": "000333", "name": "美的集团", "full_code": "SZ000333", "market": "SZ", "status": "active"},
        {"code": "002415", "name": "海康威视", "full_code": "SZ002415", "market": "SZ", "status": "active"},
        {"code": "600276", "name": "恒瑞医药", "full_code": "SH600276", "market": "SH", "status": "active"},
        {"code": "000002", "name": "万科A", "full_code": "SZ000002", "market": "SZ", "status": "active"},
        {"code": "600887", "name": "伊利股份", "full_code": "SH600887", "market": "SH", "status": "active"},
        {"code": "000725", "name": "京东方A", "full_code": "SZ000725", "market": "SZ", "status": "active"},
        {"code": "600000", "name": "浦发银行", "full_code": "SH600000", "market": "SH", "status": "active"},
        {"code": "000063", "name": "中兴通讯", "full_code": "SZ000063", "market": "SZ", "status": "active"},
        {"code": "600104", "name": "上汽集团", "full_code": "SH600104", "market": "SH", "status": "active"},
        {"code": "002304", "name": "洋河股份", "full_code": "SZ002304", "market": "SZ", "status": "active"},
        {"code": "600585", "name": "海螺水泥", "full_code": "SH600585", "market": "SH", "status": "active"},
        {"code": "000876", "name": "新希望", "full_code": "SZ000876", "market": "SZ", "status": "active"},
        {"code": "600309", "name": "万华化学", "full_code": "SH600309", "market": "SH", "status": "active"},
    ]


async def fetch_all_stocks() -> list:
    """从 akshare 获取全部 A 股信息"""
    logger.info("Fetching all A-share stocks from akshare...")
    
    # 设置 requests 不使用代理
    import requests
    session = requests.Session()
    session.proxies = {
        'http': None,
        'https': None,
    }
    
    # 设置 User-Agent
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    })
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            logger.info(f"Attempt {attempt + 1}/{max_retries}...")
            
            # 方法1: 尝试使用 stock_zh_a_spot_em
            try:
                df = ak.stock_zh_a_spot_em()
            except Exception as e1:
                logger.warning(f"Method 1 failed: {e1}")
                # 方法2: 尝试使用 stock_info_a_code_name
                try:
                    logger.info("Trying alternative method: stock_info_a_code_name...")
                    df = ak.stock_info_a_code_name()
                    if df is not None and not df.empty:
                        # 重命名列
                        df.columns = ['代码', '名称']
                except Exception as e2:
                    logger.warning(f"Method 2 failed: {e2}")
                    raise e1  # 抛出第一个错误
            
            if df is None or df.empty:
                logger.error("No data returned from akshare")
                if attempt < max_retries - 1:
                    await asyncio.sleep(2)  # 等待2秒后重试
                    continue
                return []
            
            logger.info(f"✅ Fetched {len(df)} stocks from akshare")
            
            stocks = []
            for _, row in df.iterrows():
                code = str(row['代码'])
                name = str(row['名称'])
                
                # 跳过异常数据
                if not code or not name or name in ['N/A', 'nan', '']:
                    continue
                
                # 确定市场前缀
                if code.startswith('6'):
                    market = "SH"
                    full_code = f"SH{code}"
                elif code.startswith('0') or code.startswith('3'):
                    market = "SZ"
                    full_code = f"SZ{code}"
                else:
                    market = "OTHER"
                    full_code = code
                
                stocks.append({
                    "code": code,
                    "name": name,
                    "full_code": full_code,
                    "market": market,
                    "status": "active",
                })
            
            return stocks
            
        except Exception as e:
            logger.error(f"Attempt {attempt + 1} failed: {e}")
            if attempt < max_retries - 1:
                wait_time = (attempt + 1) * 2
                logger.info(f"Waiting {wait_time} seconds before retry...")
                await asyncio.sleep(wait_time)
            else:
                logger.error("All attempts failed!")
                import traceback
                traceback.print_exc()
                return []
    
    return []


async def init_stocks_to_db():
    """初始化股票数据到数据库"""
    # 创建数据库引擎
    engine = create_async_engine(DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    # 确保表存在
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    # 获取股票数据
    stocks_data = await fetch_all_stocks()
    
    if not stocks_data:
        logger.warning("⚠️  Failed to fetch from akshare, using fallback stock list...")
        # 备用方案：导入常用股票
        stocks_data = get_fallback_stocks()
        if not stocks_data:
            logger.error("No stocks to insert")
            await engine.dispose()
            return
        logger.info(f"Using {len(stocks_data)} fallback stocks")
    
    async with async_session() as session:
        try:
            # 清空现有数据
            logger.info("Clearing existing stock data...")
            await session.execute(text("DELETE FROM stocks"))
            await session.commit()
            
            # 批量插入
            logger.info(f"Inserting {len(stocks_data)} stocks...")
            
            batch_size = 500
            for i in range(0, len(stocks_data), batch_size):
                batch = stocks_data[i:i + batch_size]
                for stock_data in batch:
                    stock = Stock(
                        code=stock_data["code"],
                        name=stock_data["name"],
                        full_code=stock_data["full_code"],
                        market=stock_data["market"],
                        status=stock_data["status"],
                        created_at=datetime.utcnow(),
                        updated_at=datetime.utcnow(),
                    )
                    session.add(stock)
                
                await session.commit()
                logger.info(f"Inserted batch {i // batch_size + 1}, total: {min(i + batch_size, len(stocks_data))}/{len(stocks_data)}")
            
            logger.info(f"✅ Successfully initialized {len(stocks_data)} stocks!")
            
        except Exception as e:
            logger.error(f"Failed to insert stocks: {e}")
            import traceback
            traceback.print_exc()
            await session.rollback()
        finally:
            await engine.dispose()


async def get_stock_count():
    """获取数据库中股票数量"""
    engine = create_async_engine(DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as session:
        result = await session.execute(text("SELECT COUNT(*) FROM stocks"))
        count = result.scalar() or 0
        logger.info(f"Current stock count in database: {count}")
        await engine.dispose()
        return count


async def main():
    print("=" * 60)
    print("🚀 Stock Data Initialization Script")
    print("=" * 60)
    
    # 检查当前数量
    try:
        await get_stock_count()
    except Exception as e:
        logger.warning(f"Could not get current count (table may not exist): {e}")
    
    # 执行初始化
    print("\n📥 Starting initialization...")
    await init_stocks_to_db()
    
    # 再次检查
    print("\n📊 After initialization:")
    await get_stock_count()
    
    print("\n✅ Done!")


if __name__ == "__main__":
    asyncio.run(main())
