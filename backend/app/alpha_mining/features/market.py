"""
行情特征构建器

从原始行情数据（OHLCV）构建因子挖掘所需的标准化特征。

特征列表：
- RET: 收益率
- VOL: 波动率（滚动标准差）
- VOLUME_CHG: 成交量变化率
- TURNOVER: 换手率
"""

import torch
from typing import Dict, List, Optional, Union
import pandas as pd
import numpy as np
import logging

from ..config import AlphaMiningConfig, DEFAULT_CONFIG

logger = logging.getLogger(__name__)


class MarketFeatureBuilder:
    """
    行情特征构建器
    
    从 OHLCV 数据构建标准化的因子特征。
    
    Args:
        config: 配置实例
        vol_window: 波动率计算窗口
        normalize: 是否标准化特征
        
    Example:
        builder = MarketFeatureBuilder()
        features = builder.build(ohlcv_df)
    """
    
    # 支持的特征名称
    FEATURE_NAMES = ["RET", "VOL", "VOLUME_CHG", "TURNOVER"]
    
    def __init__(
        self,
        config: Optional[AlphaMiningConfig] = None,
        vol_window: int = 20,
        normalize: bool = True
    ):
        self.config = config or DEFAULT_CONFIG
        self.vol_window = vol_window
        self.normalize = normalize
        
        logger.info(
            f"MarketFeatureBuilder initialized: "
            f"vol_window={vol_window}, normalize={normalize}"
        )
    
    def build(
        self,
        data: Union[pd.DataFrame, Dict[str, torch.Tensor]],
        device: Optional[torch.device] = None
    ) -> torch.Tensor:
        """
        从行情数据构建特征张量
        
        Args:
            data: 行情数据，DataFrame 或张量字典
                DataFrame 需包含: close, volume, (可选: turnover, shares)
                Dict 需包含: close, volume
            device: 目标设备
            
        Returns:
            特征张量 [batch, num_features, time_steps]
        """
        device = device or self.config.torch_device
        
        if isinstance(data, pd.DataFrame):
            return self._build_from_dataframe(data, device)
        elif isinstance(data, dict):
            return self._build_from_tensors(data, device)
        else:
            raise ValueError(f"Unsupported data type: {type(data)}")
    
    def _build_from_dataframe(
        self,
        df: pd.DataFrame,
        device: torch.device
    ) -> torch.Tensor:
        """
        从 DataFrame 构建特征
        
        支持两种格式：
        1. 单股票：index=date, columns=[close, volume, ...]
        2. 多股票：MultiIndex 或 pivot 后的 DataFrame
        """
        # 确保列名小写
        df = df.copy()
        df.columns = [c.lower() for c in df.columns]
        
        # 检查必需列
        if "close" not in df.columns:
            raise ValueError("DataFrame must have 'close' column")
        
        # 计算各特征
        close = torch.tensor(df["close"].values, dtype=torch.float32)
        
        # RET: 收益率
        ret = self._calc_returns(close)
        
        # VOL: 波动率
        vol = self._calc_volatility(ret, self.vol_window)
        
        # VOLUME_CHG: 成交量变化
        if "volume" in df.columns:
            volume = torch.tensor(df["volume"].values, dtype=torch.float32)
            volume_chg = self._calc_pct_change(volume)
        else:
            volume_chg = torch.zeros_like(ret)
        
        # TURNOVER: 换手率
        if "turnover" in df.columns:
            turnover = torch.tensor(df["turnover"].values, dtype=torch.float32)
        elif "volume" in df.columns and "shares" in df.columns:
            volume = df["volume"].values
            shares = df["shares"].values
            turnover = torch.tensor(volume / (shares + 1e-8), dtype=torch.float32)
        else:
            turnover = torch.zeros_like(ret)
        
        # Stack features: [num_features, time_steps]
        features = torch.stack([ret, vol, volume_chg, turnover], dim=0)
        
        # 标准化
        if self.normalize:
            features = self._robust_normalize(features)
        
        # 添加 batch 维度: [1, num_features, time_steps]
        features = features.unsqueeze(0).to(device)
        
        return features
    
    def _build_from_tensors(
        self,
        data: Dict[str, torch.Tensor],
        device: torch.device
    ) -> torch.Tensor:
        """
        从张量字典构建特征
        
        Args:
            data: 包含 close, volume 等张量的字典
                  每个张量形状为 [batch, time_steps] 或 [time_steps]
        """
        close = data["close"]
        
        # 确保是 2D: [batch, time_steps]
        if close.dim() == 1:
            close = close.unsqueeze(0)
        
        batch_size, time_steps = close.shape
        
        # RET
        ret = self._calc_returns(close)
        
        # VOL
        vol = self._calc_volatility(ret, self.vol_window)
        
        # VOLUME_CHG
        if "volume" in data:
            volume = data["volume"]
            if volume.dim() == 1:
                volume = volume.unsqueeze(0)
            volume_chg = self._calc_pct_change(volume)
        else:
            volume_chg = torch.zeros_like(ret)
        
        # TURNOVER
        if "turnover" in data:
            turnover = data["turnover"]
            if turnover.dim() == 1:
                turnover = turnover.unsqueeze(0)
        else:
            turnover = torch.zeros_like(ret)
        
        # Stack: [batch, num_features, time_steps]
        features = torch.stack([ret, vol, volume_chg, turnover], dim=1)
        
        # 标准化
        if self.normalize:
            features = self._robust_normalize(features)
        
        return features.to(device)
    
    def _calc_returns(self, close: torch.Tensor) -> torch.Tensor:
        """计算收益率"""
        # close: [batch, time] or [time]
        if close.dim() == 1:
            close = close.unsqueeze(0)
        
        prev_close = torch.roll(close, 1, dims=-1)
        prev_close[..., 0] = close[..., 0]
        
        returns = (close - prev_close) / (prev_close + 1e-8)
        returns[..., 0] = 0  # 第一个收益率设为 0
        
        return returns.squeeze(0) if close.size(0) == 1 else returns
    
    def _calc_volatility(self, returns: torch.Tensor, window: int) -> torch.Tensor:
        """计算滚动波动率"""
        if returns.dim() == 1:
            returns = returns.unsqueeze(0)
        
        batch_size, time_steps = returns.shape
        
        # Padding
        pad = torch.zeros((batch_size, window - 1), device=returns.device)
        padded = torch.cat([pad, returns], dim=-1)
        
        # 滚动标准差
        vol = padded.unfold(-1, window, 1).std(dim=-1)
        
        return vol.squeeze(0) if batch_size == 1 else vol
    
    def _calc_pct_change(self, x: torch.Tensor) -> torch.Tensor:
        """计算百分比变化"""
        if x.dim() == 1:
            x = x.unsqueeze(0)
        
        prev = torch.roll(x, 1, dims=-1)
        prev[..., 0] = x[..., 0]
        
        pct = (x - prev) / (prev + 1e-8)
        pct[..., 0] = 0
        
        return pct.squeeze(0) if x.size(0) == 1 else pct
    
    def _robust_normalize(self, features: torch.Tensor) -> torch.Tensor:
        """
        稳健标准化（使用中位数和 MAD）
        
        Args:
            features: [batch, num_features, time_steps] 或 [num_features, time_steps]
        """
        if features.dim() == 2:
            features = features.unsqueeze(0)
        
        # 计算每个特征的中位数
        median = features.median(dim=-1, keepdim=True).values
        
        # 计算 MAD
        mad = (features - median).abs().median(dim=-1, keepdim=True).values + 1e-6
        
        # 标准化
        normalized = (features - median) / mad
        
        # 裁剪极端值
        normalized = torch.clamp(normalized, -5.0, 5.0)
        
        return normalized
    
    def get_feature_names(self) -> List[str]:
        """获取特征名称列表"""
        return self.FEATURE_NAMES.copy()
    
    def build_batch(
        self,
        data_list: List[Union[pd.DataFrame, Dict[str, torch.Tensor]]],
        device: Optional[torch.device] = None
    ) -> torch.Tensor:
        """
        批量构建特征
        
        Args:
            data_list: 行情数据列表
            device: 目标设备
            
        Returns:
            特征张量 [batch, num_features, time_steps]
        """
        features_list = []
        for data in data_list:
            features = self.build(data, device)
            features_list.append(features)
        
        return torch.cat(features_list, dim=0)
