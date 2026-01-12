"""
因子表达式执行器（栈式虚拟机）

使用栈式执行方式解析和执行因子表达式 token 序列。

执行流程：
1. 遍历 token 序列
2. 如果是特征 token：将对应特征数据入栈
3. 如果是操作符 token：弹出所需参数，执行操作，结果入栈
4. 最终栈中应只剩一个结果

References:
- AlphaGPT upstream/model_core/vm.py
"""

import torch
from typing import List, Optional, Union
import logging

from ..dsl.vocab import FactorVocab, DEFAULT_VOCAB

logger = logging.getLogger(__name__)


class FactorVM:
    """
    因子表达式栈式虚拟机
    
    执行因子表达式 token 序列，返回计算结果。
    
    Example:
        vm = FactorVM()
        # features: [batch, num_features, time_steps]
        # formula: [0, 1, 6] 表示 ADD(RET, VOL)
        result = vm.execute([0, 1, 6], features)
    """
    
    def __init__(self, vocab: Optional[FactorVocab] = None):
        """
        初始化虚拟机
        
        Args:
            vocab: 词汇表实例，默认使用 DEFAULT_VOCAB
        """
        self.vocab = vocab or DEFAULT_VOCAB
    
    def execute(
        self, 
        formula: List[int], 
        features: torch.Tensor
    ) -> Optional[torch.Tensor]:
        """
        执行因子表达式
        
        Args:
            formula: token 序列，如 [0, 1, 6] 表示 ADD(RET, VOL)
            features: 特征张量，形状 [batch, num_features, time_steps]
            
        Returns:
            因子值张量 [batch, time_steps]，如果表达式无效则返回 None
            
        Note:
            - 如果堆栈溢出/不足，返回 None
            - 如果结果包含 NaN/Inf，会自动替换为 0
            - 如果最终堆栈不是恰好一个元素，返回 None
        """
        stack: List[torch.Tensor] = []
        
        try:
            for token in formula:
                token = int(token)
                
                if self.vocab.is_feature(token):
                    # 特征 token：从特征张量中取出对应特征
                    if token >= features.shape[1]:
                        logger.debug(f"Feature index {token} out of range")
                        return None
                    stack.append(features[:, token, :])
                    
                elif self.vocab.is_operator(token):
                    # 操作符 token：执行操作
                    arity = self.vocab.get_operator_arity(token)
                    
                    # 检查堆栈是否有足够参数
                    if len(stack) < arity:
                        logger.debug(f"Stack underflow: need {arity}, have {len(stack)}")
                        return None
                    
                    # 弹出参数（注意顺序：先弹出的是后入的）
                    args = []
                    for _ in range(arity):
                        args.append(stack.pop())
                    args.reverse()  # 恢复正确顺序
                    
                    # 执行操作
                    func = self.vocab.get_operator_func(token)
                    result = func(*args)
                    
                    # 处理 NaN 和 Inf
                    if torch.isnan(result).any() or torch.isinf(result).any():
                        result = torch.nan_to_num(
                            result, 
                            nan=0.0, 
                            posinf=1.0, 
                            neginf=-1.0
                        )
                    
                    stack.append(result)
                    
                else:
                    # 未知 token
                    logger.debug(f"Unknown token: {token}")
                    return None
            
            # 检查最终堆栈状态
            if len(stack) == 1:
                return stack[0]
            else:
                logger.debug(f"Invalid stack state: {len(stack)} elements remaining")
                return None
                
        except Exception as e:
            logger.debug(f"Execution error: {e}")
            return None
    
    def decode(self, formula: List[int]) -> str:
        """
        将 token 序列解码为人类可读的表达式字符串
        
        使用逆波兰表达式解析，转换为前缀表示法（函数调用形式）
        
        Args:
            formula: token 序列
            
        Returns:
            人类可读的表达式，如 "ADD(RET, VOL)"
            
        Example:
            vm.decode([0, 1, 6])  # -> "ADD(RET, VOL)"
            vm.decode([0, 4])    # -> "NEG(RET)"
        """
        stack: List[str] = []
        
        try:
            for token in formula:
                token = int(token)
                
                if self.vocab.is_feature(token):
                    # 特征：直接入栈名称
                    name = self.vocab.token_to_name(token)
                    stack.append(name)
                    
                elif self.vocab.is_operator(token):
                    # 操作符：弹出参数，构建表达式
                    name = self.vocab.token_to_name(token)
                    arity = self.vocab.get_operator_arity(token)
                    
                    if len(stack) < arity:
                        return f"<INVALID: stack underflow at {name}>"
                    
                    args = []
                    for _ in range(arity):
                        args.append(stack.pop())
                    args.reverse()
                    
                    # 构建函数调用形式
                    expr = f"{name}({', '.join(args)})"
                    stack.append(expr)
                    
                else:
                    return f"<INVALID: unknown token {token}>"
            
            if len(stack) == 1:
                return stack[0]
            elif len(stack) == 0:
                return "<EMPTY>"
            else:
                # 多个元素：用逗号连接
                return f"<INCOMPLETE: {', '.join(stack)}>"
                
        except Exception as e:
            return f"<ERROR: {e}>"
    
    def validate(self, formula: List[int]) -> bool:
        """
        验证因子表达式是否语法正确
        
        使用模拟执行（不实际计算）来验证。
        
        Args:
            formula: token 序列
            
        Returns:
            True 如果表达式语法正确
        """
        stack_depth = 0
        
        try:
            for token in formula:
                token = int(token)
                
                if self.vocab.is_feature(token):
                    stack_depth += 1
                elif self.vocab.is_operator(token):
                    arity = self.vocab.get_operator_arity(token)
                    if stack_depth < arity:
                        return False
                    stack_depth -= arity
                    stack_depth += 1  # 操作结果
                else:
                    return False
            
            return stack_depth == 1
            
        except Exception:
            return False
    
    def get_required_features(self, formula: List[int]) -> List[int]:
        """
        获取表达式中使用的特征列表
        
        Args:
            formula: token 序列
            
        Returns:
            使用的特征 token 列表（去重）
        """
        features = []
        for token in formula:
            token = int(token)
            if self.vocab.is_feature(token) and token not in features:
                features.append(token)
        return features
