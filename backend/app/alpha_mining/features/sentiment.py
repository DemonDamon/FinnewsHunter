"""
情感特征构建器

从 FinnewsHunter 的新闻分析结果构建情感特征。

特征列表：
- SENTIMENT: 情感分数（-1 到 1）
- NEWS_COUNT: 新闻数量（标准化）

与 FinnewsHunter 现有组件集成：
- 使用 SentimentAgent 的分析结果
- 从 PostgreSQL/Milvus 获取历史情感数据
"""

import torch
from typing import Dict, List, Optional, Union, Any
import pandas as pd
import numpy as np
import logging
from datetime import datetime, timedelta

from ..config import AlphaMiningConfig, DEFAULT_CONFIG

logger = logging.getLogger(__name__)


class SentimentFeatureBuilder:
    """
    情感特征构建器
    
    从新闻情感分析结果构建因子特征。
    
    Args:
        config: 配置实例
        sentiment_decay: 情感衰减因子（用于时序平滑）
        normalize: 是否标准化特征
        
    Example:
        builder = SentimentFeatureBuilder()
        features = builder.build(sentiment_data)
    """
    
    # 支持的特征名称
    FEATURE_NAMES = ["SENTIMENT", "NEWS_COUNT"]
    
    def __init__(
        self,
        config: Optional[AlphaMiningConfig] = None,
        sentiment_decay: float = 0.9,
        normalize: bool = True
    ):
        self.config = config or DEFAULT_CONFIG
        self.sentiment_decay = sentiment_decay
        self.normalize = normalize
        
        logger.info(
            f"SentimentFeatureBuilder initialized: "
            f"decay={sentiment_decay}, normalize={normalize}"
        )
    
    def build(
        self,
        data: Union[pd.DataFrame, Dict[str, Any], List[Dict]],
        time_steps: Optional[int] = None,
        device: Optional[torch.device] = None
    ) -> torch.Tensor:
        """
        从情感数据构建特征张量
        
        Args:
            data: 情感数据，支持多种格式：
                - DataFrame: columns=[date, sentiment, news_count]
                - Dict: {"sentiment": [...], "news_count": [...]}
                - List[Dict]: [{"date": ..., "sentiment": ..., "count": ...}, ...]
            time_steps: 目标时间步数（用于对齐行情数据）
            device: 目标设备
            
        Returns:
            特征张量 [1, 2, time_steps] (SENTIMENT, NEWS_COUNT)
        """
        device = device or self.config.torch_device
        
        if isinstance(data, pd.DataFrame):
            sentiment, news_count = self._parse_dataframe(data)
        elif isinstance(data, dict):
            sentiment, news_count = self._parse_dict(data)
        elif isinstance(data, list):
            sentiment, news_count = self._parse_list(data)
        else:
            raise ValueError(f"Unsupported data type: {type(data)}")
        
        # 转换为张量
        sentiment = torch.tensor(sentiment, dtype=torch.float32)
        news_count = torch.tensor(news_count, dtype=torch.float32)
        
        # 对齐时间步
        if time_steps is not None:
            sentiment = self._align_time_steps(sentiment, time_steps)
            news_count = self._align_time_steps(news_count, time_steps)
        
        # 应用情感衰减（指数平滑）
        sentiment = self._apply_decay(sentiment)
        
        # Stack: [2, time_steps]
        features = torch.stack([sentiment, news_count], dim=0)
        
        # 标准化
        if self.normalize:
            features = self._normalize(features)
        
        # 添加 batch 维度: [1, 2, time_steps]
        features = features.unsqueeze(0).to(device)
        
        return features
    
    def _parse_dataframe(self, df: pd.DataFrame):
        """从 DataFrame 解析情感数据"""
        df = df.copy()
        df.columns = [c.lower() for c in df.columns]
        
        # 情感分数
        if "sentiment" in df.columns:
            sentiment = df["sentiment"].fillna(0).values
        elif "sentiment_score" in df.columns:
            sentiment = df["sentiment_score"].fillna(0).values
        else:
            sentiment = np.zeros(len(df))
            logger.warning("No sentiment column found, using zeros")
        
        # 新闻数量
        if "news_count" in df.columns:
            news_count = df["news_count"].fillna(0).values
        elif "count" in df.columns:
            news_count = df["count"].fillna(0).values
        else:
            news_count = np.ones(len(df))  # 默认每天 1 条
        
        return sentiment, news_count
    
    def _parse_dict(self, data: Dict[str, Any]):
        """从字典解析情感数据"""
        sentiment = data.get("sentiment", data.get("sentiment_score", []))
        news_count = data.get("news_count", data.get("count", []))
        
        sentiment = np.array(sentiment) if sentiment else np.array([0])
        news_count = np.array(news_count) if news_count else np.array([1])
        
        return sentiment, news_count
    
    def _parse_list(self, data: List[Dict]):
        """从列表解析情感数据"""
        sentiment = []
        news_count = []
        
        for item in data:
            s = item.get("sentiment", item.get("sentiment_score", 0))
            c = item.get("news_count", item.get("count", 1))
            sentiment.append(s)
            news_count.append(c)
        
        return np.array(sentiment), np.array(news_count)
    
    def _align_time_steps(self, x: torch.Tensor, target_len: int) -> torch.Tensor:
        """对齐时间步长度"""
        current_len = len(x)
        
        if current_len == target_len:
            return x
        elif current_len > target_len:
            # 截取最近的数据
            return x[-target_len:]
        else:
            # 前面填充 0
            pad = torch.zeros(target_len - current_len)
            return torch.cat([pad, x])
    
    def _apply_decay(self, sentiment: torch.Tensor) -> torch.Tensor:
        """
        应用指数衰减平滑
        
        情感影响会随时间衰减，使用指数移动平均来平滑
        """
        if self.sentiment_decay >= 1.0:
            return sentiment
        
        result = torch.zeros_like(sentiment)
        result[0] = sentiment[0]
        
        for i in range(1, len(sentiment)):
            result[i] = self.sentiment_decay * result[i-1] + (1 - self.sentiment_decay) * sentiment[i]
        
        return result
    
    def _normalize(self, features: torch.Tensor) -> torch.Tensor:
        """标准化特征"""
        # features: [2, time_steps]
        
        # SENTIMENT: 已经在 [-1, 1] 范围内，保持不变
        # NEWS_COUNT: 标准化到 0 均值、1 标准差
        news_count = features[1]
        if news_count.std() > 0:
            features[1] = (news_count - news_count.mean()) / (news_count.std() + 1e-6)
        
        # 裁剪极端值
        features = torch.clamp(features, -5.0, 5.0)
        
        return features
    
    def get_feature_names(self) -> List[str]:
        """获取特征名称列表"""
        return self.FEATURE_NAMES.copy()
    
    def build_from_finnews(
        self,
        stock_code: str,
        start_date: datetime,
        end_date: datetime,
        db_session: Any = None,
        device: Optional[torch.device] = None
    ) -> torch.Tensor:
        """
        从 FinnewsHunter 数据库构建情感特征
        
        Args:
            stock_code: 股票代码
            start_date: 开始日期
            end_date: 结束日期
            db_session: 数据库会话（可选，用于真实数据）
            device: 目标设备
            
        Returns:
            特征张量 [1, 2, time_steps]
        """
        device = device or self.config.torch_device
        
        # 计算交易日数
        time_steps = (end_date - start_date).days
        
        if db_session is None:
            # 无数据库连接时返回模拟数据
            logger.warning("No db_session provided, returning mock sentiment data")
            return self._generate_mock_sentiment(time_steps, device)
        
        # TODO: 实现真实数据查询
        # 查询逻辑示例：
        # query = """
        #     SELECT date, AVG(sentiment_score) as sentiment, COUNT(*) as news_count
        #     FROM news_analysis
        #     WHERE stock_code = :code AND date BETWEEN :start AND :end
        #     GROUP BY date
        #     ORDER BY date
        # """
        # results = db_session.execute(query, {...})
        
        logger.info(f"Building sentiment features for {stock_code}")
        return self._generate_mock_sentiment(time_steps, device)
    
    def _generate_mock_sentiment(
        self,
        time_steps: int,
        device: torch.device
    ) -> torch.Tensor:
        """生成模拟情感数据"""
        # 模拟情感分数（正态分布，均值 0）
        sentiment = torch.randn(time_steps) * 0.3
        sentiment = torch.clamp(sentiment, -1, 1)
        
        # 模拟新闻数量（泊松分布）
        news_count = torch.abs(torch.randn(time_steps)) * 3 + 1
        
        # Stack 并添加 batch 维度
        features = torch.stack([sentiment, news_count], dim=0)
        
        if self.normalize:
            features = self._normalize(features)
        
        return features.unsqueeze(0).to(device)
    
    def combine_with_market(
        self,
        market_features: torch.Tensor,
        sentiment_features: torch.Tensor
    ) -> torch.Tensor:
        """
        合并行情特征和情感特征
        
        Args:
            market_features: [batch, 4, time_steps] (RET, VOL, VOLUME_CHG, TURNOVER)
            sentiment_features: [batch, 2, time_steps] (SENTIMENT, NEWS_COUNT)
            
        Returns:
            合并后的特征 [batch, 6, time_steps]
        """
        return torch.cat([market_features, sentiment_features], dim=1)
