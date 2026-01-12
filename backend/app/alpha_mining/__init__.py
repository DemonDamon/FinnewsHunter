"""
M12: Alpha Mining Module for FinnewsHunter

基于 AlphaGPT 技术的量化因子自动挖掘模块。
使用符号回归 + 强化学习自动发现有预测能力的交易因子。

核心组件：
- dsl: 因子表达式 DSL（操作符、词汇表）
- vm: 因子执行器（StackVM）
- model: 因子生成模型（AlphaGenerator）和训练器（AlphaTrainer）
- features: 特征构建器（行情、情感）
- backtest: 因子回测评估
- tools: AgenticX 工具封装

References:
- AlphaGPT: https://github.com/imbue-bit/AlphaGPT
- 技术方案: researches/AlphaGPT/AlphaGPT_proposal.md
"""

__version__ = "0.1.0"
__author__ = "FinnewsHunter Team"

from .config import AlphaMiningConfig, DEFAULT_CONFIG
from .dsl.vocab import FactorVocab, DEFAULT_VOCAB
from .dsl.ops import OPS_CONFIG
from .vm.factor_vm import FactorVM
from .model.alpha_generator import AlphaGenerator
from .model.trainer import AlphaTrainer
from .features.market import MarketFeatureBuilder
from .features.sentiment import SentimentFeatureBuilder
from .backtest.evaluator import FactorEvaluator
from .utils import generate_mock_data

__all__ = [
    # Config
    "AlphaMiningConfig",
    "DEFAULT_CONFIG",
    # DSL
    "FactorVocab",
    "DEFAULT_VOCAB",
    "OPS_CONFIG",
    # VM
    "FactorVM",
    # Model
    "AlphaGenerator",
    "AlphaTrainer",
    # Features
    "MarketFeatureBuilder",
    "SentimentFeatureBuilder",
    # Backtest
    "FactorEvaluator",
    # Utils
    "generate_mock_data",
]
