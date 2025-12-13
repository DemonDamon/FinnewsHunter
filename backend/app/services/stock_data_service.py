"""
股票数据服务 - 使用 akshare 获取真实股票数据
"""
import logging
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from functools import lru_cache
import asyncio

logger = logging.getLogger(__name__)

# 尝试导入 akshare
try:
    import akshare as ak
    import pandas as pd
    AKSHARE_AVAILABLE = True
except ImportError:
    AKSHARE_AVAILABLE = False
    logger.warning("akshare not installed, using mock data")


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
    
    def _is_cache_valid(self, key: str) -> bool:
        """检查缓存是否有效"""
        if key not in self._cache:
            return False
        _, timestamp = self._cache[key]
        return (datetime.now() - timestamp).seconds < self.CACHE_TTL
    
    def _get_cached(self, key: str) -> Optional[Any]:
        """获取缓存数据"""
        if self._is_cache_valid(key):
            return self._cache[key][0]
        return None
    
    def _set_cache(self, key: str, data: Any):
        """设置缓存"""
        self._cache[key] = (data, datetime.now())
    
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
        cached = self._get_cached(cache_key)
        if cached:
            logger.debug(f"Cache hit for {cache_key}")
            return cached
        
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
                logger.warning(f"No data returned for {stock_code} period={period}")
                return self._generate_mock_kline(stock_code, limit)
            
            self._set_cache(cache_key, kline_data)
            logger.info(f"Fetched {len(kline_data)} kline records for {stock_code} period={period}")
            return kline_data
            
        except Exception as e:
            logger.error(f"Failed to fetch kline data for {stock_code}: {e}")
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
        # 多获取一些天数，确保有足够数据（考虑周末和节假日）
        start_date = end_date - timedelta(days=limit * 2)
        
        df = await loop.run_in_executor(
            None,
            lambda: ak.stock_zh_a_hist(
                symbol=symbol,
                start_date=start_date.strftime("%Y%m%d"),
                end_date=end_date.strftime("%Y%m%d"),
                adjust=adjust
            )
        )
        
        if df is None or df.empty:
            return []
        
        # 只取最近 limit 条数据
        df = df.tail(limit)
        
        # 转换为标准格式
        kline_data = []
        for _, row in df.iterrows():
            date_str = str(row['日期'])
            if isinstance(row['日期'], str):
                dt = datetime.strptime(date_str, "%Y-%m-%d")
            else:
                dt = pd.to_datetime(row['日期'])
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
        
        # 只取最近 limit 条数据
        df = df.tail(limit)
        
        # 转换为标准格式
        kline_data = []
        for _, row in df.iterrows():
            # 分钟数据的时间列名是 '时间'
            time_str = str(row['时间'])
            try:
                dt = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
            except:
                try:
                    dt = pd.to_datetime(row['时间'])
                except:
                    continue
            
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


# 单例实例
stock_data_service = StockDataService()

