"""
量化分析智能体

负责量化因子挖掘、技术分析和量化策略生成。
集成 Alpha Mining 模块，提供自动化因子发现能力。

功能：
- 因子挖掘：使用 RL 自动发现有效交易因子
- 因子评估：评估因子的预测能力和回测表现
- 技术分析：结合传统技术指标进行分析
- 策略生成：基于因子生成交易策略建议
"""

import logging
import asyncio
from typing import Dict, Any, List, Optional
from datetime import datetime
import json

logger = logging.getLogger(__name__)


class QuantitativeAgent:
    """
    量化分析智能体
    
    集成 Alpha Mining 模块，提供因子挖掘和量化分析能力。
    
    Args:
        llm_provider: LLM 提供者
        enable_alpha_mining: 是否启用因子挖掘
        model_path: 预训练模型路径
        
    Example:
        agent = QuantitativeAgent(llm_provider)
        result = await agent.analyze(stock_code, stock_name, market_data)
    """
    
    def __init__(
        self,
        llm_provider=None,
        enable_alpha_mining: bool = True,
        model_path: Optional[str] = None
    ):
        self.llm_provider = llm_provider
        self.enable_alpha_mining = enable_alpha_mining
        self.model_path = model_path
        
        # 延迟初始化 Alpha Mining 组件
        self._alpha_mining_initialized = False
        self._generator = None
        self._trainer = None
        self._vm = None
        self._evaluator = None
        self._market_builder = None
        self._sentiment_builder = None
        
        # 存储发现的因子
        self.discovered_factors: List[Dict[str, Any]] = []
        
        logger.info(f"QuantitativeAgent initialized (alpha_mining={enable_alpha_mining})")
    
    def _init_alpha_mining(self):
        """延迟初始化 Alpha Mining 组件"""
        if self._alpha_mining_initialized:
            return
        
        try:
            from ..alpha_mining import (
                AlphaMiningConfig,
                FactorVocab,
                FactorVM,
                AlphaGenerator,
                AlphaTrainer,
                FactorEvaluator,
                MarketFeatureBuilder,
                SentimentFeatureBuilder
            )
            
            config = AlphaMiningConfig()
            vocab = FactorVocab()
            
            self._vm = FactorVM(vocab=vocab)
            self._evaluator = FactorEvaluator(config=config)
            self._market_builder = MarketFeatureBuilder(config=config)
            self._sentiment_builder = SentimentFeatureBuilder(config=config)
            
            # 初始化生成器
            self._generator = AlphaGenerator(vocab=vocab, config=config)
            
            # 如果有预训练模型，加载它
            if self.model_path:
                try:
                    self._generator = AlphaGenerator.load(self.model_path, vocab=vocab)
                    logger.info(f"Loaded pretrained model from {self.model_path}")
                except Exception as e:
                    logger.warning(f"Failed to load model: {e}")
            
            self._alpha_mining_initialized = True
            logger.info("Alpha Mining components initialized")
            
        except ImportError as e:
            logger.warning(f"Alpha Mining not available: {e}")
            self.enable_alpha_mining = False
    
    async def analyze(
        self,
        stock_code: str,
        stock_name: str,
        market_data: Optional[Dict[str, Any]] = None,
        sentiment_data: Optional[Dict[str, Any]] = None,
        context: str = ""
    ) -> Dict[str, Any]:
        """
        执行量化分析
        
        Args:
            stock_code: 股票代码
            stock_name: 股票名称
            market_data: 行情数据（可选）
            sentiment_data: 情感数据（可选）
            context: 额外上下文
            
        Returns:
            分析结果字典
        """
        result = {
            "success": True,
            "stock_code": stock_code,
            "stock_name": stock_name,
            "timestamp": datetime.utcnow().isoformat(),
            "analysis_type": "quantitative",
            "factors_discovered": [],
            "technical_analysis": {},
            "strategy_suggestion": "",
            "confidence": 0.0
        }
        
        try:
            # 1. 因子挖掘（如果启用）
            if self.enable_alpha_mining:
                factor_result = await self._mine_factors(
                    stock_code, stock_name, market_data, sentiment_data
                )
                result["factors_discovered"] = factor_result.get("factors", [])
                result["factor_mining_stats"] = factor_result.get("stats", {})
            
            # 2. 技术分析（使用 LLM）
            if self.llm_provider and market_data:
                tech_analysis = await self._technical_analysis(
                    stock_code, stock_name, market_data, context
                )
                result["technical_analysis"] = tech_analysis
            
            # 3. 生成策略建议
            if self.llm_provider:
                strategy = await self._generate_strategy(
                    stock_code, stock_name, result, context
                )
                result["strategy_suggestion"] = strategy.get("suggestion", "")
                result["confidence"] = strategy.get("confidence", 0.0)
            
        except Exception as e:
            logger.error(f"Quantitative analysis failed: {e}", exc_info=True)
            result["success"] = False
            result["error"] = str(e)
        
        return result
    
    async def _mine_factors(
        self,
        stock_code: str,
        stock_name: str,
        market_data: Optional[Dict[str, Any]],
        sentiment_data: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """执行因子挖掘"""
        self._init_alpha_mining()
        
        if not self._alpha_mining_initialized:
            return {"factors": [], "stats": {"error": "Alpha Mining not available"}}
        
        try:
            import torch
            from ..alpha_mining.utils import generate_mock_data
            
            # 准备特征数据
            if market_data is not None:
                market_features = self._market_builder.build(market_data)
                time_steps = market_features.size(-1)
                
                if sentiment_data is not None:
                    sentiment_features = self._sentiment_builder.build(
                        sentiment_data, time_steps=time_steps
                    )
                    features = self._sentiment_builder.combine_with_market(
                        market_features, sentiment_features
                    )
                else:
                    features = market_features
                
                returns = market_features[:, 0, :]  # RET
            else:
                # 使用模拟数据
                features, returns = generate_mock_data(
                    num_samples=50,
                    num_features=6,
                    time_steps=252,
                    seed=42
                )
            
            # 生成候选因子
            formulas, _ = self._generator.generate(batch_size=20, max_len=8)
            
            # 评估每个因子
            evaluated_factors = []
            for formula in formulas:
                factor = self._vm.execute(formula, features)
                if factor is not None and factor.std() > 1e-6:
                    try:
                        metrics = self._evaluator.evaluate(factor, returns)
                        evaluated_factors.append({
                            "formula": formula,
                            "formula_str": self._vm.decode(formula),
                            "sortino": metrics["sortino_ratio"],
                            "sharpe": metrics["sharpe_ratio"],
                            "ic": metrics["ic"],
                            "max_drawdown": metrics["max_drawdown"]
                        })
                    except Exception:
                        continue
            
            # 按 Sortino 排序，取 top 5
            evaluated_factors.sort(key=lambda x: x["sortino"], reverse=True)
            top_factors = evaluated_factors[:5]
            
            # 更新已发现因子
            for f in top_factors:
                f["stock_code"] = stock_code
                f["discovered_at"] = datetime.utcnow().isoformat()
            self.discovered_factors.extend(top_factors)
            
            return {
                "factors": top_factors,
                "stats": {
                    "generated": len(formulas),
                    "valid": len(evaluated_factors),
                    "top_sortino": top_factors[0]["sortino"] if top_factors else 0
                }
            }
            
        except Exception as e:
            logger.error(f"Factor mining failed: {e}")
            return {"factors": [], "stats": {"error": str(e)}}
    
    async def _technical_analysis(
        self,
        stock_code: str,
        stock_name: str,
        market_data: Dict[str, Any],
        context: str
    ) -> Dict[str, Any]:
        """使用 LLM 进行技术分析"""
        # 提取关键指标
        data_summary = self._summarize_market_data(market_data)
        
        prompt = f"""你是一位资深量化分析师，请对 {stock_name}({stock_code}) 进行技术分析。

行情数据摘要：
{data_summary}

{f'额外背景：{context}' if context else ''}

请分析：
1. 趋势判断（上涨/下跌/震荡）
2. 关键支撑位和阻力位
3. 技术指标信号（MA/MACD/RSI等）
4. 成交量分析
5. 短期（1周）和中期（1月）预测

请以 JSON 格式返回：
{{
    "trend": "上涨/下跌/震荡",
    "support_levels": [价格1, 价格2],
    "resistance_levels": [价格1, 价格2],
    "technical_signals": {{
        "ma_signal": "看涨/看跌/中性",
        "macd_signal": "看涨/看跌/中性",
        "rsi_signal": "超买/超卖/中性"
    }},
    "volume_analysis": "放量/缩量/正常",
    "short_term_outlook": "看涨/看跌/中性",
    "medium_term_outlook": "看涨/看跌/中性",
    "confidence": 0.0-1.0
}}"""
        
        try:
            response = await self.llm_provider.chat(prompt)
            # 尝试解析 JSON
            start = response.find("{")
            end = response.rfind("}") + 1
            if start >= 0 and end > start:
                return json.loads(response[start:end])
            return {"raw_analysis": response}
        except Exception as e:
            logger.warning(f"Technical analysis parsing failed: {e}")
            return {"error": str(e)}
    
    async def _generate_strategy(
        self,
        stock_code: str,
        stock_name: str,
        analysis_result: Dict[str, Any],
        context: str
    ) -> Dict[str, Any]:
        """生成交易策略建议"""
        factors_summary = ""
        if analysis_result.get("factors_discovered"):
            factors = analysis_result["factors_discovered"][:3]
            factors_summary = "发现的有效因子：\n"
            for i, f in enumerate(factors, 1):
                factors_summary += f"{i}. {f['formula_str']} (Sortino={f['sortino']:.2f}, IC={f['ic']:.3f})\n"
        
        tech_summary = ""
        tech = analysis_result.get("technical_analysis", {})
        if tech and not tech.get("error"):
            tech_summary = f"""技术分析结论：
- 趋势：{tech.get('trend', 'N/A')}
- 短期展望：{tech.get('short_term_outlook', 'N/A')}
- 中期展望：{tech.get('medium_term_outlook', 'N/A')}
"""
        
        prompt = f"""你是一位量化投资顾问，请为 {stock_name}({stock_code}) 生成交易策略建议。

{factors_summary}

{tech_summary}

{f'额外背景：{context}' if context else ''}

请提供：
1. 总体投资建议（买入/持有/卖出/观望）
2. 建议的仓位比例（0-100%）
3. 入场/出场价位建议
4. 风险控制建议（止损/止盈）
5. 策略置信度（0-1）

请以 JSON 格式返回：
{{
    "suggestion": "详细策略建议（100-200字）",
    "action": "买入/持有/卖出/观望",
    "position_ratio": 0-100,
    "entry_price": 价格或null,
    "exit_price": 价格或null,
    "stop_loss": 价格或null,
    "take_profit": 价格或null,
    "confidence": 0.0-1.0,
    "risk_level": "低/中/高"
}}"""
        
        try:
            response = await self.llm_provider.chat(prompt)
            start = response.find("{")
            end = response.rfind("}") + 1
            if start >= 0 and end > start:
                return json.loads(response[start:end])
            return {"suggestion": response, "confidence": 0.5}
        except Exception as e:
            logger.warning(f"Strategy generation failed: {e}")
            return {"suggestion": "策略生成失败", "confidence": 0.0, "error": str(e)}
    
    def _summarize_market_data(self, market_data: Dict[str, Any]) -> str:
        """摘要行情数据"""
        if isinstance(market_data, dict):
            if "close" in market_data:
                close = market_data["close"]
                if hasattr(close, "tolist"):
                    close = close.tolist()
                if isinstance(close, list) and len(close) > 0:
                    return f"""
- 最新价格：{close[-1]:.2f}
- 最高价（近期）：{max(close[-20:]):.2f}
- 最低价（近期）：{min(close[-20:]):.2f}
- 价格变化（5日）：{((close[-1]/close[-5])-1)*100:.2f}%
- 价格变化（20日）：{((close[-1]/close[-20])-1)*100:.2f}%
"""
        return "行情数据格式不支持摘要"
    
    async def evaluate_factor(
        self,
        formula_str: str,
        market_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """评估指定因子表达式"""
        self._init_alpha_mining()
        
        if not self._alpha_mining_initialized:
            return {"success": False, "error": "Alpha Mining not available"}
        
        try:
            import torch
            from ..alpha_mining.utils import generate_mock_data
            
            # 解析公式
            tokens = []
            parts = formula_str.replace("(", " ").replace(")", " ").replace(",", " ").split()
            for part in parts:
                part = part.strip()
                if not part:
                    continue
                try:
                    token = self._vm.vocab.name_to_token(part)
                    tokens.append(token)
                except (ValueError, KeyError):
                    continue
            
            if not tokens:
                return {"success": False, "error": "Invalid formula"}
            
            # 准备数据
            if market_data is not None:
                features = self._market_builder.build(market_data)
                returns = features[:, 0, :]
            else:
                features, returns = generate_mock_data()
            
            # 执行
            factor = self._vm.execute(tokens, features)
            if factor is None:
                return {"success": False, "error": "Factor execution failed"}
            
            # 评估
            metrics = self._evaluator.evaluate(factor, returns)
            
            return {
                "success": True,
                "formula": formula_str,
                "metrics": metrics
            }
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def get_best_factors(self, top_k: int = 5) -> List[Dict[str, Any]]:
        """获取最优因子"""
        sorted_factors = sorted(
            self.discovered_factors,
            key=lambda x: x.get("sortino", 0),
            reverse=True
        )
        return sorted_factors[:top_k]


def create_quantitative_agent(
    llm_provider=None,
    enable_alpha_mining: bool = True,
    model_path: Optional[str] = None
) -> QuantitativeAgent:
    """
    创建量化分析智能体
    
    Args:
        llm_provider: LLM 提供者
        enable_alpha_mining: 是否启用因子挖掘
        model_path: 预训练模型路径
        
    Returns:
        QuantitativeAgent 实例
    """
    return QuantitativeAgent(
        llm_provider=llm_provider,
        enable_alpha_mining=enable_alpha_mining,
        model_path=model_path
    )
