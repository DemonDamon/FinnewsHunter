"""
Alpha Mining 配置模块

定义训练、模型、回测等配置参数。

References:
- AlphaGPT upstream/model_core/config.py
"""

import torch
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class AlphaMiningConfig:
    """Alpha Mining 模块配置"""
    
    # ============ 设备配置 ============
    device: str = field(default_factory=lambda: "cuda" if torch.cuda.is_available() else "cpu")
    
    # ============ 模型配置 ============
    d_model: int = 64              # Transformer 嵌入维度
    nhead: int = 4                 # 注意力头数
    num_layers: int = 2            # Transformer 层数
    max_seq_len: int = 12          # 最大因子表达式长度
    
    # ============ 训练配置 ============
    batch_size: int = 1024         # 批量大小（每批生成的因子数）
    num_steps: int = 1000          # 训练步数
    lr: float = 1e-3               # 学习率
    
    # ============ 奖励配置 ============
    invalid_formula_reward: float = -5.0   # 无效公式惩罚
    constant_factor_reward: float = -2.0   # 常量因子惩罚
    low_activity_reward: float = -10.0     # 低活跃度惩罚
    constant_threshold: float = 1e-4       # 常量因子阈值（std < 此值视为常量）
    
    # ============ 回测配置 ============
    cost_rate: float = 0.0015      # A股交易费率（双边约0.3%）
    signal_threshold: float = 0.7  # 信号阈值（factor > threshold 时建仓）
    min_holding_days: int = 1      # 最小持仓天数
    min_activity: int = 5          # 最小活跃度（持仓天数）
    
    # ============ 特征配置 ============
    market_features: List[str] = field(default_factory=lambda: [
        "RET",           # 收益率
        "VOL",           # 波动率  
        "VOLUME_CHG",    # 成交量变化
        "TURNOVER",      # 换手率
    ])
    
    sentiment_features: List[str] = field(default_factory=lambda: [
        "SENTIMENT",     # 情感分数
        "NEWS_COUNT",    # 新闻数量
    ])
    
    enable_sentiment: bool = True  # 是否启用情感特征
    
    # ============ 持久化配置 ============
    checkpoint_dir: str = "checkpoints/alpha_mining"
    save_every_n_steps: int = 100
    
    @property
    def torch_device(self) -> torch.device:
        """获取 torch.device 对象"""
        return torch.device(self.device)
    
    @property
    def all_features(self) -> List[str]:
        """获取所有启用的特征列表"""
        features = self.market_features.copy()
        if self.enable_sentiment:
            features.extend(self.sentiment_features)
        return features
    
    @property
    def num_features(self) -> int:
        """特征数量"""
        return len(self.all_features)


# 默认配置实例
DEFAULT_CONFIG = AlphaMiningConfig()
