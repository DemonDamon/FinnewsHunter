"""
Alpha Mining 工具函数

提供模拟数据生成、数据预处理等工具函数。
"""

import torch
import numpy as np
from typing import Tuple, Optional
import logging

from .config import AlphaMiningConfig, DEFAULT_CONFIG

logger = logging.getLogger(__name__)


def generate_mock_data(
    num_samples: int = 100,
    num_features: int = 6,
    time_steps: int = 252,
    seed: Optional[int] = 42,
    device: Optional[torch.device] = None
) -> Tuple[torch.Tensor, torch.Tensor]:
    """
    生成模拟行情数据用于测试
    
    Args:
        num_samples: 样本数（股票数）
        num_features: 特征数
        time_steps: 时间步数（交易日数）
        seed: 随机种子
        device: 设备
        
    Returns:
        features: [num_samples, num_features, time_steps]
        returns: [num_samples, time_steps]
    """
    if seed is not None:
        torch.manual_seed(seed)
        np.random.seed(seed)
    
    device = device or DEFAULT_CONFIG.torch_device
    
    # 生成模拟收益率（正态分布）
    returns = torch.randn(num_samples, time_steps, device=device) * 0.02
    
    # 生成模拟价格（累积收益）
    prices = torch.exp(returns.cumsum(dim=1))
    
    # 生成模拟特征
    features_list = []
    
    # Feature 0: RET - 收益率
    ret = returns.clone()
    features_list.append(ret)
    
    # Feature 1: VOL - 波动率（滚动 20 日标准差）
    vol = _rolling_std(returns, window=20)
    features_list.append(vol)
    
    # Feature 2: VOLUME_CHG - 成交量变化（模拟）
    volume = torch.abs(torch.randn(num_samples, time_steps, device=device))
    volume_chg = _pct_change(volume)
    features_list.append(volume_chg)
    
    # Feature 3: TURNOVER - 换手率（模拟）
    turnover = torch.abs(torch.randn(num_samples, time_steps, device=device)) * 0.05
    features_list.append(turnover)
    
    # Feature 4: SENTIMENT - 情感分数（模拟）
    sentiment = torch.randn(num_samples, time_steps, device=device) * 0.5
    features_list.append(sentiment)
    
    # Feature 5: NEWS_COUNT - 新闻数量（模拟）
    news_count = torch.abs(torch.randn(num_samples, time_steps, device=device)) * 5
    features_list.append(news_count)
    
    # 如果需要更多特征，填充随机噪声
    while len(features_list) < num_features:
        noise = torch.randn(num_samples, time_steps, device=device)
        features_list.append(noise)
    
    # 截取到指定特征数
    features_list = features_list[:num_features]
    
    # Stack features: [num_samples, num_features, time_steps]
    features = torch.stack(features_list, dim=1)
    
    # 标准化特征
    features = _robust_normalize(features)
    
    logger.debug(
        f"Generated mock data: features {features.shape}, returns {returns.shape}"
    )
    
    return features, returns


def _rolling_std(x: torch.Tensor, window: int = 20) -> torch.Tensor:
    """
    计算滚动标准差
    
    Args:
        x: [batch, time_steps]
        window: 窗口大小
        
    Returns:
        滚动标准差 [batch, time_steps]
    """
    batch_size, time_steps = x.shape
    device = x.device
    
    # Padding
    pad = torch.zeros((batch_size, window - 1), device=device)
    x_padded = torch.cat([pad, x], dim=1)
    
    # 使用 unfold 计算滚动窗口
    result = x_padded.unfold(1, window, 1).std(dim=-1)
    
    return result


def _pct_change(x: torch.Tensor) -> torch.Tensor:
    """
    计算百分比变化
    
    Args:
        x: [batch, time_steps]
        
    Returns:
        百分比变化 [batch, time_steps]
    """
    prev = torch.roll(x, 1, dims=1)
    prev[:, 0] = x[:, 0]  # 第一个值不变
    
    pct = (x - prev) / (prev + 1e-8)
    return pct


def _robust_normalize(x: torch.Tensor) -> torch.Tensor:
    """
    稳健标准化（使用中位数和 MAD）
    
    Args:
        x: [batch, num_features, time_steps]
        
    Returns:
        标准化后的张量
    """
    # 计算每个特征的中位数
    median = x.median(dim=2, keepdim=True).values
    
    # 计算 MAD (Median Absolute Deviation)
    mad = (x - median).abs().median(dim=2, keepdim=True).values + 1e-6
    
    # 标准化
    normalized = (x - median) / mad
    
    # 裁剪极端值
    normalized = torch.clamp(normalized, -5.0, 5.0)
    
    return normalized


def set_random_seed(seed: int):
    """设置随机种子以确保可复现性"""
    torch.manual_seed(seed)
    np.random.seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def get_device() -> torch.device:
    """获取最佳可用设备"""
    if torch.cuda.is_available():
        return torch.device("cuda")
    elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        return torch.device("mps")
    else:
        return torch.device("cpu")
