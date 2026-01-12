"""
因子操作符定义

定义因子表达式中可用的操作符，包括：
- 算术运算：ADD, SUB, MUL, DIV
- 一元运算：NEG, ABS, SIGN
- 时序运算：DELAY, DELTA, MA, STD
- 条件运算：GATE, MAX, MIN

References:
- AlphaGPT upstream/model_core/ops.py
"""

import torch
from typing import Callable, Tuple, List


# ============================================================================
# 时序操作函数（优化版本，支持 JIT 编译）
# ============================================================================

def ts_delay(x: torch.Tensor, d: int = 1) -> torch.Tensor:
    """
    时序延迟：将序列向右移动 d 步
    
    Args:
        x: [batch, time_steps] 输入张量
        d: 延迟步数
        
    Returns:
        延迟后的张量，前 d 个位置填充 0
    """
    if d == 0:
        return x
    if d < 0:
        raise ValueError(f"Delay must be non-negative, got {d}")
    
    batch_size = x.shape[0]
    pad = torch.zeros((batch_size, d), device=x.device, dtype=x.dtype)
    return torch.cat([pad, x[:, :-d]], dim=1)


def ts_delta(x: torch.Tensor, d: int = 1) -> torch.Tensor:
    """
    时序差分：计算 x[t] - x[t-d]
    
    Args:
        x: [batch, time_steps] 输入张量
        d: 差分步数
        
    Returns:
        差分后的张量
    """
    return x - ts_delay(x, d)


def ts_mean(x: torch.Tensor, window: int = 5) -> torch.Tensor:
    """
    滑动平均
    
    Args:
        x: [batch, time_steps] 输入张量
        window: 窗口大小
        
    Returns:
        滑动平均后的张量
    """
    if window <= 0:
        raise ValueError(f"Window must be positive, got {window}")
    
    # 使用 unfold 实现滑动窗口
    batch_size, time_steps = x.shape
    
    # Padding
    pad = torch.zeros((batch_size, window - 1), device=x.device, dtype=x.dtype)
    x_padded = torch.cat([pad, x], dim=1)
    
    # 滑动窗口平均
    result = x_padded.unfold(1, window, 1).mean(dim=-1)
    return result


def ts_std(x: torch.Tensor, window: int = 5) -> torch.Tensor:
    """
    滑动标准差
    
    Args:
        x: [batch, time_steps] 输入张量
        window: 窗口大小
        
    Returns:
        滑动标准差后的张量
    """
    if window <= 0:
        raise ValueError(f"Window must be positive, got {window}")
    
    batch_size, time_steps = x.shape
    
    # Padding
    pad = torch.zeros((batch_size, window - 1), device=x.device, dtype=x.dtype)
    x_padded = torch.cat([pad, x], dim=1)
    
    # 滑动窗口标准差
    result = x_padded.unfold(1, window, 1).std(dim=-1)
    return result


def _op_gate(condition: torch.Tensor, x: torch.Tensor, y: torch.Tensor) -> torch.Tensor:
    """
    条件选择：condition > 0 时返回 x，否则返回 y
    
    类似于 torch.where(condition > 0, x, y)
    """
    mask = (condition > 0).float()
    return mask * x + (1.0 - mask) * y


def _op_jump(x: torch.Tensor) -> torch.Tensor:
    """
    跳跃检测：返回超过 3 sigma 的异常值
    
    用于检测价格跳跃/异常波动
    """
    mean = x.mean(dim=1, keepdim=True)
    std = x.std(dim=1, keepdim=True) + 1e-6
    z = (x - mean) / std
    return torch.relu(z - 3.0)


def _op_decay(x: torch.Tensor) -> torch.Tensor:
    """
    衰减加权：x + 0.8*x[-1] + 0.6*x[-2]
    
    给近期数据更高权重
    """
    return x + 0.8 * ts_delay(x, 1) + 0.6 * ts_delay(x, 2)


def _op_max3(x: torch.Tensor) -> torch.Tensor:
    """
    3 期最大值
    """
    return torch.max(x, torch.max(ts_delay(x, 1), ts_delay(x, 2)))


# ============================================================================
# 操作符配置
# ============================================================================

# 操作符配置格式：(name, function, arity)
# - name: 操作符名称
# - function: 操作符函数
# - arity: 参数数量（1=一元，2=二元，3=三元）

OPS_CONFIG: List[Tuple[str, Callable, int]] = [
    # 二元算术运算
    ('ADD', lambda x, y: x + y, 2),
    ('SUB', lambda x, y: x - y, 2),
    ('MUL', lambda x, y: x * y, 2),
    ('DIV', lambda x, y: x / (y + 1e-6), 2),  # 安全除法
    
    # 一元运算
    ('NEG', lambda x: -x, 1),
    ('ABS', torch.abs, 1),
    ('SIGN', torch.sign, 1),
    
    # 条件运算
    ('GATE', _op_gate, 3),  # 条件选择
    ('MAX', lambda x, y: torch.max(x, y), 2),
    ('MIN', lambda x, y: torch.min(x, y), 2),
    
    # 时序运算
    ('DELAY1', lambda x: ts_delay(x, 1), 1),
    ('DELAY5', lambda x: ts_delay(x, 5), 1),
    ('DELTA1', lambda x: ts_delta(x, 1), 1),
    ('DELTA5', lambda x: ts_delta(x, 5), 1),
    ('MA5', lambda x: ts_mean(x, 5), 1),
    ('MA10', lambda x: ts_mean(x, 10), 1),
    ('STD5', lambda x: ts_std(x, 5), 1),
    ('STD10', lambda x: ts_std(x, 10), 1),
    
    # 特殊运算
    ('JUMP', _op_jump, 1),
    ('DECAY', _op_decay, 1),
    ('MAX3', _op_max3, 1),
]


def get_op_names() -> List[str]:
    """获取所有操作符名称"""
    return [op[0] for op in OPS_CONFIG]


def get_op_by_name(name: str) -> Tuple[Callable, int]:
    """
    根据名称获取操作符函数和参数数量
    
    Args:
        name: 操作符名称
        
    Returns:
        (function, arity) 元组
        
    Raises:
        KeyError: 如果操作符不存在
    """
    for op_name, func, arity in OPS_CONFIG:
        if op_name == name:
            return func, arity
    raise KeyError(f"Unknown operator: {name}")


def get_num_ops() -> int:
    """获取操作符数量"""
    return len(OPS_CONFIG)
