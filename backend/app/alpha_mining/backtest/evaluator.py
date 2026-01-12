"""
因子回测评估器

评估因子的预测能力和交易表现。

评估指标：
- Sortino Ratio: 风险调整收益（只考虑下行风险）
- Sharpe Ratio: 风险调整收益
- IC: 信息系数（因子与收益的相关性）
- Rank IC: 排名信息系数
- Turnover: 换手率
- Max Drawdown: 最大回撤
"""

import torch
from typing import Dict, Optional, List, Tuple
import numpy as np
import logging

from ..config import AlphaMiningConfig, DEFAULT_CONFIG

logger = logging.getLogger(__name__)


class FactorEvaluator:
    """
    因子回测评估器
    
    评估因子表达式的有效性和收益表现。
    
    Args:
        config: 配置实例
        cost_rate: 交易成本率
        signal_threshold: 信号阈值（用于生成持仓）
        
    Example:
        evaluator = FactorEvaluator()
        metrics = evaluator.evaluate(factor, returns)
    """
    
    def __init__(
        self,
        config: Optional[AlphaMiningConfig] = None,
        cost_rate: Optional[float] = None,
        signal_threshold: Optional[float] = None
    ):
        self.config = config or DEFAULT_CONFIG
        self.cost_rate = cost_rate or self.config.cost_rate
        self.signal_threshold = signal_threshold or self.config.signal_threshold
        
        # 年化系数（假设 252 个交易日）
        self.annualize_factor = np.sqrt(252)
        
        logger.info(
            f"FactorEvaluator initialized: "
            f"cost_rate={self.cost_rate}, threshold={self.signal_threshold}"
        )
    
    def evaluate(
        self,
        factor: torch.Tensor,
        returns: torch.Tensor,
        benchmark: Optional[torch.Tensor] = None
    ) -> Dict[str, float]:
        """
        综合评估因子
        
        Args:
            factor: 因子值 [batch, time_steps] 或 [time_steps]
            returns: 收益率 [batch, time_steps] 或 [time_steps]
            benchmark: 基准收益率（可选）
            
        Returns:
            评估指标字典
        """
        # 确保是 2D
        if factor.dim() == 1:
            factor = factor.unsqueeze(0)
        if returns.dim() == 1:
            returns = returns.unsqueeze(0)
        
        # 对每个样本计算指标，然后平均
        metrics_list = []
        for i in range(factor.size(0)):
            f = factor[i]
            r = returns[i]
            b = benchmark[i] if benchmark is not None else None
            
            m = self._evaluate_single(f, r, b)
            metrics_list.append(m)
        
        # 聚合指标
        result = {}
        for key in metrics_list[0].keys():
            values = [m[key] for m in metrics_list]
            result[key] = np.mean(values)
            result[f"{key}_std"] = np.std(values)
        
        return result
    
    def _evaluate_single(
        self,
        factor: torch.Tensor,
        returns: torch.Tensor,
        benchmark: Optional[torch.Tensor] = None
    ) -> Dict[str, float]:
        """评估单个样本"""
        # 转换为 numpy
        factor_np = factor.detach().cpu().numpy()
        returns_np = returns.detach().cpu().numpy()
        
        # 生成信号和持仓
        signal = self._factor_to_signal(factor_np)
        position = self._signal_to_position(signal)
        
        # 计算策略收益
        strategy_returns = position[:-1] * returns_np[1:]
        
        # 计算交易成本
        turnover = np.abs(np.diff(position)).mean()
        net_returns = strategy_returns - turnover * self.cost_rate
        
        # 计算各指标
        metrics = {
            "sortino_ratio": self._calc_sortino(net_returns),
            "sharpe_ratio": self._calc_sharpe(net_returns),
            "ic": self._calc_ic(factor_np, returns_np),
            "rank_ic": self._calc_rank_ic(factor_np, returns_np),
            "turnover": turnover,
            "max_drawdown": self._calc_max_drawdown(net_returns),
            "total_return": np.sum(net_returns),
            "win_rate": np.mean(net_returns > 0),
            "avg_return": np.mean(net_returns),
        }
        
        # 相对基准的超额收益
        if benchmark is not None:
            benchmark_np = benchmark.detach().cpu().numpy()
            excess_returns = net_returns - benchmark_np[1:]
            metrics["excess_return"] = np.sum(excess_returns)
            metrics["information_ratio"] = self._calc_sharpe(excess_returns)
        
        return metrics
    
    def _factor_to_signal(self, factor: np.ndarray) -> np.ndarray:
        """因子值转换为信号（-1 到 1）"""
        # 使用 Z-score 标准化
        mean = np.mean(factor)
        std = np.std(factor) + 1e-8
        z_score = (factor - mean) / std
        
        # Sigmoid 映射到 (-1, 1)
        signal = 2 / (1 + np.exp(-z_score)) - 1
        
        return signal
    
    def _signal_to_position(self, signal: np.ndarray) -> np.ndarray:
        """信号转换为持仓"""
        position = np.zeros_like(signal)
        
        # 信号大于阈值时做多
        position[signal > self.signal_threshold] = 1.0
        # 信号小于负阈值时做空
        position[signal < -self.signal_threshold] = -1.0
        # 中间区域不持仓
        
        return position
    
    def _calc_sortino(self, returns: np.ndarray) -> float:
        """
        计算 Sortino Ratio
        
        只考虑下行风险（负收益的标准差）
        """
        mean_return = np.mean(returns)
        downside = returns[returns < 0]
        
        if len(downside) == 0:
            return float('inf') if mean_return > 0 else 0.0
        
        downside_std = np.std(downside) + 1e-8
        sortino = mean_return / downside_std * self.annualize_factor
        
        return float(sortino)
    
    def _calc_sharpe(self, returns: np.ndarray) -> float:
        """计算 Sharpe Ratio"""
        mean_return = np.mean(returns)
        std_return = np.std(returns) + 1e-8
        
        sharpe = mean_return / std_return * self.annualize_factor
        return float(sharpe)
    
    def _calc_ic(self, factor: np.ndarray, returns: np.ndarray) -> float:
        """
        计算 IC (Information Coefficient)
        
        因子值与下期收益的 Pearson 相关系数
        """
        # 对齐：factor[t] 预测 returns[t+1]
        factor_lag = factor[:-1]
        returns_lead = returns[1:]
        
        # Pearson 相关
        corr = np.corrcoef(factor_lag, returns_lead)[0, 1]
        
        return float(corr) if not np.isnan(corr) else 0.0
    
    def _calc_rank_ic(self, factor: np.ndarray, returns: np.ndarray) -> float:
        """
        计算 Rank IC
        
        因子排名与收益排名的 Spearman 相关系数
        """
        from scipy.stats import spearmanr
        
        factor_lag = factor[:-1]
        returns_lead = returns[1:]
        
        try:
            corr, _ = spearmanr(factor_lag, returns_lead)
            return float(corr) if not np.isnan(corr) else 0.0
        except Exception:
            return 0.0
    
    def _calc_max_drawdown(self, returns: np.ndarray) -> float:
        """计算最大回撤"""
        cumulative = np.cumsum(returns)
        running_max = np.maximum.accumulate(cumulative)
        drawdown = running_max - cumulative
        
        max_dd = np.max(drawdown)
        return float(max_dd)
    
    def get_reward(
        self,
        factor: torch.Tensor,
        returns: torch.Tensor
    ) -> float:
        """
        获取强化学习奖励
        
        使用 Sortino Ratio 作为奖励信号。
        
        Args:
            factor: 因子值
            returns: 收益率
            
        Returns:
            奖励值
        """
        metrics = self.evaluate(factor, returns)
        
        # 主要使用 Sortino Ratio
        reward = metrics["sortino_ratio"]
        
        # 惩罚过高的换手率
        if metrics["turnover"] > 0.5:
            reward -= (metrics["turnover"] - 0.5) * 2
        
        # 惩罚过大的最大回撤
        if metrics["max_drawdown"] > 0.2:
            reward -= (metrics["max_drawdown"] - 0.2) * 5
        
        return float(reward)
    
    def compare_factors(
        self,
        factors: List[torch.Tensor],
        returns: torch.Tensor,
        factor_names: Optional[List[str]] = None
    ) -> Dict[str, Dict[str, float]]:
        """
        比较多个因子的表现
        
        Args:
            factors: 因子列表
            returns: 收益率
            factor_names: 因子名称列表
            
        Returns:
            {factor_name: metrics_dict}
        """
        if factor_names is None:
            factor_names = [f"factor_{i}" for i in range(len(factors))]
        
        results = {}
        for name, factor in zip(factor_names, factors):
            results[name] = self.evaluate(factor, returns)
        
        return results
    
    def rank_factors(
        self,
        factors: List[torch.Tensor],
        returns: torch.Tensor,
        metric: str = "sortino_ratio"
    ) -> List[Tuple[int, float]]:
        """
        对因子按指定指标排名
        
        Args:
            factors: 因子列表
            returns: 收益率
            metric: 排名指标
            
        Returns:
            [(index, score), ...] 按 score 降序排列
        """
        scores = []
        for i, factor in enumerate(factors):
            metrics = self.evaluate(factor, returns)
            scores.append((i, metrics.get(metric, 0)))
        
        # 降序排列
        scores.sort(key=lambda x: x[1], reverse=True)
        
        return scores
