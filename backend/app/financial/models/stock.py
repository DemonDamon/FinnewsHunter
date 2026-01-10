"""
股票数据标准模型

借鉴 OpenBB Standard Models 设计:
- StockQueryParams: 股票数据查询参数
- StockPriceData: 股票价格数据 (K线)

来源参考:
- OpenBB: openbb_core.provider.standard_models
- 设计文档: research/codedeepresearch/OpenBB/FinnewsHunter_improvement_plan.md
"""
from pydantic import BaseModel, Field
from datetime import date, datetime
from typing import Optional, List
from enum import Enum


class KlineInterval(str, Enum):
    """K线周期"""
    MIN_1 = "1m"
    MIN_5 = "5m"
    MIN_15 = "15m"
    MIN_30 = "30m"
    MIN_60 = "60m"
    DAILY = "1d"
    WEEKLY = "1w"
    MONTHLY = "1M"


class AdjustType(str, Enum):
    """复权类型"""
    NONE = "none"
    QFQ = "qfq"    # 前复权
    HFQ = "hfq"    # 后复权


class StockQueryParams(BaseModel):
    """
    股票数据查询参数

    Example:
        >>> params = StockQueryParams(symbol="600519", interval=KlineInterval.DAILY)
        >>> fetcher.fetch(params)  # 返回 List[StockPriceData]
    """
    symbol: str = Field(..., description="股票代码，如 '600519' 或 'SH600519'")
    start_date: Optional[date] = Field(default=None, description="开始日期")
    end_date: Optional[date] = Field(default=None, description="结束日期")
    interval: KlineInterval = Field(
        default=KlineInterval.DAILY,
        description="K线周期"
    )
    adjust: AdjustType = Field(
        default=AdjustType.QFQ,
        description="复权类型"
    )
    limit: int = Field(
        default=90,
        ge=1,
        le=1000,
        description="返回条数"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "symbol": "600519",
                "interval": "1d",
                "limit": 90,
                "adjust": "qfq"
            }
        }


class StockPriceData(BaseModel):
    """
    股票价格数据（K线）

    与现有 StockDataService 返回格式对齐，
    确保迁移时的兼容性。
    """
    symbol: str = Field(..., description="股票代码")
    date: datetime = Field(..., description="交易时间")
    open: float = Field(..., description="开盘价")
    high: float = Field(..., description="最高价")
    low: float = Field(..., description="最低价")
    close: float = Field(..., description="收盘价")
    volume: int = Field(..., description="成交量")
    turnover: Optional[float] = Field(default=None, description="成交额")
    change_percent: Optional[float] = Field(default=None, description="涨跌幅 %")
    change_amount: Optional[float] = Field(default=None, description="涨跌额")
    amplitude: Optional[float] = Field(default=None, description="振幅 %")
    turnover_rate: Optional[float] = Field(default=None, description="换手率 %")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }

    def to_legacy_dict(self) -> dict:
        """
        转换为旧版 StockDataService 格式 (兼容现有代码)

        Returns:
            与旧版 get_kline_data 返回格式一致的字典
        """
        return {
            "timestamp": int(self.date.timestamp() * 1000),
            "date": self.date.strftime("%Y-%m-%d") if self.date else None,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "turnover": self.turnover or 0,
            "change_percent": self.change_percent or 0,
            "change_amount": self.change_amount or 0,
            "amplitude": self.amplitude or 0,
            "turnover_rate": self.turnover_rate or 0,
        }


class StockRealtimeData(BaseModel):
    """股票实时行情"""
    symbol: str
    name: str
    price: float
    change_percent: float
    change_amount: float
    volume: int
    turnover: float
    high: float
    low: float
    open: float
    prev_close: float
    timestamp: datetime = Field(default_factory=datetime.now)


class StockFinancialData(BaseModel):
    """股票财务指标"""
    symbol: str
    pe_ratio: Optional[float] = None          # 市盈率
    pb_ratio: Optional[float] = None          # 市净率
    roe: Optional[float] = None               # 净资产收益率
    total_market_value: Optional[float] = None
    circulating_market_value: Optional[float] = None
    gross_profit_margin: Optional[float] = None
    net_profit_margin: Optional[float] = None
    debt_ratio: Optional[float] = None
    revenue_yoy: Optional[float] = None       # 营收同比
    profit_yoy: Optional[float] = None        # 净利润同比
