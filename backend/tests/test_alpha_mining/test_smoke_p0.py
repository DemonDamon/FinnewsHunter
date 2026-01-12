"""
P0 冒烟测试 - Alpha Mining 核心机制

测试覆盖：
- F02: 配置模块
- F03-F04: 操作符和时序函数
- F05: 词汇表
- F06-F07: FactorVM 执行和解码
- F08-F09: AlphaGenerator 模型和生成
- F10: AlphaTrainer 训练
- F11: 模拟数据生成
"""

import pytest
import torch
import sys
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from app.alpha_mining.config import AlphaMiningConfig, DEFAULT_CONFIG
from app.alpha_mining.dsl.ops import (
    OPS_CONFIG, ts_delay, ts_delta, ts_mean, ts_std, get_op_names
)
from app.alpha_mining.dsl.vocab import FactorVocab, FEATURES, DEFAULT_VOCAB
from app.alpha_mining.vm.factor_vm import FactorVM
from app.alpha_mining.model.alpha_generator import AlphaGenerator
from app.alpha_mining.model.trainer import AlphaTrainer
from app.alpha_mining.utils import generate_mock_data


# ============================================================================
# F02: 配置模块测试
# ============================================================================

class TestConfig:
    """配置模块测试"""
    
    def test_default_config_exists(self):
        """测试默认配置存在"""
        assert DEFAULT_CONFIG is not None
        assert isinstance(DEFAULT_CONFIG, AlphaMiningConfig)
    
    def test_config_device(self):
        """测试设备配置"""
        config = AlphaMiningConfig()
        assert config.device in ["cpu", "cuda", "mps"]
        assert isinstance(config.torch_device, torch.device)
    
    def test_config_features(self):
        """测试特征配置"""
        config = AlphaMiningConfig()
        assert len(config.market_features) >= 4
        assert len(config.all_features) >= 4
        assert config.num_features > 0


# ============================================================================
# F03-F04: 操作符测试
# ============================================================================

class TestOps:
    """操作符测试"""
    
    @pytest.fixture
    def sample_tensor(self):
        """创建测试张量"""
        return torch.randn(10, 100)  # [batch=10, time=100]
    
    def test_ts_delay(self, sample_tensor):
        """测试时序延迟"""
        result = ts_delay(sample_tensor, d=1)
        assert result.shape == sample_tensor.shape
        # 第一列应该是 0
        assert (result[:, 0] == 0).all()
        # 后续应该是原始值的延迟
        assert torch.allclose(result[:, 1:], sample_tensor[:, :-1])
    
    def test_ts_delta(self, sample_tensor):
        """测试时序差分"""
        result = ts_delta(sample_tensor, d=1)
        assert result.shape == sample_tensor.shape
        # 差分 = x[t] - x[t-1]
        expected = sample_tensor - ts_delay(sample_tensor, 1)
        assert torch.allclose(result, expected)
    
    def test_ts_mean(self, sample_tensor):
        """测试滑动平均"""
        result = ts_mean(sample_tensor, window=5)
        assert result.shape == sample_tensor.shape
        # 值应该在合理范围内
        assert not torch.isnan(result).any()
    
    def test_ts_std(self, sample_tensor):
        """测试滑动标准差"""
        result = ts_std(sample_tensor, window=5)
        assert result.shape == sample_tensor.shape
        # 标准差应该非负
        assert (result >= 0).all()
    
    def test_ops_config_complete(self):
        """测试操作符配置完整性"""
        assert len(OPS_CONFIG) >= 10
        for name, func, arity in OPS_CONFIG:
            assert isinstance(name, str)
            assert callable(func)
            assert arity in [1, 2, 3]
    
    def test_all_ops_executable(self, sample_tensor):
        """测试所有操作符可执行"""
        y = torch.randn_like(sample_tensor)
        z = torch.randn_like(sample_tensor)
        
        for name, func, arity in OPS_CONFIG:
            try:
                if arity == 1:
                    result = func(sample_tensor)
                elif arity == 2:
                    result = func(sample_tensor, y)
                elif arity == 3:
                    result = func(sample_tensor, y, z)
                
                assert result.shape == sample_tensor.shape, f"{name} shape mismatch"
                assert not torch.isnan(result).all(), f"{name} all NaN"
            except Exception as e:
                pytest.fail(f"Operator {name} failed: {e}")


# ============================================================================
# F05: 词汇表测试
# ============================================================================

class TestVocab:
    """词汇表测试"""
    
    def test_default_vocab_exists(self):
        """测试默认词汇表存在"""
        assert DEFAULT_VOCAB is not None
        assert DEFAULT_VOCAB.vocab_size > 0
    
    def test_vocab_token_mapping(self):
        """测试 token 映射"""
        vocab = FactorVocab()
        
        # 测试特征映射
        assert vocab.token_to_name(0) == FEATURES[0]
        assert vocab.name_to_token(FEATURES[0]) == 0
        
        # 测试操作符映射
        op_names = get_op_names()
        first_op_token = vocab.num_features
        assert vocab.token_to_name(first_op_token) == op_names[0]
    
    def test_vocab_is_feature_operator(self):
        """测试特征/操作符判断"""
        vocab = FactorVocab()
        
        # 特征 token
        assert vocab.is_feature(0)
        assert not vocab.is_operator(0)
        
        # 操作符 token
        op_token = vocab.num_features
        assert vocab.is_operator(op_token)
        assert not vocab.is_feature(op_token)
    
    def test_vocab_get_operator_arity(self):
        """测试获取操作符参数数量"""
        vocab = FactorVocab()
        
        for i, (name, func, arity) in enumerate(OPS_CONFIG):
            token = vocab.num_features + i
            assert vocab.get_operator_arity(token) == arity


# ============================================================================
# F06-F07: FactorVM 测试
# ============================================================================

class TestFactorVM:
    """因子执行器测试"""
    
    @pytest.fixture
    def vm(self):
        """创建 VM 实例"""
        return FactorVM()
    
    @pytest.fixture
    def features(self):
        """创建测试特征"""
        # [batch=10, num_features=6, time=100]
        return torch.randn(10, 6, 100)
    
    def test_vm_execute_simple(self, vm, features):
        """测试简单表达式执行"""
        # 只取第一个特征
        formula = [0]  # RET
        result = vm.execute(formula, features)
        
        assert result is not None
        assert result.shape == (10, 100)
        assert torch.allclose(result, features[:, 0, :])
    
    def test_vm_execute_binary_op(self, vm, features):
        """测试二元操作"""
        vocab = vm.vocab
        add_token = vocab.name_to_token("ADD")
        
        # ADD(RET, VOL) = features[0] + features[1]
        formula = [0, 1, add_token]
        result = vm.execute(formula, features)
        
        assert result is not None
        expected = features[:, 0, :] + features[:, 1, :]
        assert torch.allclose(result, expected)
    
    def test_vm_execute_unary_op(self, vm, features):
        """测试一元操作"""
        vocab = vm.vocab
        neg_token = vocab.name_to_token("NEG")
        
        # NEG(RET) = -features[0]
        formula = [0, neg_token]
        result = vm.execute(formula, features)
        
        assert result is not None
        expected = -features[:, 0, :]
        assert torch.allclose(result, expected)
    
    def test_vm_execute_invalid_formula(self, vm, features):
        """测试无效公式"""
        vocab = vm.vocab
        add_token = vocab.name_to_token("ADD")
        
        # 只有一个参数的 ADD（无效）
        formula = [0, add_token]
        result = vm.execute(formula, features)
        
        assert result is None  # 应该返回 None
    
    def test_vm_decode_simple(self, vm):
        """测试表达式解码"""
        # RET
        assert "RET" in vm.decode([0])
        
        # ADD(RET, VOL)
        vocab = vm.vocab
        add_token = vocab.name_to_token("ADD")
        decoded = vm.decode([0, 1, add_token])
        assert "ADD" in decoded
        assert "RET" in decoded
    
    def test_vm_validate(self, vm):
        """测试表达式验证"""
        vocab = vm.vocab
        add_token = vocab.name_to_token("ADD")
        neg_token = vocab.name_to_token("NEG")
        
        # 有效公式
        assert vm.validate([0])  # RET
        assert vm.validate([0, neg_token])  # NEG(RET)
        assert vm.validate([0, 1, add_token])  # ADD(RET, VOL)
        
        # 无效公式
        assert not vm.validate([add_token])  # ADD without args
        assert not vm.validate([0, 1])  # Two features, no op


# ============================================================================
# F08-F09: AlphaGenerator 测试
# ============================================================================

class TestAlphaGenerator:
    """因子生成器测试"""
    
    @pytest.fixture
    def generator(self):
        """创建生成器实例"""
        config = AlphaMiningConfig(d_model=32, num_layers=1)  # 小模型用于测试
        return AlphaGenerator(config=config)
    
    def test_generator_init(self, generator):
        """测试生成器初始化"""
        assert generator.vocab_size > 0
        assert generator.d_model > 0
    
    def test_generator_forward(self, generator):
        """测试前向传播"""
        batch_size = 4
        seq_len = 5
        tokens = torch.zeros((batch_size, seq_len), dtype=torch.long)
        
        logits, value = generator(tokens)
        
        assert logits.shape == (batch_size, generator.vocab_size)
        assert value.shape == (batch_size, 1)
    
    def test_generator_generate(self, generator):
        """测试生成功能"""
        batch_size = 8
        max_len = 6
        
        formulas, log_probs = generator.generate(
            batch_size=batch_size,
            max_len=max_len
        )
        
        assert len(formulas) == batch_size
        assert all(len(f) == max_len for f in formulas)
        assert len(log_probs) == batch_size
    
    def test_generator_generate_with_training(self, generator):
        """测试训练模式生成"""
        batch_size = 4
        max_len = 6
        
        sequences, log_probs, values = generator.generate_with_training(
            batch_size=batch_size,
            max_len=max_len
        )
        
        assert sequences.shape == (batch_size, max_len)
        assert len(log_probs) == max_len
        assert len(values) == max_len


# ============================================================================
# F10: AlphaTrainer 测试
# ============================================================================

class TestAlphaTrainer:
    """训练器测试"""
    
    @pytest.fixture
    def trainer(self):
        """创建训练器实例"""
        config = AlphaMiningConfig(
            d_model=32,
            num_layers=1,
            batch_size=16,
            max_seq_len=6
        )
        return AlphaTrainer(config=config)
    
    @pytest.fixture
    def mock_data(self):
        """创建模拟数据"""
        return generate_mock_data(
            num_samples=20,
            num_features=6,
            time_steps=50,
            seed=42
        )
    
    def test_trainer_init(self, trainer):
        """测试训练器初始化"""
        assert trainer.generator is not None
        assert trainer.vm is not None
        assert trainer.best_score == -float('inf')
    
    def test_trainer_train_step(self, trainer, mock_data):
        """测试单步训练"""
        features, returns = mock_data
        
        metrics = trainer.train_step(features, returns)
        
        assert "loss" in metrics
        assert "avg_reward" in metrics
        assert "valid_ratio" in metrics
        assert trainer.step_count == 1
    
    def test_trainer_short_training(self, trainer, mock_data):
        """测试短训练（3步）"""
        features, returns = mock_data
        
        result = trainer.train(
            features, returns,
            num_steps=3,
            progress_bar=False
        )
        
        assert result["total_steps"] == 3
        assert "best_score" in result
        assert len(trainer.training_history) == 3


# ============================================================================
# F11: 模拟数据测试
# ============================================================================

class TestMockData:
    """模拟数据生成测试"""
    
    def test_generate_mock_data_shape(self):
        """测试模拟数据形状"""
        features, returns = generate_mock_data(
            num_samples=50,
            num_features=6,
            time_steps=100
        )
        
        assert features.shape == (50, 6, 100)
        assert returns.shape == (50, 100)
    
    def test_generate_mock_data_no_nan(self):
        """测试模拟数据无 NaN"""
        features, returns = generate_mock_data()
        
        assert not torch.isnan(features).any()
        assert not torch.isnan(returns).any()
    
    def test_generate_mock_data_reproducible(self):
        """测试模拟数据可复现"""
        f1, r1 = generate_mock_data(seed=42)
        f2, r2 = generate_mock_data(seed=42)
        
        assert torch.allclose(f1, f2)
        assert torch.allclose(r1, r2)


# ============================================================================
# 端到端冒烟测试
# ============================================================================

class TestEndToEnd:
    """端到端测试"""
    
    def test_full_pipeline_smoke(self):
        """完整流程冒烟测试"""
        # 1. 创建配置
        config = AlphaMiningConfig(
            d_model=32,
            num_layers=1,
            batch_size=8,
            max_seq_len=6
        )
        
        # 2. 创建组件
        vocab = FactorVocab()
        vm = FactorVM(vocab=vocab)
        generator = AlphaGenerator(vocab=vocab, config=config)
        trainer = AlphaTrainer(generator=generator, vocab=vocab, config=config)
        
        # 3. 生成模拟数据
        features, returns = generate_mock_data(
            num_samples=10,
            num_features=6,
            time_steps=30,
            seed=42
        )
        
        # 4. 生成因子表达式
        formulas, _ = generator.generate(batch_size=4, max_len=5)
        
        # 5. 执行表达式
        valid_count = 0
        for formula in formulas:
            result = vm.execute(formula, features)
            if result is not None:
                valid_count += 1
                decoded = vm.decode(formula)
                assert isinstance(decoded, str)
        
        # 6. 训练（1步）
        metrics = trainer.train_step(features, returns)
        assert metrics["step"] == 1
        
        print(f"\n✅ End-to-end smoke test passed!")
        print(f"   - Valid formulas: {valid_count}/{len(formulas)}")
        print(f"   - Avg reward: {metrics['avg_reward']:.4f}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
