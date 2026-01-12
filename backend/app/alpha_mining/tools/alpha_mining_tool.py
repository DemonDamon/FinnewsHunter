"""
Alpha Mining AgenticX 工具封装

将因子挖掘功能封装为 AgenticX BaseTool，供 Agent 调用。

支持的操作：
- mine: 挖掘新因子
- evaluate: 评估现有因子
- list: 列出已发现的因子
"""

import torch
from typing import Dict, Any, Optional, List
from datetime import datetime
import logging
import json
import uuid

from agenticx.core.tool_v2 import (
    BaseTool,
    ToolMetadata,
    ToolParameter,
    ToolResult,
    ToolContext,
    ToolCategory,
    ToolStatus,
    ParameterType
)

from ..config import AlphaMiningConfig, DEFAULT_CONFIG
from ..dsl.vocab import FactorVocab, DEFAULT_VOCAB
from ..vm.factor_vm import FactorVM
from ..model.alpha_generator import AlphaGenerator
from ..model.trainer import AlphaTrainer
from ..features.market import MarketFeatureBuilder
from ..features.sentiment import SentimentFeatureBuilder
from ..backtest.evaluator import FactorEvaluator
from ..utils import generate_mock_data

logger = logging.getLogger(__name__)


class AlphaMiningTool(BaseTool[Dict[str, Any]]):
    """
    Alpha Mining 工具
    
    封装因子挖掘功能，供 QuantitativeAgent 调用。
    
    支持操作：
    - mine: 使用 RL 挖掘新因子
    - evaluate: 评估指定因子表达式
    - generate: 生成候选因子
    - list: 列出最优因子
    
    Example:
        tool = AlphaMiningTool()
        result = tool.execute({
            "action": "mine",
            "num_steps": 100,
            "use_sentiment": True
        }, context)
    """
    
    def __init__(
        self,
        config: Optional[AlphaMiningConfig] = None,
        model_path: Optional[str] = None
    ):
        """
        初始化 Alpha Mining 工具
        
        Args:
            config: 配置实例
            model_path: 预训练模型路径
        """
        self.config = config or DEFAULT_CONFIG
        
        metadata = ToolMetadata(
            name="alpha_mining",
            version="1.0.0",
            description="量化因子自动挖掘工具，使用符号回归 + 强化学习发现有效交易因子",
            category=ToolCategory.ANALYSIS,
            author="FinnewsHunter Team",
            tags=["quant", "factor", "alpha", "ml", "reinforcement-learning"],
            timeout=600,  # 10分钟超时
            max_retries=1,
        )
        
        super().__init__(metadata)
        
        # 初始化组件
        self.vocab = DEFAULT_VOCAB
        self.vm = FactorVM(vocab=self.vocab)
        self.evaluator = FactorEvaluator(config=self.config)
        self.market_builder = MarketFeatureBuilder(config=self.config)
        self.sentiment_builder = SentimentFeatureBuilder(config=self.config)
        
        # 初始化模型
        self.generator = AlphaGenerator(vocab=self.vocab, config=self.config)
        self.trainer: Optional[AlphaTrainer] = None
        
        # 加载预训练模型
        if model_path:
            try:
                self.generator = AlphaGenerator.load(model_path, vocab=self.vocab)
                logger.info(f"Loaded pretrained model from {model_path}")
            except Exception as e:
                logger.warning(f"Failed to load model: {e}")
        
        # 存储发现的因子
        self.discovered_factors: List[Dict[str, Any]] = []
        
        logger.info("AlphaMiningTool initialized")
    
    def _setup_parameters(self) -> None:
        """设置工具参数"""
        self._parameters = {
            "action": ToolParameter(
                name="action",
                type=ParameterType.STRING,
                description="操作类型: mine(挖掘), evaluate(评估), generate(生成), list(列表)",
                required=True,
                enum=["mine", "evaluate", "generate", "list"]
            ),
            "num_steps": ToolParameter(
                name="num_steps",
                type=ParameterType.INTEGER,
                description="训练步数（仅 mine 操作）",
                required=False,
                default=100,
                minimum=1,
                maximum=10000
            ),
            "formula": ToolParameter(
                name="formula",
                type=ParameterType.STRING,
                description="因子表达式（仅 evaluate 操作）",
                required=False
            ),
            "use_sentiment": ToolParameter(
                name="use_sentiment",
                type=ParameterType.BOOLEAN,
                description="是否使用情感特征",
                required=False,
                default=True
            ),
            "batch_size": ToolParameter(
                name="batch_size",
                type=ParameterType.INTEGER,
                description="生成因子数量（仅 generate 操作）",
                required=False,
                default=10,
                minimum=1,
                maximum=100
            ),
            "top_k": ToolParameter(
                name="top_k",
                type=ParameterType.INTEGER,
                description="返回最优因子数量（仅 list 操作）",
                required=False,
                default=5,
                minimum=1,
                maximum=50
            ),
            "market_data": ToolParameter(
                name="market_data",
                type=ParameterType.OBJECT,
                description="行情数据（可选，不提供则使用模拟数据）",
                required=False
            ),
            "sentiment_data": ToolParameter(
                name="sentiment_data",
                type=ParameterType.OBJECT,
                description="情感数据（可选）",
                required=False
            )
        }
    
    def execute(self, parameters: Dict[str, Any], context: ToolContext) -> ToolResult:
        """同步执行工具"""
        start_time = datetime.now()
        
        try:
            validated = self.validate_parameters(parameters)
            action = validated["action"]
            
            if action == "mine":
                result_data = self._action_mine(validated, context)
            elif action == "evaluate":
                result_data = self._action_evaluate(validated, context)
            elif action == "generate":
                result_data = self._action_generate(validated, context)
            elif action == "list":
                result_data = self._action_list(validated, context)
            else:
                raise ValueError(f"Unknown action: {action}")
            
            end_time = datetime.now()
            
            return ToolResult(
                status=ToolStatus.SUCCESS,
                data=result_data,
                execution_time=(end_time - start_time).total_seconds(),
                start_time=start_time,
                end_time=end_time,
                metadata={"action": action}
            )
            
        except Exception as e:
            logger.error(f"AlphaMiningTool error: {e}")
            end_time = datetime.now()
            
            return ToolResult(
                status=ToolStatus.ERROR,
                error=str(e),
                execution_time=(end_time - start_time).total_seconds(),
                start_time=start_time,
                end_time=end_time
            )
    
    async def aexecute(self, parameters: Dict[str, Any], context: ToolContext) -> ToolResult:
        """异步执行工具"""
        # 目前使用同步实现
        return self.execute(parameters, context)
    
    def _action_mine(self, params: Dict[str, Any], context: ToolContext) -> Dict[str, Any]:
        """执行因子挖掘"""
        num_steps = params.get("num_steps", 100)
        use_sentiment = params.get("use_sentiment", True)
        
        # 准备特征数据
        features, returns = self._prepare_features(params, use_sentiment)
        
        # 创建或复用训练器
        if self.trainer is None:
            self.trainer = AlphaTrainer(
                generator=self.generator,
                vocab=self.vocab,
                config=self.config,
                evaluator=self.evaluator.get_reward
            )
        
        # 执行训练
        logger.info(f"Starting factor mining for {num_steps} steps...")
        result = self.trainer.train(
            features=features,
            returns=returns,
            num_steps=num_steps,
            progress_bar=False
        )
        
        # 保存最优因子
        if result["best_formula"]:
            factor_info = {
                "id": str(uuid.uuid4()),
                "formula": result["best_formula"],
                "formula_str": result["best_formula_str"],
                "score": result["best_score"],
                "discovered_at": datetime.now().isoformat(),
                "training_steps": num_steps,
                "use_sentiment": use_sentiment
            }
            self.discovered_factors.append(factor_info)
            
            # 保持只存储最优的 100 个
            self.discovered_factors.sort(key=lambda x: x["score"], reverse=True)
            self.discovered_factors = self.discovered_factors[:100]
        
        return {
            "success": True,
            "best_factor": result["best_formula_str"],
            "best_score": result["best_score"],
            "total_steps": result["total_steps"],
            "message": f"因子挖掘完成，最优因子: {result['best_formula_str']} (score={result['best_score']:.4f})"
        }
    
    def _action_evaluate(self, params: Dict[str, Any], context: ToolContext) -> Dict[str, Any]:
        """评估因子表达式"""
        formula_str = params.get("formula")
        if not formula_str:
            raise ValueError("Parameter 'formula' is required for evaluate action")
        
        use_sentiment = params.get("use_sentiment", True)
        
        # 解析公式
        formula = self._parse_formula(formula_str)
        if formula is None:
            return {
                "success": False,
                "error": f"Invalid formula: {formula_str}",
                "message": "无法解析因子表达式"
            }
        
        # 准备数据
        features, returns = self._prepare_features(params, use_sentiment)
        
        # 执行因子
        factor = self.vm.execute(formula, features)
        if factor is None:
            return {
                "success": False,
                "error": "Formula execution failed",
                "message": "因子表达式执行失败"
            }
        
        # 评估
        metrics = self.evaluator.evaluate(factor, returns)
        
        return {
            "success": True,
            "formula": formula_str,
            "metrics": metrics,
            "message": f"因子评估完成: Sortino={metrics['sortino_ratio']:.4f}, IC={metrics['ic']:.4f}"
        }
    
    def _action_generate(self, params: Dict[str, Any], context: ToolContext) -> Dict[str, Any]:
        """生成候选因子"""
        batch_size = params.get("batch_size", 10)
        use_sentiment = params.get("use_sentiment", True)
        
        # 生成因子
        formulas, _ = self.generator.generate(batch_size=batch_size)
        
        # 准备数据用于评估
        features, returns = self._prepare_features(params, use_sentiment)
        
        # 评估每个因子
        results = []
        for formula in formulas:
            factor = self.vm.execute(formula, features)
            if factor is not None and factor.std() > 1e-6:
                try:
                    metrics = self.evaluator.evaluate(factor, returns)
                    results.append({
                        "formula": formula,
                        "formula_str": self.vm.decode(formula),
                        "sortino": metrics["sortino_ratio"],
                        "ic": metrics["ic"]
                    })
                except Exception:
                    continue
        
        # 按 Sortino 排序
        results.sort(key=lambda x: x["sortino"], reverse=True)
        
        return {
            "success": True,
            "generated": len(formulas),
            "valid": len(results),
            "factors": results[:10],  # 返回 top 10
            "message": f"生成 {len(formulas)} 个因子，其中 {len(results)} 个有效"
        }
    
    def _action_list(self, params: Dict[str, Any], context: ToolContext) -> Dict[str, Any]:
        """列出已发现的因子"""
        top_k = params.get("top_k", 5)
        
        factors = self.discovered_factors[:top_k]
        
        return {
            "success": True,
            "total_discovered": len(self.discovered_factors),
            "factors": factors,
            "message": f"共发现 {len(self.discovered_factors)} 个因子，返回 top {len(factors)}"
        }
    
    def _prepare_features(
        self,
        params: Dict[str, Any],
        use_sentiment: bool
    ) -> tuple:
        """准备特征数据"""
        market_data = params.get("market_data")
        sentiment_data = params.get("sentiment_data")
        
        if market_data is not None:
            # 使用提供的行情数据
            market_features = self.market_builder.build(market_data)
            time_steps = market_features.size(-1)
            
            if use_sentiment and sentiment_data is not None:
                sentiment_features = self.sentiment_builder.build(
                    sentiment_data, time_steps=time_steps
                )
                features = self.sentiment_builder.combine_with_market(
                    market_features, sentiment_features
                )
            else:
                features = market_features
            
            # 假设收益率在行情数据中
            returns = market_features[:, 0, :]  # RET 特征
        else:
            # 使用模拟数据
            num_features = 6 if use_sentiment else 4
            features, returns = generate_mock_data(
                num_samples=50,
                num_features=num_features,
                time_steps=252,
                seed=42
            )
        
        return features, returns
    
    def _parse_formula(self, formula_str: str) -> Optional[List[int]]:
        """解析因子表达式字符串"""
        # 简单解析：尝试匹配已知的 token
        tokens = []
        
        # 移除括号和空格，按操作符分割
        clean = formula_str.replace("(", " ").replace(")", " ").replace(",", " ")
        parts = clean.split()
        
        for part in parts:
            part = part.strip()
            if not part:
                continue
            
            # 尝试作为特征名
            try:
                token = self.vocab.name_to_token(part)
                tokens.append(token)
            except (ValueError, KeyError):
                # 尝试作为数字（常量）
                try:
                    float(part)
                    # 忽略常量
                    continue
                except ValueError:
                    logger.warning(f"Unknown token: {part}")
                    return None
        
        return tokens if tokens else None
