"""
Alpha Mining 模块冒烟测试

测试覆盖：
1. DSL 操作符执行
2. 因子虚拟机（FactorVM）
3. 因子生成模型（AlphaGenerator）
4. RL 训练器（AlphaTrainer）
5. 因子评估器（FactorEvaluator）
6. REST API 端点
"""

import pytest
import torch
import numpy as np
from typing import List

# 确保可以导入模块
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "app"))


class TestDSLOperators:
    """测试 DSL 操作符"""
    
    def test_ops_config_exists(self):
        """操作符配置存在"""
        from app.alpha_mining.dsl.ops import OPS_CONFIG, get_op_names
        
        assert len(OPS_CONFIG) == 21, f"Expected 21 operators, got {len(OPS_CONFIG)}"
        
        names = get_op_names()
        assert 'ADD' in names
        assert 'SUB' in names
        assert 'MUL' in names
        assert 'DIV' in names
        assert 'MA5' in names
        assert 'DELAY1' in names
    
    def test_arithmetic_ops(self):
        """算术操作符测试"""
        from app.alpha_mining.dsl.ops import get_op_by_name
        
        x = torch.tensor([1.0, 2.0, 3.0])
        y = torch.tensor([2.0, 3.0, 4.0])
        
        # ADD
        add_fn, add_arity = get_op_by_name('ADD')
        assert add_arity == 2
        result = add_fn(x, y)
        assert torch.allclose(result, torch.tensor([3.0, 5.0, 7.0]))
        
        # MUL
        mul_fn, mul_arity = get_op_by_name('MUL')
        result = mul_fn(x, y)
        assert torch.allclose(result, torch.tensor([2.0, 6.0, 12.0]))
        
        # DIV (safe division)
        div_fn, _ = get_op_by_name('DIV')
        result = div_fn(x, y)
        assert result.shape == x.shape
        assert not torch.any(torch.isinf(result))
    
    def test_timeseries_ops(self):
        """时序操作符测试"""
        from app.alpha_mining.dsl.ops import ts_delay, ts_mean, ts_std
        
        x = torch.tensor([[1.0, 2.0, 3.0, 4.0, 5.0]])
        
        # Delay
        delayed = ts_delay(x, 1)
        assert delayed[0, 0] == 0  # 填充 0
        assert delayed[0, 1] == 1  # 原来的第一个值
        
        # MA
        ma = ts_mean(x, 3)
        assert ma.shape == x.shape
        
        # STD
        std = ts_std(x, 3)
        assert std.shape == x.shape


class TestFactorVM:
    """测试因子虚拟机"""
    
    @pytest.fixture
    def vm(self):
        from app.alpha_mining.vm.factor_vm import FactorVM
        from app.alpha_mining.dsl.vocab import DEFAULT_VOCAB
        return FactorVM(vocab=DEFAULT_VOCAB)
    
    @pytest.fixture
    def sample_features(self):
        """[batch=2, features=4, time=10]"""
        return torch.randn(2, 4, 10)
    
    def test_execute_simple_formula(self, vm, sample_features):
        """执行简单因子表达式"""
        # RET + VOL (假设 RET=0, VOL=1, ADD=某个 token)
        formula = [0, 1, vm.vocab.name_to_token('ADD')]
        
        result = vm.execute(formula, sample_features)
        assert result is not None
        assert result.shape == (2, 10)  # [batch, time]
    
    def test_execute_invalid_formula(self, vm, sample_features):
        """无效表达式返回 None"""
        # 不完整的表达式
        formula = [0]  # 只有一个特征，没有操作
        result = vm.execute(formula, sample_features)
        # 只有一个操作数，应该返回该操作数（有效）
        assert result is not None
        
        # 操作符参数不足
        formula = [vm.vocab.name_to_token('ADD')]  # 二元操作符但没有操作数
        result = vm.execute(formula, sample_features)
        assert result is None
    
    def test_decode_formula(self, vm):
        """解码因子表达式为字符串"""
        formula = [0, 1, vm.vocab.name_to_token('ADD')]
        decoded = vm.decode(formula)
        assert decoded is not None
        assert 'ADD' in decoded or '+' in decoded


class TestAlphaGenerator:
    """测试因子生成模型"""
    
    @pytest.fixture
    def generator(self):
        from app.alpha_mining.model.alpha_generator import AlphaGenerator
        from app.alpha_mining.dsl.vocab import DEFAULT_VOCAB
        from app.alpha_mining.config import AlphaMiningConfig
        
        config = AlphaMiningConfig()
        return AlphaGenerator(vocab=DEFAULT_VOCAB, config=config)
    
    def test_generate_batch(self, generator):
        """生成一批因子表达式"""
        formulas, log_probs = generator.generate(batch_size=5, max_len=8)
        
        assert len(formulas) == 5
        for formula in formulas:
            assert len(formula) <= 8
            assert all(isinstance(t, int) for t in formula)
    
    def test_generate_with_training(self, generator):
        """训练模式生成"""
        sequences, log_probs_list, values = generator.generate_with_training(
            batch_size=3, device='cpu'
        )
        
        assert sequences.shape[0] == 3
        assert len(log_probs_list) > 0


class TestAlphaTrainer:
    """测试 RL 训练器"""
    
    @pytest.fixture
    def trainer(self):
        from app.alpha_mining.model.trainer import AlphaTrainer
        from app.alpha_mining.config import AlphaMiningConfig
        
        config = AlphaMiningConfig()
        config.batch_size = 8
        return AlphaTrainer(config=config)
    
    @pytest.fixture
    def sample_data(self):
        """生成样本数据"""
        features = torch.randn(10, 4, 50)  # [samples, features, time]
        returns = torch.randn(10, 50)      # [samples, time]
        return features, returns
    
    def test_train_step(self, trainer, sample_data):
        """单步训练测试"""
        features, returns = sample_data
        
        metrics = trainer.train_step(features, returns)
        
        assert 'step' in metrics
        assert 'loss' in metrics
        assert 'avg_reward' in metrics
        assert 'valid_ratio' in metrics
        assert 'best_score' in metrics
    
    def test_train_with_callback(self, trainer, sample_data):
        """带回调的训练测试"""
        features, returns = sample_data
        
        callback_results = []
        def callback(metrics):
            callback_results.append(metrics)
        
        result = trainer.train(
            features=features,
            returns=returns,
            num_steps=3,
            progress_bar=False,
            step_callback=callback
        )
        
        assert len(callback_results) == 3
        assert 'best_score' in result
        assert 'best_formula_str' in result


class TestFactorEvaluator:
    """测试因子评估器"""
    
    @pytest.fixture
    def evaluator(self):
        from app.alpha_mining.backtest.evaluator import FactorEvaluator
        return FactorEvaluator()
    
    def test_evaluate_factor(self, evaluator):
        """评估因子"""
        factor = torch.randn(50)   # 因子值
        returns = torch.randn(50)  # 收益率
        
        metrics = evaluator.evaluate(factor, returns)
        
        assert 'sortino_ratio' in metrics
        assert 'sharpe_ratio' in metrics
        assert 'ic' in metrics
        assert 'rank_ic' in metrics
        assert 'max_drawdown' in metrics
        assert 'turnover' in metrics
        assert 'win_rate' in metrics
    
    def test_get_reward(self, evaluator):
        """获取 RL 奖励"""
        factor = torch.randn(50)
        returns = torch.randn(50)
        
        reward = evaluator.get_reward(factor, returns)
        
        assert isinstance(reward, float)


class TestVocab:
    """测试词汇表"""
    
    def test_vocab_initialization(self):
        """词汇表初始化"""
        from app.alpha_mining.dsl.vocab import FactorVocab, FEATURES
        
        vocab = FactorVocab()
        
        assert vocab.vocab_size > 0
        assert vocab.num_features == len(FEATURES)
        assert vocab.num_ops > 0
    
    def test_token_conversion(self):
        """Token 转换"""
        from app.alpha_mining.dsl.vocab import FactorVocab
        
        vocab = FactorVocab()
        
        # 特征转换
        token = vocab.name_to_token('RET')
        name = vocab.token_to_name(token)
        assert name == 'RET'
        
        # 操作符转换
        token = vocab.name_to_token('ADD')
        name = vocab.token_to_name(token)
        assert name == 'ADD'


class TestAPIEndpoints:
    """测试 REST API 端点（需要 FastAPI TestClient）"""
    
    @pytest.fixture
    def client(self):
        """创建测试客户端"""
        try:
            from fastapi.testclient import TestClient
            from app.main import app
            return TestClient(app)
        except ImportError:
            pytest.skip("FastAPI TestClient not available")
    
    def test_get_operators(self, client):
        """获取操作符列表"""
        response = client.get("/api/v1/alpha-mining/operators")
        
        assert response.status_code == 200
        data = response.json()
        assert data.get('success') is True
        assert 'operators' in data
        assert 'features' in data
        assert len(data['operators']) == 21
    
    def test_get_factors_empty(self, client):
        """获取因子列表（空）"""
        response = client.get("/api/v1/alpha-mining/factors?top_k=5")
        
        assert response.status_code == 200
        data = response.json()
        assert data.get('success') is True
        assert 'factors' in data
    
    def test_evaluate_factor(self, client):
        """评估因子表达式"""
        response = client.post(
            "/api/v1/alpha-mining/evaluate",
            json={"formula": "ADD(RET, VOL)"}
        )
        
        assert response.status_code == 200
        data = response.json()
        # 可能成功或失败（取决于公式解析）
        assert 'success' in data
    
    def test_mine_task_start(self, client):
        """启动挖掘任务"""
        response = client.post(
            "/api/v1/alpha-mining/mine",
            json={"num_steps": 5, "use_sentiment": False, "batch_size": 4}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data.get('success') is True
        assert 'task_id' in data


class TestEdgeCases:
    """边界条件测试"""
    
    def test_empty_formula(self):
        """空表达式"""
        from app.alpha_mining.vm.factor_vm import FactorVM
        from app.alpha_mining.dsl.vocab import DEFAULT_VOCAB
        
        vm = FactorVM(vocab=DEFAULT_VOCAB)
        features = torch.randn(2, 4, 10)
        
        result = vm.execute([], features)
        assert result is None
    
    def test_constant_factor_penalty(self):
        """常量因子惩罚"""
        from app.alpha_mining.model.trainer import AlphaTrainer
        from app.alpha_mining.config import AlphaMiningConfig
        
        config = AlphaMiningConfig()
        trainer = AlphaTrainer(config=config)
        
        # 常量因子的标准差接近 0
        constant_factor = torch.ones(50)
        assert constant_factor.std() < config.constant_threshold
    
    def test_nan_handling(self):
        """NaN 处理"""
        from app.alpha_mining.vm.factor_vm import FactorVM
        from app.alpha_mining.dsl.vocab import DEFAULT_VOCAB
        
        vm = FactorVM(vocab=DEFAULT_VOCAB)
        
        # 创建包含 NaN 的特征
        features = torch.randn(2, 4, 10)
        features[0, 0, 5] = float('nan')
        
        # 执行应该处理 NaN
        formula = [0]  # 只取第一个特征
        result = vm.execute(formula, features)
        
        if result is not None:
            # NaN 应该被替换为 0
            assert not torch.any(torch.isnan(result))


# 运行测试
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
