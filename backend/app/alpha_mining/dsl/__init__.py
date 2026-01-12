"""
因子表达式 DSL（Domain Specific Language）

包含操作符定义和词汇表管理。
"""

from .ops import OPS_CONFIG, ts_delay, ts_delta, ts_mean, ts_std
from .vocab import FactorVocab, FEATURES

__all__ = [
    "OPS_CONFIG",
    "ts_delay",
    "ts_delta", 
    "ts_mean",
    "ts_std",
    "FactorVocab",
    "FEATURES",
]
