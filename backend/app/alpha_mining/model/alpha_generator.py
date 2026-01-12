"""
因子生成模型

基于 Transformer 的策略网络，用于生成因子表达式 token 序列。

架构：
- Token Embedding + Position Embedding
- Transformer Encoder（使用 causal mask）
- Policy Head（输出 token 概率）
- Value Head（估计状态价值，用于 Actor-Critic）

References:
- AlphaGPT upstream/model_core/alphagpt.py
"""

import torch
import torch.nn as nn
from torch.distributions import Categorical
from typing import Tuple, List, Optional
import logging

from ..config import AlphaMiningConfig, DEFAULT_CONFIG
from ..dsl.vocab import FactorVocab, DEFAULT_VOCAB

logger = logging.getLogger(__name__)


class AlphaGenerator(nn.Module):
    """
    因子生成器（Transformer 策略网络）
    
    使用 Transformer 架构生成因子表达式的 token 序列。
    
    Args:
        vocab: 词汇表实例
        config: 配置实例
        
    Example:
        generator = AlphaGenerator()
        tokens = torch.zeros((batch_size, 1), dtype=torch.long)
        logits, value = generator(tokens)
    """
    
    def __init__(
        self, 
        vocab: Optional[FactorVocab] = None,
        config: Optional[AlphaMiningConfig] = None
    ):
        super().__init__()
        
        self.vocab = vocab or DEFAULT_VOCAB
        self.config = config or DEFAULT_CONFIG
        
        # 模型参数
        self.vocab_size = self.vocab.vocab_size
        self.d_model = self.config.d_model
        self.max_seq_len = self.config.max_seq_len
        
        # Token Embedding
        self.token_emb = nn.Embedding(self.vocab_size, self.d_model)
        
        # Position Embedding（可学习的位置编码）
        self.pos_emb = nn.Parameter(
            torch.zeros(1, self.max_seq_len + 1, self.d_model)
        )
        
        # Transformer Encoder
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=self.d_model,
            nhead=self.config.nhead,
            dim_feedforward=self.d_model * 2,
            batch_first=True,
            dropout=0.1
        )
        self.transformer = nn.TransformerEncoder(
            encoder_layer,
            num_layers=self.config.num_layers
        )
        
        # Output heads
        self.ln_f = nn.LayerNorm(self.d_model)
        self.policy_head = nn.Linear(self.d_model, self.vocab_size)  # Actor
        self.value_head = nn.Linear(self.d_model, 1)  # Critic
        
        # 初始化权重
        self._init_weights()
        
        logger.info(
            f"AlphaGenerator initialized: vocab_size={self.vocab_size}, "
            f"d_model={self.d_model}, max_seq_len={self.max_seq_len}"
        )
    
    def _init_weights(self):
        """初始化模型权重"""
        # 使用 Xavier 初始化
        for module in self.modules():
            if isinstance(module, nn.Linear):
                nn.init.xavier_uniform_(module.weight)
                if module.bias is not None:
                    nn.init.zeros_(module.bias)
            elif isinstance(module, nn.Embedding):
                nn.init.normal_(module.weight, mean=0.0, std=0.02)
    
    def forward(
        self, 
        tokens: torch.Tensor
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        前向传播
        
        Args:
            tokens: 输入 token 序列 [batch, seq_len]
            
        Returns:
            logits: 下一个 token 的 logits [batch, vocab_size]
            value: 状态价值估计 [batch, 1]
        """
        batch_size, seq_len = tokens.size()
        device = tokens.device
        
        # Token + Position Embedding
        x = self.token_emb(tokens) + self.pos_emb[:, :seq_len, :]
        
        # Causal Mask（确保只能看到之前的 token）
        mask = nn.Transformer.generate_square_subsequent_mask(seq_len).to(device)
        
        # Transformer 编码
        x = self.transformer(x, mask=mask, is_causal=True)
        
        # Layer Norm
        x = self.ln_f(x)
        
        # 取最后一个位置的表示
        last_hidden = x[:, -1, :]  # [batch, d_model]
        
        # 输出 heads
        logits = self.policy_head(last_hidden)  # [batch, vocab_size]
        value = self.value_head(last_hidden)    # [batch, 1]
        
        return logits, value
    
    @torch.no_grad()
    def generate(
        self,
        batch_size: int = 1,
        max_len: Optional[int] = None,
        temperature: float = 1.0,
        device: Optional[torch.device] = None
    ) -> Tuple[List[List[int]], List[torch.Tensor]]:
        """
        批量生成因子表达式
        
        使用自回归采样生成 token 序列。
        
        Args:
            batch_size: 生成数量
            max_len: 最大长度，默认使用 config.max_seq_len
            temperature: 采样温度，越高越随机
            device: 设备，默认使用 config.device
            
        Returns:
            formulas: 生成的 token 序列列表
            log_probs_list: 每个序列的 log_prob 列表（用于策略梯度）
        """
        self.eval()
        
        max_len = max_len or self.config.max_seq_len
        device = device or self.config.torch_device
        
        # 初始化：以空 token 开始（使用 0）
        tokens = torch.zeros((batch_size, 1), dtype=torch.long, device=device)
        
        all_log_probs: List[List[torch.Tensor]] = [[] for _ in range(batch_size)]
        
        for step in range(max_len):
            # 前向传播
            logits, _ = self.forward(tokens)
            
            # 应用温度
            if temperature != 1.0:
                logits = logits / temperature
            
            # 采样
            dist = Categorical(logits=logits)
            action = dist.sample()  # [batch]
            
            # 记录 log_prob
            log_prob = dist.log_prob(action)  # [batch]
            for i in range(batch_size):
                all_log_probs[i].append(log_prob[i])
            
            # 拼接到序列
            tokens = torch.cat([tokens, action.unsqueeze(1)], dim=1)
        
        # 转换为列表格式
        formulas = tokens[:, 1:].tolist()  # 去掉初始的 0
        
        # 将 log_probs 转换为 tensor 列表
        log_probs_tensors = [torch.stack(lps) for lps in all_log_probs]
        
        return formulas, log_probs_tensors
    
    def generate_with_training(
        self,
        batch_size: int = 1,
        max_len: Optional[int] = None,
        device: Optional[torch.device] = None
    ) -> Tuple[torch.Tensor, List[torch.Tensor], List[torch.Tensor]]:
        """
        生成因子表达式（训练模式，保留梯度）
        
        Args:
            batch_size: 生成数量
            max_len: 最大长度
            device: 设备
            
        Returns:
            sequences: 生成的序列 [batch, seq_len]
            log_probs: 每步的 log_prob 列表
            values: 每步的 value 估计列表
        """
        self.train()
        
        max_len = max_len or self.config.max_seq_len
        device = device or self.config.torch_device
        
        # 初始化
        tokens = torch.zeros((batch_size, 1), dtype=torch.long, device=device)
        
        log_probs_list = []
        values_list = []
        tokens_list = []
        
        for step in range(max_len):
            # 前向传播
            logits, value = self.forward(tokens)
            
            # 采样
            dist = Categorical(logits=logits)
            action = dist.sample()
            
            # 记录
            log_probs_list.append(dist.log_prob(action))
            values_list.append(value.squeeze(-1))
            tokens_list.append(action)
            
            # 拼接
            tokens = torch.cat([tokens, action.unsqueeze(1)], dim=1)
        
        # 组装结果
        sequences = torch.stack(tokens_list, dim=1)  # [batch, max_len]
        
        return sequences, log_probs_list, values_list
    
    def save(self, path: str):
        """保存模型"""
        torch.save({
            'model_state_dict': self.state_dict(),
            'vocab_size': self.vocab_size,
            'd_model': self.d_model,
            'max_seq_len': self.max_seq_len,
        }, path)
        logger.info(f"Model saved to {path}")
    
    @classmethod
    def load(cls, path: str, vocab: Optional[FactorVocab] = None) -> 'AlphaGenerator':
        """加载模型"""
        checkpoint = torch.load(path, map_location='cpu')
        
        # 创建模型
        config = AlphaMiningConfig(
            d_model=checkpoint['d_model'],
            max_seq_len=checkpoint['max_seq_len']
        )
        model = cls(vocab=vocab, config=config)
        
        # 加载权重
        model.load_state_dict(checkpoint['model_state_dict'])
        logger.info(f"Model loaded from {path}")
        
        return model
