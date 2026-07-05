"""
股票数据服务 - 使用 akshare 获取真实股票数据
"""
import logging
import os
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any, Iterator
from functools import lru_cache
import asyncio

logger = logging.getLogger(__name__)

PROXY_ENV_VARS = (
    "http_proxy",
    "https_proxy",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "all_proxy",
    "ALL_PROXY",
)

FALLBACK_A_SHARE_STOCKS: List[Dict[str, str]] = [
    {"code": "600519", "name": "贵州茅台", "full_code": "SH600519", "market": "SH"},
    {"code": "000001", "name": "平安银行", "full_code": "SZ000001", "market": "SZ"},
    {"code": "601318", "name": "中国平安", "full_code": "SH601318", "market": "SH"},
    {"code": "000858", "name": "五粮液", "full_code": "SZ000858", "market": "SZ"},
    {"code": "002594", "name": "比亚迪", "full_code": "SZ002594", "market": "SZ"},
    {"code": "600036", "name": "招商银行", "full_code": "SH600036", "market": "SH"},
    {"code": "601166", "name": "兴业银行", "full_code": "SH601166", "market": "SH"},
    {"code": "000333", "name": "美的集团", "full_code": "SZ000333", "market": "SZ"},
    {"code": "002415", "name": "海康威视", "full_code": "SZ002415", "market": "SZ"},
    {"code": "600276", "name": "恒瑞医药", "full_code": "SH600276", "market": "SH"},
    {"code": "000002", "name": "万科A", "full_code": "SZ000002", "market": "SZ"},
    {"code": "600887", "name": "伊利股份", "full_code": "SH600887", "market": "SH"},
    {"code": "000725", "name": "京东方A", "full_code": "SZ000725", "market": "SZ"},
    {"code": "600000", "name": "浦发银行", "full_code": "SH600000", "market": "SH"},
    {"code": "000063", "name": "中兴通讯", "full_code": "SZ000063", "market": "SZ"},
    {"code": "600104", "name": "上汽集团", "full_code": "SH600104", "market": "SH"},
    {"code": "002304", "name": "洋河股份", "full_code": "SZ002304", "market": "SZ"},
    {"code": "600585", "name": "海螺水泥", "full_code": "SH600585", "market": "SH"},
    {"code": "000876", "name": "新希望", "full_code": "SZ000876", "market": "SZ"},
    {"code": "600309", "name": "万华化学", "full_code": "SH600309", "market": "SH"},
]


# 尝试导入 akshare
try:
    import akshare as ak
    import pandas as pd
    AKSHARE_AVAILABLE = True
except ImportError:
    ak = None  # type: ignore[assignment]
    pd = None  # type: ignore[assignment]
    AKSHARE_AVAILABLE = False
    logger.warning("akshare not installed, using mock data")


@contextmanager
def akshare_direct_connection() -> Iterator[None]:
    """akshare 访问国内数据源时需绕过 shell 代理，否则易 ProxyError。"""
    saved = {key: os.environ.pop(key, None) for key in PROXY_ENV_VARS}
    try:
        yield
    finally:
        for key, value in saved.items():
            if value is not None:
                os.environ[key] = value


def _normalize_stock_row(code: str, name: str) -> Optional[Dict[str, str]]:
    if not code or not name or name in {"N/A", "nan", ""}:
        return None
    if code.startswith("6"):
        market, full_code = "SH", f"SH{code}"
    elif code.startswith(("0", "3")):
        market, full_code = "SZ", f"SZ{code}"
    else:
        market, full_code = "OTHER", code
    return {"code": code, "name": name, "full_code": full_code, "market": market}


def fetch_all_a_share_stocks(use_fallback: bool = True) -> List[Dict[str, str]]:
    """从 akshare 拉取 A 股列表；失败时可回落到常用股票。"""
    if not AKSHARE_AVAILABLE:
        raise ImportError("akshare not installed")

    last_error: Optional[Exception] = None
    with akshare_direct_connection():
        for attempt in range(3):
            try:
                try:
                    df = ak.stock_zh_a_spot_em()
                except Exception as primary_error:
                    logger.warning("stock_zh_a_spot_em failed: %s", primary_error)
                    df = ak.stock_info_a_code_name()
                    if df is not None and not df.empty:
                        df = df.rename(columns={df.columns[0]: "代码", df.columns[1]: "名称"})

                if df is None or df.empty:
                    raise RuntimeError("akshare returned empty stock list")

                stocks: List[Dict[str, str]] = []
                for _, row in df.iterrows():
                    normalized = _normalize_stock_row(str(row["代码"]), str(row["名称"]))
                    if normalized:
                        stocks.append(normalized)
                if stocks:
                    logger.info("Fetched %s stocks from akshare", len(stocks))
                    return stocks
                raise RuntimeError("akshare returned no valid stock rows")
            except Exception as exc:
                last_error = exc
                logger.warning("Fetch A-share stocks attempt %s/3 failed: %s", attempt + 1, exc)

    if use_fallback:
        logger.warning("Using fallback stock list (%s items)", len(FALLBACK_A_SHARE_STOCKS))
        return list(FALLBACK_A_SHARE_STOCKS)

    raise RuntimeError(str(last_error) if last_error else "Failed to fetch stocks from akshare")


class StockDataService:
    """股票数据服务 - 封装 akshare 接口"""
    
    # 缓存过期时间（秒）
    CACHE_TTL = 300  # 5分钟
    CACHE_TTL_MINUTE = 60  # 分钟级数据缓存1分钟
    
    # 股票代码前缀映射
    MARKET_PREFIX = {
        "sh": "6",     # 上海 60xxxx
        "sz": "0",     # 深圳 00xxxx, 30xxxx
        "sz3": "3",    # 创业板 30xxxx
    }
    
    # 周期映射
    PERIOD_MAP = {
        "1m": "1",      # 1分钟
        "5m": "5",      # 5分钟
        "15m": "15",    # 15分钟
        "30m": "30",    # 30分钟
        "60m": "60",    # 60分钟/1小时
        "1h": "60",     # 1小时（别名）
        "daily": "daily",  # 日线
        "1d": "daily",     # 日线（别名）
    }
    
    def __init__(self):
        self._cache: Dict[str, tuple] = {}  # {key: (data, timestamp)}
    
    def _normalize_code(self, stock_code: str) -> str:
        """
        标准化股票代码，返回纯数字代码
        支持格式: SH600519, sh600519, 600519
        """
        code = stock_code.upper().strip()
        if code.startswith("SH") or code.startswith("SZ"):
            return code[2:]
        return code
    
    def _get_symbol(self, stock_code: str) -> str:
        """
        获取 akshare 使用的股票代码格式
        akshare stock_zh_a_hist 需要纯数字代码
        """
        return self._normalize_code(stock_code)
    
    def _is_cache_valid(self, key: str, ttl: int = None) -> bool:
        """检查缓存是否有效"""
        if key not in self._cache:
            return False
        _, timestamp = self._cache[key]
        cache_ttl = ttl if ttl is not None else self.CACHE_TTL
        # 修复bug: 使用 total_seconds() 而不是 seconds
        # seconds 只返回秒数部分(0-86399)，不包括天数
        return (datetime.now() - timestamp).total_seconds() < cache_ttl
    
    def _get_cached(self, key: str, ttl: int = None) -> Optional[Any]:
        """获取缓存数据"""
        if self._is_cache_valid(key, ttl):
            return self._cache[key][0]
        # 清理过期缓存
        if key in self._cache:
            del self._cache[key]
        return None
    
    def _set_cache(self, key: str, data: Any):
        """设置缓存"""
        self._cache[key] = (data, datetime.now())
    
    def clear_cache(self, pattern: str = None):
        """
        清除缓存
        Args:
            pattern: 可选的缓存键模式，如果提供则只清除匹配的缓存
        """
        if pattern:
            keys_to_delete = [k for k in self._cache.keys() if pattern in k]
            for key in keys_to_delete:
                del self._cache[key]
            logger.info(f"🧹 Cleared {len(keys_to_delete)} cache entries matching pattern: {pattern}")
        else:
            count = len(self._cache)
            self._cache.clear()
            logger.info(f"🧹 Cleared all {count} cache entries")
    
    async def get_kline_data(
        self,
        stock_code: str,
        period: str = "daily",  # daily, 1m, 5m, 15m, 30m, 60m
        limit: int = 90,  # 数据条数
        adjust: str = "qfq"  # qfq=前复权, hfq=后复权, ""=不复权
    ) -> List[Dict[str, Any]]:
        """
        获取K线数据（支持日线和分钟级数据）
        
        Args:
            stock_code: 股票代码
            period: 周期 (daily, 1m, 5m, 15m, 30m, 60m)
            limit: 返回数据条数
            adjust: 复权类型（仅日线有效）
            
        Returns:
            K线数据列表，每条包含: timestamp, open, high, low, close, volume, turnover
        """
        # 标准化周期
        period_key = self.PERIOD_MAP.get(period, period)
        cache_key = f"kline:{stock_code}:{period}:{limit}:{adjust}"
        
        # 根据周期使用不同的缓存TTL：日线5分钟，分钟级1分钟
        cache_ttl = self.CACHE_TTL if period_key == "daily" else self.CACHE_TTL_MINUTE
        cached = self._get_cached(cache_key, ttl=cache_ttl)
        if cached:
            latest_date = cached[-1].get('date', 'unknown') if cached else 'empty'
            logger.info(f"🔵 Cache hit for {cache_key}, latest date: {latest_date}, count: {len(cached)}")
            return cached
        
        logger.info(f"🔴 Cache miss for {cache_key}, fetching fresh data...")
        
        if not AKSHARE_AVAILABLE:
            logger.warning("akshare not available, returning mock data")
            return self._generate_mock_kline(stock_code, limit)
        
        try:
            symbol = self._get_symbol(stock_code)
            loop = asyncio.get_event_loop()
            
            if period_key == "daily":
                # 日线数据
                kline_data = await self._fetch_daily_kline(symbol, limit, adjust, loop)
            else:
                # 分钟级数据
                kline_data = await self._fetch_minute_kline(symbol, period_key, limit, loop)
            
            if not kline_data:
                logger.warning(f"⚠️ No valid data after parsing for {stock_code} period={period}, using mock data")
                return self._generate_mock_kline(stock_code, limit)
            
            # 记录最新数据的日期和价格，便于调试
            latest = kline_data[-1]
            logger.info(f"✅ Successfully fetched {len(kline_data)} kline records for {stock_code} period={period}, latest: {latest['date']}, close: {latest['close']}")
            
            self._set_cache(cache_key, kline_data)
            return kline_data
            
        except Exception as e:
            logger.error(f"❌ Failed to fetch kline data for {stock_code}: {type(e).__name__}: {e}", exc_info=True)
            # 只在某些特定错误时返回mock数据，其他错误应该抛出
            if "NaTType" in str(e) or "timestamp" in str(e).lower():
                logger.warning(f"Data parsing error, this should not happen after fix. Returning empty list.")
                return []
            # 网络错误或API错误才返回mock数据
            return self._generate_mock_kline(stock_code, limit)
    
    async def _fetch_daily_kline(
        self, 
        symbol: str, 
        limit: int, 
        adjust: str,
        loop
    ) -> List[Dict[str, Any]]:
        """获取日线数据"""
        end_date = datetime.now()
        # 多获取一些天数，确保有足够数据（考虑周末和节假日，约1个交易日=1.5个自然日）
        # limit * 1.6 能确保获取到足够的交易日数据
        start_date = end_date - timedelta(days=int(limit * 1.6))
        
        logger.info(f"📊 Calling akshare API: symbol={symbol}, start={start_date.strftime('%Y%m%d')}, end={end_date.strftime('%Y%m%d')}, adjust={adjust}")
        
        df = await loop.run_in_executor(
            None,
            lambda: ak.stock_zh_a_hist(
                symbol=symbol,
                start_date=start_date.strftime("%Y%m%d"),
                end_date=end_date.strftime("%Y%m%d"),
                adjust=adjust
            )
        )
        
        logger.info(f"✅ Akshare returned {len(df) if df is not None and not df.empty else 0} rows")
        
        if df is None or df.empty:
            return []
        
        # 清理数据：移除日期为NaT的行
        df = df.dropna(subset=['日期'])
        
        # 只取最近 limit 条数据
        df = df.tail(limit)
        
        # 转换为标准格式
        kline_data = []
        for _, row in df.iterrows():
            try:
                # 处理日期
                date_val = row['日期']
                if pd.isna(date_val):
                    logger.warning(f"Skipping row with NaT date")
                    continue
                    
                if isinstance(date_val, str):
                    dt = datetime.strptime(date_val, "%Y-%m-%d")
                    date_str = date_val
                else:
                    dt = pd.to_datetime(date_val)
                    if pd.isna(dt):
                        logger.warning(f"Skipping row with invalid date")
                        continue
                    date_str = dt.strftime("%Y-%m-%d")
                
                timestamp = int(dt.timestamp() * 1000)
                
                kline_data.append({
                    "timestamp": timestamp,
                    "date": date_str,
                    "open": float(row['开盘']),
                    "high": float(row['最高']),
                    "low": float(row['最低']),
                    "close": float(row['收盘']),
                    "volume": int(row['成交量']),
                    "turnover": float(row.get('成交额', 0)),
                    "change_percent": float(row.get('涨跌幅', 0)),
                    "change_amount": float(row.get('涨跌额', 0)),
                    "amplitude": float(row.get('振幅', 0)),
                    "turnover_rate": float(row.get('换手率', 0)),
                })
            except Exception as e:
                logger.warning(f"Failed to parse row, skipping: {e}")
                continue
        
        # 记录数据范围
        if kline_data:
            logger.info(f"✅ Parsed {len(kline_data)} valid records, date range: {kline_data[0]['date']} to {kline_data[-1]['date']}")
        
        return kline_data
    
    async def _fetch_minute_kline(
        self, 
        symbol: str, 
        period: str,  # "1", "5", "15", "30", "60"
        limit: int,
        loop
    ) -> List[Dict[str, Any]]:
        """获取分钟级数据"""
        df = await loop.run_in_executor(
            None,
            lambda: ak.stock_zh_a_hist_min_em(
                symbol=symbol,
                period=period,
                adjust=""
            )
        )
        
        if df is None or df.empty:
            return []
        
        # 清理数据：移除时间为NaT的行
        df = df.dropna(subset=['时间'])
        
        # 只取最近 limit 条数据
        df = df.tail(limit)
        
        # 转换为标准格式
        kline_data = []
        for _, row in df.iterrows():
            try:
                # 处理时间
                time_val = row['时间']
                if pd.isna(time_val):
                    logger.warning(f"Skipping row with NaT time")
                    continue
                
                time_str = str(time_val)
                try:
                    dt = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
                except:
                    dt = pd.to_datetime(time_val)
                    if pd.isna(dt):
                        logger.warning(f"Skipping row with invalid time")
                        continue
                    time_str = dt.strftime("%Y-%m-%d %H:%M:%S")
                
                timestamp = int(dt.timestamp() * 1000)
                
                kline_data.append({
                    "timestamp": timestamp,
                    "date": time_str,
                    "open": float(row['开盘']),
                    "high": float(row['最高']),
                    "low": float(row['最低']),
                    "close": float(row['收盘']),
                    "volume": int(row['成交量']),
                    "turnover": float(row.get('成交额', 0)),
                    "change_percent": 0,  # 分钟数据可能没有涨跌幅
                    "change_amount": 0,
                    "amplitude": 0,
                    "turnover_rate": 0,
                })
            except Exception as e:
                logger.warning(f"Failed to parse minute row, skipping: {e}")
                continue
        
        # 记录数据范围
        if kline_data:
            logger.info(f"✅ Parsed {len(kline_data)} valid minute records, time range: {kline_data[0]['date']} to {kline_data[-1]['date']}")
        
        return kline_data
    
    async def get_realtime_quote(self, stock_code: str) -> Optional[Dict[str, Any]]:
        """
        获取实时行情
        
        Returns:
            实时行情数据
        """
        cache_key = f"realtime:{stock_code}"
        cached = self._get_cached(cache_key)
        if cached:
            return cached
        
        if not AKSHARE_AVAILABLE:
            return None
        
        try:
            symbol = self._get_symbol(stock_code)
            
            loop = asyncio.get_event_loop()
            df = await loop.run_in_executor(
                None,
                lambda: ak.stock_zh_a_spot_em()
            )
            
            if df is None or df.empty:
                return None
            
            # 根据股票代码筛选
            row = df[df['代码'] == symbol]
            if row.empty:
                return None
            
            row = row.iloc[0]
            quote = {
                "code": symbol,
                "name": row.get('名称', ''),
                "price": float(row.get('最新价', 0)),
                "change_percent": float(row.get('涨跌幅', 0)),
                "change_amount": float(row.get('涨跌额', 0)),
                "volume": int(row.get('成交量', 0)),
                "turnover": float(row.get('成交额', 0)),
                "high": float(row.get('最高', 0)),
                "low": float(row.get('最低', 0)),
                "open": float(row.get('今开', 0)),
                "prev_close": float(row.get('昨收', 0)),
            }
            
            self._set_cache(cache_key, quote)
            return quote
            
        except Exception as e:
            logger.error(f"Failed to fetch realtime quote for {stock_code}: {e}")
            return None
    
    async def search_stocks(
        self,
        keyword: str,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        搜索股票（通过代码或名称模糊匹配）
        
        Args:
            keyword: 搜索关键词
            limit: 返回数量限制
            
        Returns:
            股票列表
        """
        cache_key = f"search:{keyword}:{limit}"
        cached = self._get_cached(cache_key)
        if cached:
            return cached
        
        if not AKSHARE_AVAILABLE:
            return self._get_mock_stock_list(keyword, limit)
        
        try:
            loop = asyncio.get_event_loop()
            
            # 获取全部 A 股实时行情（包含代码和名称）
            df = await loop.run_in_executor(
                None,
                lambda: ak.stock_zh_a_spot_em()
            )
            
            if df is None or df.empty:
                return self._get_mock_stock_list(keyword, limit)
            
            # 模糊匹配代码或名称
            keyword_upper = keyword.upper()
            mask = (
                df['代码'].str.contains(keyword_upper, na=False) |
                df['名称'].str.contains(keyword, na=False)
            )
            matched = df[mask].head(limit)
            
            results = []
            for _, row in matched.iterrows():
                code = str(row['代码'])
                # 确定市场前缀
                if code.startswith('6'):
                    full_code = f"SH{code}"
                elif code.startswith('0') or code.startswith('3'):
                    full_code = f"SZ{code}"
                else:
                    full_code = code
                
                results.append({
                    "code": code,
                    "name": str(row['名称']),
                    "full_code": full_code,
                    "price": float(row.get('最新价', 0)) if pd.notna(row.get('最新价')) else 0,
                    "change_percent": float(row.get('涨跌幅', 0)) if pd.notna(row.get('涨跌幅')) else 0,
                })
            
            self._set_cache(cache_key, results)
            return results
            
        except Exception as e:
            logger.error(f"Failed to search stocks: {e}")
            return self._get_mock_stock_list(keyword, limit)
    
    def _get_mock_stock_list(self, keyword: str, limit: int) -> List[Dict[str, Any]]:
        """返回模拟股票列表"""
        mock_stocks = [
            {"code": "600519", "name": "贵州茅台", "full_code": "SH600519", "price": 1420.0, "change_percent": 0.5},
            {"code": "000001", "name": "平安银行", "full_code": "SZ000001", "price": 12.0, "change_percent": -0.3},
            {"code": "601318", "name": "中国平安", "full_code": "SH601318", "price": 45.0, "change_percent": 0.2},
            {"code": "000858", "name": "五粮液", "full_code": "SZ000858", "price": 150.0, "change_percent": 1.1},
            {"code": "002594", "name": "比亚迪", "full_code": "SZ002594", "price": 250.0, "change_percent": -0.8},
            {"code": "600036", "name": "招商银行", "full_code": "SH600036", "price": 35.0, "change_percent": 0.1},
            {"code": "601166", "name": "兴业银行", "full_code": "SH601166", "price": 18.0, "change_percent": 0.3},
            {"code": "000333", "name": "美的集团", "full_code": "SZ000333", "price": 65.0, "change_percent": 0.6},
            {"code": "002415", "name": "海康威视", "full_code": "SZ002415", "price": 32.0, "change_percent": -0.5},
            {"code": "600276", "name": "恒瑞医药", "full_code": "SH600276", "price": 42.0, "change_percent": 0.4},
        ]
        
        keyword_lower = keyword.lower()
        filtered = [
            s for s in mock_stocks
            if keyword_lower in s["code"].lower() or keyword_lower in s["name"].lower()
        ]
        return filtered[:limit]
    
    async def get_stock_info(self, stock_code: str) -> Optional[Dict[str, Any]]:
        """
        获取股票基本信息
        """
        if not AKSHARE_AVAILABLE:
            return None
        
        try:
            symbol = self._get_symbol(stock_code)
            
            loop = asyncio.get_event_loop()
            df = await loop.run_in_executor(
                None,
                lambda: ak.stock_individual_info_em(symbol=symbol)
            )
            
            if df is None or df.empty:
                return None
            
            # 转换为字典
            info = {}
            for _, row in df.iterrows():
                info[row['item']] = row['value']
            
            return info
            
        except Exception as e:
            logger.error(f"Failed to fetch stock info for {stock_code}: {e}")
            return None
    
    def _generate_mock_kline(self, stock_code: str, days: int) -> List[Dict[str, Any]]:
        """
        生成模拟K线数据（当 akshare 不可用时使用）
        """
        import random
        
        # 根据股票代码设定基准价格
        base_prices = {
            "600519": 1500.0,  # 贵州茅台
            "000001": 12.0,    # 平安银行
            "601318": 45.0,    # 中国平安
            "000858": 150.0,   # 五粮液
            "002594": 250.0,   # 比亚迪
        }
        
        code = self._normalize_code(stock_code)
        base_price = base_prices.get(code, 50.0)
        current_price = base_price
        
        kline_data = []
        for i in range(days):
            dt = datetime.now() - timedelta(days=days - i - 1)
            # 跳过周末
            if dt.weekday() >= 5:
                continue
                
            timestamp = int(dt.timestamp() * 1000)
            date_str = dt.strftime("%Y-%m-%d")
            
            # 随机波动
            change_percent = random.uniform(-3, 3)
            open_price = current_price
            close_price = current_price * (1 + change_percent / 100)
            high_price = max(open_price, close_price) * (1 + random.uniform(0, 1.5) / 100)
            low_price = min(open_price, close_price) * (1 - random.uniform(0, 1.5) / 100)
            volume = random.randint(50000, 500000)
            turnover = volume * close_price
            
            kline_data.append({
                "timestamp": timestamp,
                "date": date_str,
                "open": round(open_price, 2),
                "high": round(high_price, 2),
                "low": round(low_price, 2),
                "close": round(close_price, 2),
                "volume": volume,
                "turnover": round(turnover, 2),
                "change_percent": round(change_percent, 2),
                "change_amount": round(close_price - open_price, 2),
                "amplitude": round((high_price - low_price) / open_price * 100, 2),
                "turnover_rate": round(random.uniform(0.5, 5), 2),
            })
            
            current_price = close_price
        
        return kline_data[-days:] if len(kline_data) > days else kline_data
    
    async def get_financial_indicators(self, stock_code: str) -> Optional[Dict[str, Any]]:
        """
        获取股票财务指标（用于辩论分析）
        
        包括：PE、PB、ROE、净利润增长率等
        
        Args:
            stock_code: 股票代码
            
        Returns:
            财务指标字典
        """
        cache_key = f"financial:{stock_code}"
        cached = self._get_cached(cache_key, ttl=3600)  # 财务数据缓存1小时
        if cached:
            return cached
        
        if not AKSHARE_AVAILABLE:
            logger.warning("akshare not available, returning mock financial data")
            return self._get_mock_financial_indicators(stock_code)
        
        try:
            symbol = self._get_symbol(stock_code)
            loop = asyncio.get_event_loop()
            
            # 方法1：从实时行情获取基础估值数据
            spot_df = await loop.run_in_executor(
                None,
                lambda: ak.stock_zh_a_spot_em()
            )
            
            financial_data = {}
            
            if spot_df is not None and not spot_df.empty:
                row = spot_df[spot_df['代码'] == symbol]
                if not row.empty:
                    row = row.iloc[0]
                    financial_data.update({
                        "pe_ratio": self._safe_float(row.get('市盈率-动态')),
                        "pb_ratio": self._safe_float(row.get('市净率')),
                        "total_market_value": self._safe_float(row.get('总市值')),
                        "circulating_market_value": self._safe_float(row.get('流通市值')),
                        "turnover_rate": self._safe_float(row.get('换手率')),
                        "volume_ratio": self._safe_float(row.get('量比')),
                        "amplitude": self._safe_float(row.get('振幅')),
                        "price_52w_high": self._safe_float(row.get('52周最高')),
                        "price_52w_low": self._safe_float(row.get('52周最低')),
                    })
            
            # 方法2：尝试获取更详细的财务摘要
            try:
                financial_abstract = await loop.run_in_executor(
                    None,
                    lambda: ak.stock_financial_abstract_ths(symbol=symbol)
                )
                
                if financial_abstract is not None and not financial_abstract.empty:
                    # 取最新一期数据
                    latest = financial_abstract.iloc[0] if len(financial_abstract) > 0 else None
                    if latest is not None:
                        financial_data.update({
                            "roe": self._safe_float(latest.get('净资产收益率')),
                            "gross_profit_margin": self._safe_float(latest.get('毛利率')),
                            "net_profit_margin": self._safe_float(latest.get('净利率')),
                            "debt_ratio": self._safe_float(latest.get('资产负债率')),
                            "revenue_yoy": self._safe_float(latest.get('营业总收入同比增长率')),
                            "profit_yoy": self._safe_float(latest.get('净利润同比增长率')),
                        })
            except Exception as e:
                logger.debug(f"Failed to fetch financial abstract for {stock_code}: {e}")
            
            if financial_data:
                self._set_cache(cache_key, financial_data)
                return financial_data
            
            return self._get_mock_financial_indicators(stock_code)
            
        except Exception as e:
            logger.error(f"Failed to fetch financial indicators for {stock_code}: {e}")
            return self._get_mock_financial_indicators(stock_code)
    
    def _safe_float(self, value, default=None) -> Optional[float]:
        """安全转换为浮点数"""
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return default
        try:
            return float(value)
        except (ValueError, TypeError):
            return default
    
    def _get_mock_financial_indicators(self, stock_code: str) -> Dict[str, Any]:
        """返回模拟财务指标"""
        return {
            "pe_ratio": 25.5,
            "pb_ratio": 3.2,
            "roe": 15.8,
            "total_market_value": 100000000000,  # 1000亿
            "circulating_market_value": 80000000000,
            "turnover_rate": 2.5,
            "gross_profit_margin": 45.2,
            "net_profit_margin": 22.1,
            "debt_ratio": 35.5,
            "revenue_yoy": 12.5,
            "profit_yoy": 18.3,
        }
    
    async def get_fund_flow(self, stock_code: str, days: int = 5) -> Optional[Dict[str, Any]]:
        """
        获取个股资金流向（用于辩论分析）
        
        包括：主力资金净流入、散户资金流向等
        
        Args:
            stock_code: 股票代码
            days: 获取最近几天的数据
            
        Returns:
            资金流向数据
        """
        cache_key = f"fund_flow:{stock_code}:{days}"
        cached = self._get_cached(cache_key, ttl=300)  # 资金流向缓存5分钟
        if cached:
            return cached
        
        if not AKSHARE_AVAILABLE:
            logger.warning("akshare not available, returning mock fund flow data")
            return self._get_mock_fund_flow(stock_code)
        
        try:
            symbol = self._get_symbol(stock_code)
            loop = asyncio.get_event_loop()
            
            # 获取个股资金流向
            df = await loop.run_in_executor(
                None,
                lambda: ak.stock_individual_fund_flow(stock=symbol, market="sh" if symbol.startswith("6") else "sz")
            )
            
            if df is None or df.empty:
                return self._get_mock_fund_flow(stock_code)
            
            # 取最近几天的数据
            df = df.head(days)
            
            # 汇总数据
            total_main_net = 0
            total_super_large_net = 0
            total_large_net = 0
            total_medium_net = 0
            total_small_net = 0
            daily_flows = []
            
            for _, row in df.iterrows():
                main_net = self._safe_float(row.get('主力净流入-净额'), 0)
                super_large_net = self._safe_float(row.get('超大单净流入-净额'), 0)
                large_net = self._safe_float(row.get('大单净流入-净额'), 0)
                medium_net = self._safe_float(row.get('中单净流入-净额'), 0)
                small_net = self._safe_float(row.get('小单净流入-净额'), 0)
                
                total_main_net += main_net
                total_super_large_net += super_large_net
                total_large_net += large_net
                total_medium_net += medium_net
                total_small_net += small_net
                
                daily_flows.append({
                    "date": str(row.get('日期', '')),
                    "main_net": main_net,
                    "super_large_net": super_large_net,
                    "large_net": large_net,
                    "medium_net": medium_net,
                    "small_net": small_net,
                })
            
            fund_flow_data = {
                "period_days": days,
                "total_main_net": total_main_net,
                "total_super_large_net": total_super_large_net,
                "total_large_net": total_large_net,
                "total_medium_net": total_medium_net,
                "total_small_net": total_small_net,
                "main_flow_trend": "流入" if total_main_net > 0 else "流出",
                "daily_flows": daily_flows,
            }
            
            self._set_cache(cache_key, fund_flow_data)
            return fund_flow_data
            
        except Exception as e:
            logger.error(f"Failed to fetch fund flow for {stock_code}: {e}")
            return self._get_mock_fund_flow(stock_code)
    
    def _get_mock_fund_flow(self, stock_code: str) -> Dict[str, Any]:
        """返回模拟资金流向数据"""
        return {
            "period_days": 5,
            "total_main_net": 50000000,  # 5000万
            "total_super_large_net": 30000000,
            "total_large_net": 20000000,
            "total_medium_net": -5000000,
            "total_small_net": -10000000,
            "main_flow_trend": "流入",
            "daily_flows": [],
        }
    
    async def get_debate_context(self, stock_code: str) -> Dict[str, Any]:
        """
        获取用于辩论的综合上下文数据
        
        整合财务指标、资金流向、实时行情等信息
        
        Args:
            stock_code: 股票代码
            
        Returns:
            综合上下文数据
        """
        # 并行获取多个数据源
        realtime_task = self.get_realtime_quote(stock_code)
        financial_task = self.get_financial_indicators(stock_code)
        fund_flow_task = self.get_fund_flow(stock_code, days=5)
        
        realtime, financial, fund_flow = await asyncio.gather(
            realtime_task, financial_task, fund_flow_task,
            return_exceptions=True
        )
        
        # 处理异常
        if isinstance(realtime, Exception):
            logger.error(f"Failed to get realtime quote: {realtime}")
            realtime = None
        if isinstance(financial, Exception):
            logger.error(f"Failed to get financial indicators: {financial}")
            financial = None
        if isinstance(fund_flow, Exception):
            logger.error(f"Failed to get fund flow: {fund_flow}")
            fund_flow = None
        
        # 生成文本摘要
        context_parts = []
        
        if realtime:
            context_parts.append(
                f"【实时行情】当前价: {realtime.get('price', 'N/A')}元, "
                f"涨跌幅: {realtime.get('change_percent', 'N/A')}%, "
                f"成交量: {realtime.get('volume', 'N/A')}"
            )
        
        if financial:
            pe = financial.get('pe_ratio')
            pb = financial.get('pb_ratio')
            roe = financial.get('roe')
            profit_yoy = financial.get('profit_yoy')
            context_parts.append(
                f"【估值指标】PE: {pe if pe else 'N/A'}, PB: {pb if pb else 'N/A'}, "
                f"ROE: {roe if roe else 'N/A'}%, 净利润同比: {profit_yoy if profit_yoy else 'N/A'}%"
            )
        
        if fund_flow:
            main_net = fund_flow.get('total_main_net', 0)
            main_net_str = f"{main_net/10000:.2f}万" if abs(main_net) < 100000000 else f"{main_net/100000000:.2f}亿"
            context_parts.append(
                f"【资金流向】近{fund_flow.get('period_days', 5)}日主力净{fund_flow.get('main_flow_trend', 'N/A')}: {main_net_str}"
            )
        
        return {
            "realtime": realtime,
            "financial": financial,
            "fund_flow": fund_flow,
            "summary": "\n".join(context_parts) if context_parts else "暂无额外数据",
        }


# 单例实例
stock_data_service = StockDataService()

