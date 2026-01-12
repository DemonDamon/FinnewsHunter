"""
P1 冒烟测试 - Alpha Mining 数据集成

测试覆盖：
- F13: MarketFeatureBuilder
- F14: SentimentFeatureBuilder
- F15: FactorEvaluator
- F16: AlphaMiningTool
"""

import pytest
import torch
import pandas as pd
import numpy as np
import sys
from pathlib import Path
from datetime import datetime, timedelta

# 添加项目路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from app.alpha_mining.config import AlphaMiningConfig, DEFAULT_CONFIG
from app.alpha_mining.features.market import MarketFeatureBuilder
from app.alpha_mining.features.sentiment import SentimentFeatureBuilder
from app.alpha_mining.backtest.evaluator import FactorEvaluator
from app.alpha_mining.utils import generate_mock_data


# ============================================================================
# F13: MarketFeatureBuilder 测试
# ============================================================================

class TestMarketFeatureBuilder:
    """行情特征构建器测试"""
    
    @pytest.fixture
    def builder(self):
        return MarketFeatureBuilder()
    
    @pytest.fixture
    def sample_df(self):
        """创建示例 DataFrame"""
        dates = pd.date_range("2024-01-01", periods=100, freq="D")
        np.random.seed(42)
        
        return pd.DataFrame({
            "date": dates,
            "close": 100 * np.exp(np.cumsum(np.random.randn(100) * 0.02)),
            "volume": np.abs(np.random.randn(100)) * 1e6 + 1e6,
            "turnover": np.abs(np.random.randn(100)) * 0.05,
        }).set_index("date")
    
    def test_build_from_dataframe(self, builder, sample_df):
        """测试从 DataFrame 构建特征"""
        features = builder.build(sample_df)
        
        assert features.dim() == 3  # [batch, features, time]
        assert features.size(0) == 1  # batch=1
        assert features.size(1) == 4  # 4 个特征
        assert features.size(2) == 100  # time_steps
    
    def test_build_from_tensors(self, builder):
        """测试从张量字典构建特征"""
        data = {
            "close": torch.randn(10, 100).abs() * 100 + 50,
            "volume": torch.randn(10, 100).abs() * 1e6,
        }
        
        features = builder.build(data)
        
        assert features.shape == (10, 4, 100)
    
    def test_features_normalized(self, builder, sample_df):
        """测试特征被正确标准化"""
        features = builder.build(sample_df)
        
        # 检查值在合理范围内
        assert features.max() <= 5.0
        assert features.min() >= -5.0
    
    def test_no_nan_in_features(self, builder, sample_df):
        """测试特征无 NaN"""
        features = builder.build(sample_df)
        
        assert not torch.isnan(features).any()
        assert not torch.isinf(features).any()
    
    def test_feature_names(self, builder):
        """测试特征名称"""
        names = builder.get_feature_names()
        
        assert "RET" in names
        assert "VOL" in names
        assert "VOLUME_CHG" in names
        assert "TURNOVER" in names


# ============================================================================
# F14: SentimentFeatureBuilder 测试
# ============================================================================

class TestSentimentFeatureBuilder:
    """情感特征构建器测试"""
    
    @pytest.fixture
    def builder(self):
        return SentimentFeatureBuilder()
    
    @pytest.fixture
    def sample_df(self):
        """创建示例 DataFrame"""
        dates = pd.date_range("2024-01-01", periods=50, freq="D")
        np.random.seed(42)
        
        return pd.DataFrame({
            "date": dates,
            "sentiment": np.random.randn(50) * 0.3,
            "news_count": np.abs(np.random.randn(50)) * 5 + 1,
        }).set_index("date")
    
    def test_build_from_dataframe(self, builder, sample_df):
        """测试从 DataFrame 构建特征"""
        features = builder.build(sample_df)
        
        assert features.dim() == 3
        assert features.size(0) == 1
        assert features.size(1) == 2  # SENTIMENT, NEWS_COUNT
        assert features.size(2) == 50
    
    def test_build_from_dict(self, builder):
        """测试从字典构建特征"""
        data = {
            "sentiment": [0.1, -0.2, 0.3, 0.0, -0.1],
            "news_count": [5, 3, 8, 2, 4]
        }
        
        features = builder.build(data)
        
        assert features.shape == (1, 2, 5)
    
    def test_build_from_list(self, builder):
        """测试从列表构建特征"""
        data = [
            {"sentiment": 0.1, "news_count": 5},
            {"sentiment": -0.2, "news_count": 3},
            {"sentiment": 0.3, "news_count": 8},
        ]
        
        features = builder.build(data)
        
        assert features.shape == (1, 2, 3)
    
    def test_time_alignment(self, builder):
        """测试时间步对齐"""
        data = {"sentiment": [0.1, 0.2, 0.3], "news_count": [1, 2, 3]}
        
        features = builder.build(data, time_steps=10)
        
        assert features.size(2) == 10
    
    def test_sentiment_decay(self, builder):
        """测试情感衰减"""
        # 创建一个有明显峰值的情感序列
        data = {"sentiment": [0, 0, 0, 1.0, 0, 0, 0], "news_count": [1] * 7}
        
        features = builder.build(data)
        
        # 衰减后的值应该逐渐减小
        sentiment = features[0, 0, :]
        assert sentiment[4] < sentiment[3]  # 峰值后开始衰减
    
    def test_combine_with_market(self, builder):
        """测试与行情特征合并"""
        market = torch.randn(2, 4, 100)  # [batch, 4 features, time]
        sentiment = torch.randn(2, 2, 100)  # [batch, 2 features, time]
        
        combined = builder.combine_with_market(market, sentiment)
        
        assert combined.shape == (2, 6, 100)


# ============================================================================
# F15: FactorEvaluator 测试
# ============================================================================

class TestFactorEvaluator:
    """因子评估器测试"""
    
    @pytest.fixture
    def evaluator(self):
        return FactorEvaluator()
    
    @pytest.fixture
    def sample_data(self):
        """创建示例数据"""
        np.random.seed(42)
        time_steps = 252
        
        # 模拟收益率
        returns = torch.randn(time_steps) * 0.02
        
        # 模拟因子（与收益率有一定相关性）
        noise = torch.randn(time_steps) * 0.5
        factor = returns + noise
        
        return factor, returns
    
    def test_evaluate_basic(self, evaluator, sample_data):
        """测试基础评估"""
        factor, returns = sample_data
        
        metrics = evaluator.evaluate(factor, returns)
        
        assert "sortino_ratio" in metrics
        assert "sharpe_ratio" in metrics
        assert "ic" in metrics
        assert "rank_ic" in metrics
        assert "max_drawdown" in metrics
        assert "turnover" in metrics
    
    def test_evaluate_batch(self, evaluator):
        """测试批量评估"""
        factor = torch.randn(10, 100)
        returns = torch.randn(10, 100) * 0.02
        
        metrics = evaluator.evaluate(factor, returns)
        
        # 应该返回平均值和标准差
        assert "sortino_ratio" in metrics
        assert "sortino_ratio_std" in metrics
    
    def test_get_reward(self, evaluator, sample_data):
        """测试获取 RL 奖励"""
        factor, returns = sample_data
        
        reward = evaluator.get_reward(factor, returns)
        
        assert isinstance(reward, float)
        assert not np.isnan(reward)
    
    def test_good_factor_high_ic(self, evaluator):
        """测试好因子有较高 IC"""
        # 创建一个与收益率高度相关的因子
        returns = torch.randn(252) * 0.02
        factor = returns * 0.8 + torch.randn(252) * 0.01  # 80% 相关
        
        metrics = evaluator.evaluate(factor, returns)
        
        # IC 应该显著为正
        assert metrics["ic"] > 0.3
    
    def test_random_factor_low_ic(self, evaluator):
        """测试随机因子 IC 接近 0"""
        returns = torch.randn(252) * 0.02
        factor = torch.randn(252)  # 完全随机
        
        metrics = evaluator.evaluate(factor, returns)
        
        # IC 应该接近 0
        assert abs(metrics["ic"]) < 0.3
    
    def test_compare_factors(self, evaluator):
        """测试因子比较"""
        returns = torch.randn(252) * 0.02
        
        # 创建不同质量的因子
        good_factor = returns * 0.8 + torch.randn(252) * 0.01
        bad_factor = torch.randn(252)
        
        results = evaluator.compare_factors(
            [good_factor, bad_factor],
            returns,
            ["good", "bad"]
        )
        
        assert "good" in results
        assert "bad" in results
        assert results["good"]["ic"] > results["bad"]["ic"]
    
    def test_rank_factors(self, evaluator):
        """测试因子排名"""
        returns = torch.randn(100) * 0.02
        
        factors = [torch.randn(100) for _ in range(5)]
        
        ranking = evaluator.rank_factors(factors, returns)
        
        assert len(ranking) == 5
        # 检查是降序排列
        scores = [score for _, score in ranking]
        assert scores == sorted(scores, reverse=True)


# ============================================================================
# F16: AlphaMiningTool 测试（需要 AgenticX 依赖）
# ============================================================================

class TestAlphaMiningToolImport:
    """AlphaMiningTool 导入测试"""
    
    def test_import_tool(self):
        """测试工具可导入"""
        try:
            from app.alpha_mining.tools.alpha_mining_tool import AlphaMiningTool
            assert AlphaMiningTool is not None
        except ImportError as e:
            # 如果 AgenticX 不可用，跳过
            pytest.skip(f"AgenticX not available: {e}")
    
    def test_tool_metadata(self):
        """测试工具元数据"""
        try:
            from app.alpha_mining.tools.alpha_mining_tool import AlphaMiningTool
            
            tool = AlphaMiningTool()
            
            assert tool.name == "alpha_mining"
            assert "量化因子" in tool.description
            assert len(tool.parameters) > 0
        except ImportError:
            pytest.skip("AgenticX not available")


# ============================================================================
# 端到端 P1 测试
# ============================================================================

class TestP1EndToEnd:
    """P1 端到端测试"""
    
    def test_full_pipeline_with_real_features(self):
        """使用真实特征的完整流程"""
        # 1. 准备行情数据
        dates = pd.date_range("2024-01-01", periods=252, freq="D")
        np.random.seed(42)
        
        market_df = pd.DataFrame({
            "close": 100 * np.exp(np.cumsum(np.random.randn(252) * 0.02)),
            "volume": np.abs(np.random.randn(252)) * 1e6 + 1e6,
            "turnover": np.abs(np.random.randn(252)) * 0.05,
        }, index=dates)
        
        # 2. 构建行情特征
        market_builder = MarketFeatureBuilder()
        market_features = market_builder.build(market_df)
        
        assert market_features.shape == (1, 4, 252)
        
        # 3. 准备情感数据
        sentiment_data = {
            "sentiment": np.random.randn(252) * 0.3,
            "news_count": np.abs(np.random.randn(252)) * 5 + 1
        }
        
        # 4. 构建情感特征
        sentiment_builder = SentimentFeatureBuilder()
        sentiment_features = sentiment_builder.build(sentiment_data, time_steps=252)
        
        assert sentiment_features.shape == (1, 2, 252)
        
        # 5. 合并特征
        combined = sentiment_builder.combine_with_market(
            market_features, sentiment_features
        )
        
        assert combined.shape == (1, 6, 252)
        
        # 6. 导入生成器和 VM
        from app.alpha_mining.model.alpha_generator import AlphaGenerator
        from app.alpha_mining.vm.factor_vm import FactorVM
        
        config = AlphaMiningConfig(d_model=32, num_layers=1, max_seq_len=6)
        generator = AlphaGenerator(config=config)
        vm = FactorVM()
        
        # 7. 生成并执行因子
        formulas, _ = generator.generate(batch_size=5, max_len=5)
        
        valid_factors = []
        for formula in formulas:
            factor = vm.execute(formula, combined)
            if factor is not None and factor.std() > 1e-6:
                valid_factors.append(factor)
        
        # 8. 评估因子
        if valid_factors:
            evaluator = FactorEvaluator()
            returns = market_features[:, 0, :]  # RET 作为收益率
            
            for factor in valid_factors:
                metrics = evaluator.evaluate(factor, returns)
                assert "sortino_ratio" in metrics
        
        print(f"\n✅ P1 End-to-end test passed!")
        print(f"   - Market features: {market_features.shape}")
        print(f"   - Sentiment features: {sentiment_features.shape}")
        print(f"   - Combined features: {combined.shape}")
        print(f"   - Valid factors generated: {len(valid_factors)}/{len(formulas)}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
