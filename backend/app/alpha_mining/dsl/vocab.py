"""
因子词汇表管理

管理因子表达式中的 token 词汇表，包括：
- 特征 token（RET, VOL, VOLUME_CHG 等）
- 操作符 token（ADD, SUB, MUL 等）

提供 token <-> name 双向映射。

References:
- AlphaGPT upstream/model_core/alphagpt.py:10-14
"""

from typing import List, Dict, Optional
from dataclasses import dataclass, field

from .ops import OPS_CONFIG, get_op_names


# 默认特征列表
FEATURES: List[str] = [
    "RET",           # 收益率
    "VOL",           # 波动率
    "VOLUME_CHG",    # 成交量变化
    "TURNOVER",      # 换手率
    "SENTIMENT",     # 情感分数
    "NEWS_COUNT",    # 新闻数量
]


@dataclass
class FactorVocab:
    """
    因子词汇表
    
    词汇表结构：[FEATURES..., OPERATORS...]
    - 前 num_features 个 token 是特征
    - 后 num_ops 个 token 是操作符
    
    Example:
        vocab = FactorVocab(features=["RET", "VOL"])
        vocab.token_to_name(0)  # -> "RET"
        vocab.name_to_token("ADD")  # -> 2 (假设有 2 个特征)
    """
    
    features: List[str] = field(default_factory=lambda: FEATURES.copy())
    
    def __post_init__(self):
        """初始化词汇表映射"""
        self._operators = get_op_names()
        self._vocab = self.features + self._operators
        
        # 构建映射
        self._token_to_name: Dict[int, str] = {
            i: name for i, name in enumerate(self._vocab)
        }
        self._name_to_token: Dict[str, int] = {
            name: i for i, name in enumerate(self._vocab)
        }
    
    @property
    def vocab_size(self) -> int:
        """词汇表大小"""
        return len(self._vocab)
    
    @property
    def num_features(self) -> int:
        """特征数量"""
        return len(self.features)
    
    @property
    def num_ops(self) -> int:
        """操作符数量"""
        return len(self._operators)
    
    @property
    def feature_offset(self) -> int:
        """特征 token 的结束位置（也是操作符的起始位置）"""
        return self.num_features
    
    def token_to_name(self, token: int) -> str:
        """
        将 token ID 转换为名称
        
        Args:
            token: token ID
            
        Returns:
            token 对应的名称
            
        Raises:
            KeyError: 如果 token 不存在
        """
        if token not in self._token_to_name:
            raise KeyError(f"Unknown token: {token}")
        return self._token_to_name[token]
    
    def name_to_token(self, name: str) -> int:
        """
        将名称转换为 token ID
        
        Args:
            name: 特征或操作符名称
            
        Returns:
            对应的 token ID
            
        Raises:
            KeyError: 如果名称不存在
        """
        if name not in self._name_to_token:
            raise KeyError(f"Unknown name: {name}")
        return self._name_to_token[name]
    
    def is_feature(self, token: int) -> bool:
        """判断 token 是否为特征"""
        return 0 <= token < self.feature_offset
    
    def is_operator(self, token: int) -> bool:
        """判断 token 是否为操作符"""
        return self.feature_offset <= token < self.vocab_size
    
    def get_operator_arity(self, token: int) -> int:
        """
        获取操作符的参数数量
        
        Args:
            token: 操作符 token ID
            
        Returns:
            参数数量（1, 2 或 3）
            
        Raises:
            ValueError: 如果不是操作符
        """
        if not self.is_operator(token):
            raise ValueError(f"Token {token} is not an operator")
        
        op_index = token - self.feature_offset
        return OPS_CONFIG[op_index][2]
    
    def get_operator_func(self, token: int):
        """
        获取操作符的函数
        
        Args:
            token: 操作符 token ID
            
        Returns:
            操作符函数
            
        Raises:
            ValueError: 如果不是操作符
        """
        if not self.is_operator(token):
            raise ValueError(f"Token {token} is not an operator")
        
        op_index = token - self.feature_offset
        return OPS_CONFIG[op_index][1]
    
    def get_all_tokens(self) -> List[int]:
        """获取所有 token ID"""
        return list(range(self.vocab_size))
    
    def get_feature_tokens(self) -> List[int]:
        """获取所有特征 token ID"""
        return list(range(self.num_features))
    
    def get_operator_tokens(self) -> List[int]:
        """获取所有操作符 token ID"""
        return list(range(self.feature_offset, self.vocab_size))
    
    def __repr__(self) -> str:
        return f"FactorVocab(features={self.features}, vocab_size={self.vocab_size})"


# 默认词汇表实例
DEFAULT_VOCAB = FactorVocab()
