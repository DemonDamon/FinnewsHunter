"""
因子生成模型和训练器

- AlphaGenerator: Transformer 策略网络，生成因子表达式
- AlphaTrainer: RL 训练器，使用 REINFORCE 算法优化
"""

from .alpha_generator import AlphaGenerator
from .trainer import AlphaTrainer

__all__ = ["AlphaGenerator", "AlphaTrainer"]
