"""
因子挖掘 RL 训练器

使用 REINFORCE 算法训练 AlphaGenerator，以回测收益为奖励信号。

训练流程：
1. 生成因子表达式
2. 执行表达式得到因子值
3. 回测评估因子有效性（计算奖励）
4. 策略梯度更新

References:
- AlphaGPT upstream/model_core/engine.py
"""

import torch
from typing import Optional, List, Dict, Any, Callable
from tqdm import tqdm
import logging
import json
from pathlib import Path

from ..config import AlphaMiningConfig, DEFAULT_CONFIG
from ..dsl.vocab import FactorVocab, DEFAULT_VOCAB
from ..vm.factor_vm import FactorVM
from .alpha_generator import AlphaGenerator

logger = logging.getLogger(__name__)


class AlphaTrainer:
    """
    因子挖掘 RL 训练器
    
    使用 REINFORCE 算法训练 AlphaGenerator。
    
    Args:
        generator: 因子生成模型
        vocab: 词汇表
        config: 配置
        evaluator: 因子评估函数，接收 (factor, returns) 返回 score
    """
    
    def __init__(
        self,
        generator: Optional[AlphaGenerator] = None,
        vocab: Optional[FactorVocab] = None,
        config: Optional[AlphaMiningConfig] = None,
        evaluator: Optional[Callable[[torch.Tensor, torch.Tensor], float]] = None
    ):
        self.config = config or DEFAULT_CONFIG
        self.vocab = vocab or DEFAULT_VOCAB
        self.generator = generator or AlphaGenerator(vocab=self.vocab, config=self.config)
        self.vm = FactorVM(vocab=self.vocab)
        
        # 默认评估器（简单 Sharpe-like）
        self.evaluator = evaluator or self._default_evaluator
        
        # 优化器
        self.optimizer = torch.optim.AdamW(
            self.generator.parameters(),
            lr=self.config.lr
        )
        
        # 训练状态
        self.best_score = -float('inf')
        self.best_formula: Optional[List[int]] = None
        self.best_formula_str: Optional[str] = None
        self.training_history: List[Dict[str, Any]] = []
        self.step_count = 0
        
        # 移动到指定设备
        self.device = self.config.torch_device
        self.generator.to(self.device)
        
        logger.info(f"AlphaTrainer initialized on device: {self.device}")
    
    def _default_evaluator(self, factor: torch.Tensor, returns: torch.Tensor) -> float:
        """
        默认因子评估器（简化版 Sharpe-like）
        
        Args:
            factor: 因子值 [batch, time_steps]
            returns: 收益率 [batch, time_steps]
            
        Returns:
            评分（越高越好）
        """
        # 因子值作为信号（sigmoid 归一化）
        signal = torch.sigmoid(factor)
        
        # 简单策略：signal > threshold 时持仓
        threshold = self.config.signal_threshold
        position = (signal > threshold).float()
        
        # 计算收益
        pnl = position * returns
        
        # Sharpe-like ratio（简化）
        mean_pnl = pnl.mean()
        std_pnl = pnl.std() + 1e-6
        
        score = (mean_pnl / std_pnl).item()
        return score
    
    def train_step(
        self,
        features: torch.Tensor,
        returns: torch.Tensor
    ) -> Dict[str, Any]:
        """
        单步训练
        
        Args:
            features: 特征张量 [batch, num_features, time_steps]
            returns: 收益率张量 [batch, time_steps]
            
        Returns:
            训练指标字典
        """
        self.generator.train()
        batch_size = self.config.batch_size
        
        # 1. 生成因子表达式
        sequences, log_probs_list, _ = self.generator.generate_with_training(
            batch_size=batch_size,
            device=self.device
        )
        
        # 2. 执行并评估每个公式
        rewards = torch.zeros(batch_size, device=self.device)
        valid_count = 0
        
        for i in range(batch_size):
            formula = sequences[i].tolist()
            
            # 执行因子表达式
            factor = self.vm.execute(formula, features)
            
            if factor is None:
                # 无效公式
                rewards[i] = self.config.invalid_formula_reward
                continue
            
            # 检查是否为常量因子
            if factor.std() < self.config.constant_threshold:
                rewards[i] = self.config.constant_factor_reward
                continue
            
            # 评估因子
            try:
                score = self.evaluator(factor, returns)
                rewards[i] = score
                valid_count += 1
                
                # 更新最优
                if score > self.best_score:
                    self.best_score = score
                    self.best_formula = formula
                    self.best_formula_str = self.vm.decode(formula)
                    logger.info(
                        f"[Step {self.step_count}] New best: "
                        f"score={score:.4f}, formula={self.best_formula_str}"
                    )
            except Exception as e:
                logger.warning(f"Evaluation error: {e}")
                rewards[i] = self.config.invalid_formula_reward
        
        # 3. 计算 advantage（归一化）
        adv = (rewards - rewards.mean()) / (rewards.std() + 1e-5)
        
        # 4. 策略梯度 loss
        loss = torch.zeros(1, device=self.device)
        for t, log_prob in enumerate(log_probs_list):
            loss = loss - (log_prob * adv).mean()
        
        # 5. 反向传播
        self.optimizer.zero_grad()
        loss.backward()
        
        # 梯度裁剪
        torch.nn.utils.clip_grad_norm_(self.generator.parameters(), max_norm=1.0)
        
        self.optimizer.step()
        
        # 6. 记录指标
        self.step_count += 1
        metrics = {
            "step": self.step_count,
            "loss": loss.item(),
            "avg_reward": rewards.mean().item(),
            "max_reward": rewards.max().item(),
            "min_reward": rewards.min().item(),
            "valid_ratio": valid_count / batch_size,
            "best_score": self.best_score,
            "best_formula": self.best_formula_str,
        }
        self.training_history.append(metrics)
        
        return metrics
    
    def train(
        self,
        features: torch.Tensor,
        returns: torch.Tensor,
        num_steps: Optional[int] = None,
        progress_bar: bool = True,
        step_callback: Optional[Callable[[Dict[str, Any]], None]] = None
    ) -> Dict[str, Any]:
        """
        完整训练循环
        
        Args:
            features: 特征张量 [num_samples, num_features, time_steps]
            returns: 收益率张量 [num_samples, time_steps]
            num_steps: 训练步数，默认使用 config.num_steps
            progress_bar: 是否显示进度条
            step_callback: 每步回调函数，接收 metrics 字典，用于 SSE 流式推送
            
        Returns:
            训练结果
        """
        num_steps = num_steps or self.config.num_steps
        
        logger.info(f"Starting training for {num_steps} steps...")
        
        # 确保数据在正确设备上
        features = features.to(self.device)
        returns = returns.to(self.device)
        
        iterator = range(num_steps)
        if progress_bar:
            iterator = tqdm(iterator, desc="Training")
        
        for step in iterator:
            metrics = self.train_step(features, returns)
            
            # 添加进度百分比
            metrics["progress"] = (step + 1) / num_steps * 100
            metrics["total_steps"] = num_steps
            
            if progress_bar:
                iterator.set_postfix({
                    "loss": f"{metrics['loss']:.4f}",
                    "avg_rew": f"{metrics['avg_reward']:.4f}",
                    "best": f"{metrics['best_score']:.4f}"
                })
            
            # 调用回调函数（用于 SSE 流式推送）
            if step_callback is not None:
                try:
                    step_callback(metrics)
                except Exception as e:
                    logger.warning(f"Step callback error: {e}")
            
            # 定期保存检查点
            if self.step_count % self.config.save_every_n_steps == 0:
                self._save_checkpoint()
        
        # 最终结果
        result = {
            "total_steps": self.step_count,
            "best_score": self.best_score,
            "best_formula": self.best_formula,
            "best_formula_str": self.best_formula_str,
            "final_metrics": self.training_history[-1] if self.training_history else None,
        }
        
        logger.info(f"Training complete. Best score: {self.best_score:.4f}")
        logger.info(f"Best formula: {self.best_formula_str}")
        
        return result
    
    def _save_checkpoint(self):
        """保存训练检查点"""
        checkpoint_dir = Path(self.config.checkpoint_dir)
        checkpoint_dir.mkdir(parents=True, exist_ok=True)
        
        # 保存模型
        model_path = checkpoint_dir / f"model_step_{self.step_count}.pt"
        self.generator.save(str(model_path))
        
        # 保存最优公式
        if self.best_formula:
            formula_path = checkpoint_dir / "best_formula.json"
            with open(formula_path, 'w') as f:
                json.dump({
                    "formula": self.best_formula,
                    "formula_str": self.best_formula_str,
                    "score": self.best_score,
                    "step": self.step_count
                }, f, indent=2)
    
    def get_best_formula(self) -> Optional[str]:
        """获取最优因子表达式字符串"""
        return self.best_formula_str
    
    def get_training_history(self) -> List[Dict[str, Any]]:
        """获取训练历史"""
        return self.training_history
