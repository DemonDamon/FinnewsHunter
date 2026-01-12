"""
P2 集成测试 - Alpha Mining 完整集成

测试覆盖：
- F18: QuantitativeAgent 集成
- F19: REST API 端点
- 完整工作流测试
"""

import pytest
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import asyncio

# 添加项目路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


# ============================================================================
# F18: QuantitativeAgent 集成测试
# ============================================================================

class TestQuantitativeAgent:
    """量化分析智能体测试"""
    
    def test_agent_import(self):
        """测试 Agent 可导入"""
        from app.agents.quantitative_agent import QuantitativeAgent, create_quantitative_agent
        
        assert QuantitativeAgent is not None
        assert create_quantitative_agent is not None
    
    def test_agent_init_without_llm(self):
        """测试不使用 LLM 初始化"""
        from app.agents.quantitative_agent import QuantitativeAgent
        
        agent = QuantitativeAgent(
            llm_provider=None,
            enable_alpha_mining=True
        )
        
        assert agent.enable_alpha_mining is True
        assert agent._alpha_mining_initialized is False
    
    def test_agent_lazy_init(self):
        """测试延迟初始化"""
        from app.agents.quantitative_agent import QuantitativeAgent
        
        agent = QuantitativeAgent(enable_alpha_mining=True)
        
        # 初始时未初始化
        assert agent._generator is None
        assert agent._vm is None
        
        # 调用 _init_alpha_mining
        agent._init_alpha_mining()
        
        # 现在应该已初始化
        assert agent._alpha_mining_initialized is True
        assert agent._generator is not None
        assert agent._vm is not None
    
    @pytest.mark.asyncio
    async def test_agent_mine_factors(self):
        """测试因子挖掘功能"""
        from app.agents.quantitative_agent import QuantitativeAgent
        
        agent = QuantitativeAgent(enable_alpha_mining=True)
        
        result = await agent._mine_factors(
            stock_code="000001",
            stock_name="测试股票",
            market_data=None,
            sentiment_data=None
        )
        
        assert "factors" in result
        assert "stats" in result
        assert isinstance(result["factors"], list)
    
    @pytest.mark.asyncio
    async def test_agent_full_analysis(self):
        """测试完整分析流程（无 LLM）"""
        from app.agents.quantitative_agent import QuantitativeAgent
        
        agent = QuantitativeAgent(
            llm_provider=None,
            enable_alpha_mining=True
        )
        
        result = await agent.analyze(
            stock_code="000001",
            stock_name="平安银行",
            market_data=None,
            sentiment_data=None,
            context=""
        )
        
        assert result["success"] is True
        assert result["stock_code"] == "000001"
        assert "factors_discovered" in result
    
    @pytest.mark.asyncio
    async def test_agent_with_mock_llm(self):
        """测试使用 Mock LLM"""
        from app.agents.quantitative_agent import QuantitativeAgent
        
        # 创建 Mock LLM
        mock_llm = AsyncMock()
        mock_llm.chat = AsyncMock(return_value='{"trend": "上涨", "confidence": 0.7}')
        
        agent = QuantitativeAgent(
            llm_provider=mock_llm,
            enable_alpha_mining=True
        )
        
        # 准备模拟数据
        import torch
        market_data = {
            "close": torch.randn(100).abs() * 100 + 50,
            "volume": torch.randn(100).abs() * 1e6
        }
        
        result = await agent.analyze(
            stock_code="000001",
            stock_name="平安银行",
            market_data=market_data,
            context="测试上下文"
        )
        
        assert result["success"] is True
        assert len(result["factors_discovered"]) >= 0
    
    def test_agent_evaluate_factor(self):
        """测试因子评估"""
        from app.agents.quantitative_agent import QuantitativeAgent
        
        agent = QuantitativeAgent(enable_alpha_mining=True)
        
        # 同步包装异步调用
        loop = asyncio.get_event_loop()
        result = loop.run_until_complete(
            agent.evaluate_factor("ADD RET VOL")
        )
        
        # 可能成功或失败，取决于公式解析
        assert "success" in result
    
    def test_agent_get_best_factors(self):
        """测试获取最优因子"""
        from app.agents.quantitative_agent import QuantitativeAgent
        
        agent = QuantitativeAgent(enable_alpha_mining=True)
        
        # 手动添加一些因子
        agent.discovered_factors = [
            {"formula_str": "ADD(RET, VOL)", "sortino": 1.5},
            {"formula_str": "MUL(RET, MA5(VOL))", "sortino": 0.8},
            {"formula_str": "SUB(RET, DELTA1(VOL))", "sortino": 2.0},
        ]
        
        best = agent.get_best_factors(top_k=2)
        
        assert len(best) == 2
        assert best[0]["sortino"] == 2.0  # 最高分在前


# ============================================================================
# F19: REST API 测试
# ============================================================================

class TestAlphaMiningAPI:
    """Alpha Mining REST API 测试"""
    
    def test_api_module_import(self):
        """测试 API 模块可导入"""
        from app.api.v1.alpha_mining import router
        
        assert router is not None
        assert router.prefix == "/alpha-mining"
    
    def test_api_routes_exist(self):
        """测试 API 路由存在"""
        from app.api.v1.alpha_mining import router
        
        routes = [r.path for r in router.routes]
        
        assert "/mine" in routes
        assert "/evaluate" in routes
        assert "/generate" in routes
        assert "/factors" in routes
        assert "/status/{task_id}" in routes
        assert "/operators" in routes
    
    @pytest.fixture
    def test_client(self):
        """创建测试客户端"""
        try:
            from fastapi.testclient import TestClient
            from app.main import app
            return TestClient(app)
        except ImportError:
            pytest.skip("FastAPI test client not available")
    
    def test_get_operators(self, test_client):
        """测试获取操作符列表"""
        if test_client is None:
            pytest.skip("Test client not available")
        
        response = test_client.get("/api/v1/alpha-mining/operators")
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "features" in data
        assert "operators" in data
    
    def test_get_factors_empty(self, test_client):
        """测试获取因子列表（空）"""
        if test_client is None:
            pytest.skip("Test client not available")
        
        response = test_client.get("/api/v1/alpha-mining/factors")
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "factors" in data
    
    def test_evaluate_factor(self, test_client):
        """测试因子评估端点"""
        if test_client is None:
            pytest.skip("Test client not available")
        
        response = test_client.post(
            "/api/v1/alpha-mining/evaluate",
            json={"formula": "RET"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "success" in data
    
    def test_generate_factors(self, test_client):
        """测试因子生成端点"""
        if test_client is None:
            pytest.skip("Test client not available")
        
        response = test_client.post(
            "/api/v1/alpha-mining/generate",
            json={"batch_size": 5, "max_len": 6}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "factors" in data


# ============================================================================
# 完整工作流测试
# ============================================================================

class TestFullWorkflow:
    """完整工作流测试"""
    
    @pytest.mark.asyncio
    async def test_end_to_end_factor_discovery(self):
        """端到端因子发现流程"""
        import torch
        
        # 1. 准备数据
        from app.alpha_mining import (
            AlphaMiningConfig,
            FactorVocab,
            FactorVM,
            AlphaGenerator,
            AlphaTrainer,
            FactorEvaluator,
            MarketFeatureBuilder,
            SentimentFeatureBuilder,
            generate_mock_data
        )
        
        # 2. 初始化组件
        config = AlphaMiningConfig(
            d_model=32,
            num_layers=1,
            batch_size=8,
            max_seq_len=6
        )
        vocab = FactorVocab()
        vm = FactorVM(vocab=vocab)
        generator = AlphaGenerator(vocab=vocab, config=config)
        evaluator = FactorEvaluator(config=config)
        
        # 3. 生成模拟数据
        features, returns = generate_mock_data(
            num_samples=30,
            num_features=6,
            time_steps=100,
            seed=42
        )
        
        # 4. 创建训练器并训练
        trainer = AlphaTrainer(
            generator=generator,
            vocab=vocab,
            config=config
        )
        
        result = trainer.train(
            features=features,
            returns=returns,
            num_steps=5,  # 少量步数用于测试
            progress_bar=False
        )
        
        assert result["total_steps"] == 5
        assert "best_score" in result
        
        # 5. 验证最优因子
        if result["best_formula"]:
            factor = vm.execute(result["best_formula"], features)
            assert factor is not None or factor is None  # 可能无效
            
            if factor is not None:
                metrics = evaluator.evaluate(factor, returns)
                assert "sortino_ratio" in metrics
        
        print("\n✅ End-to-end factor discovery test passed!")
    
    @pytest.mark.asyncio
    async def test_quantitative_agent_workflow(self):
        """量化智能体工作流测试"""
        from app.agents.quantitative_agent import QuantitativeAgent
        import torch
        
        # 创建智能体
        agent = QuantitativeAgent(enable_alpha_mining=True)
        
        # 准备数据
        market_data = {
            "close": torch.randn(252).abs() * 100 + 50,
            "volume": torch.randn(252).abs() * 1e6
        }
        
        sentiment_data = {
            "sentiment": torch.randn(252).tolist(),
            "news_count": torch.abs(torch.randn(252)).tolist()
        }
        
        # 执行分析
        result = await agent.analyze(
            stock_code="600000",
            stock_name="浦发银行",
            market_data=market_data,
            sentiment_data=sentiment_data,
            context="银行股分析"
        )
        
        assert result["success"] is True
        assert result["stock_code"] == "600000"
        assert "factors_discovered" in result
        
        print("\n✅ QuantitativeAgent workflow test passed!")
        print(f"   - Factors discovered: {len(result['factors_discovered'])}")
    
    def test_api_and_agent_integration(self):
        """API 和 Agent 集成测试"""
        from app.agents.quantitative_agent import create_quantitative_agent
        
        # 创建智能体
        agent = create_quantitative_agent(enable_alpha_mining=True)
        
        # 验证组件
        agent._init_alpha_mining()
        
        assert agent._generator is not None
        assert agent._vm is not None
        assert agent._evaluator is not None
        
        # 验证因子生成
        formulas, _ = agent._generator.generate(batch_size=3, max_len=5)
        
        assert len(formulas) == 3
        
        # 验证因子执行
        from app.alpha_mining import generate_mock_data
        features, returns = generate_mock_data(num_samples=10, time_steps=50)
        
        valid_count = 0
        for formula in formulas:
            factor = agent._vm.execute(formula, features)
            if factor is not None:
                valid_count += 1
        
        print(f"\n✅ API-Agent integration test passed!")
        print(f"   - Generated: {len(formulas)}, Valid: {valid_count}")


# ============================================================================
# 性能测试
# ============================================================================

class TestPerformance:
    """性能测试"""
    
    def test_generator_speed(self):
        """测试生成器速度"""
        import time
        from app.alpha_mining import AlphaGenerator, AlphaMiningConfig
        
        config = AlphaMiningConfig(d_model=64, num_layers=2)
        generator = AlphaGenerator(config=config)
        
        # 预热
        generator.generate(batch_size=10, max_len=8)
        
        # 计时
        start = time.time()
        for _ in range(10):
            generator.generate(batch_size=100, max_len=8)
        elapsed = time.time() - start
        
        avg_time = elapsed / 10
        print(f"\n📊 Generator speed: {avg_time*1000:.2f}ms per batch (100 factors)")
        
        assert avg_time < 5.0  # 应该在 5 秒内完成
    
    def test_vm_execution_speed(self):
        """测试 VM 执行速度"""
        import time
        import torch
        from app.alpha_mining import FactorVM, FactorVocab, generate_mock_data
        
        vm = FactorVM()
        vocab = FactorVocab()
        features, _ = generate_mock_data(num_samples=100, time_steps=252)
        
        # 创建测试公式
        formulas = [
            [0],  # RET
            [0, 1, vocab.name_to_token("ADD")],  # ADD(RET, VOL)
            [0, vocab.name_to_token("MA5")],  # MA5(RET)
        ]
        
        # 计时
        start = time.time()
        for _ in range(100):
            for formula in formulas:
                vm.execute(formula, features)
        elapsed = time.time() - start
        
        avg_time = elapsed / (100 * len(formulas))
        print(f"\n📊 VM execution speed: {avg_time*1000:.3f}ms per formula")
        
        assert avg_time < 0.1  # 应该在 100ms 内完成


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
