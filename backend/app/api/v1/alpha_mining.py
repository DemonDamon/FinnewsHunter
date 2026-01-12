"""
Alpha Mining REST API

提供因子挖掘相关的 HTTP 接口。

Endpoints:
- POST /alpha-mining/mine - 启动因子挖掘任务
- POST /alpha-mining/mine/stream - SSE 流式训练进度
- POST /alpha-mining/evaluate - 评估因子表达式
- POST /alpha-mining/generate - 生成候选因子
- POST /alpha-mining/compare-sentiment - 情感融合效果对比
- POST /alpha-mining/agent-demo - AgenticX Agent 调用演示
- GET /alpha-mining/factors - 获取已发现的因子列表
- GET /alpha-mining/status - 获取挖掘状态
- GET /alpha-mining/operators - 获取操作符列表
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, AsyncGenerator
from datetime import datetime
import logging
import uuid
import asyncio
import json
import queue
import threading

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/alpha-mining", tags=["Alpha Mining"])

# 存储挖掘任务状态
_mining_tasks: Dict[str, Dict[str, Any]] = {}
_discovered_factors: List[Dict[str, Any]] = []


# ============================================================================
# Request/Response Models
# ============================================================================

class MineRequest(BaseModel):
    """因子挖掘请求"""
    stock_code: Optional[str] = Field(None, description="股票代码")
    num_steps: int = Field(100, ge=1, le=10000, description="训练步数")
    use_sentiment: bool = Field(True, description="是否使用情感特征")
    batch_size: int = Field(16, ge=1, le=128, description="批量大小")


class EvaluateRequest(BaseModel):
    """因子评估请求"""
    formula: str = Field(..., description="因子表达式")
    stock_code: Optional[str] = Field(None, description="股票代码")


class GenerateRequest(BaseModel):
    """因子生成请求"""
    batch_size: int = Field(10, ge=1, le=100, description="生成数量")
    max_len: int = Field(8, ge=4, le=16, description="最大表达式长度")


class FactorResponse(BaseModel):
    """因子响应"""
    formula: List[int] = Field(..., description="Token 序列")
    formula_str: str = Field(..., description="表达式字符串")
    sortino: float = Field(..., description="Sortino Ratio")
    sharpe: Optional[float] = Field(None, description="Sharpe Ratio")
    ic: Optional[float] = Field(None, description="IC")
    discovered_at: Optional[str] = Field(None, description="发现时间")


class MineResponse(BaseModel):
    """挖掘响应"""
    success: bool
    task_id: str
    message: str
    best_factor: Optional[FactorResponse] = None


class EvaluateResponse(BaseModel):
    """评估响应"""
    success: bool
    formula: str
    metrics: Optional[Dict[str, float]] = None
    error: Optional[str] = None


class GenerateResponse(BaseModel):
    """生成响应"""
    success: bool
    generated: int
    valid: int
    factors: List[Dict[str, Any]]


class TaskStatusResponse(BaseModel):
    """任务状态响应"""
    task_id: str
    status: str  # pending, running, completed, failed
    progress: float  # 0-100
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None


class SentimentCompareRequest(BaseModel):
    """情感融合对比请求"""
    num_steps: int = Field(50, ge=10, le=500, description="训练步数")
    batch_size: int = Field(16, ge=1, le=64, description="批量大小")


class SentimentCompareResponse(BaseModel):
    """情感融合对比响应"""
    success: bool
    with_sentiment: Dict[str, Any] = Field(..., description="含情感特征的结果")
    without_sentiment: Dict[str, Any] = Field(..., description="不含情感特征的结果")
    improvement: Dict[str, float] = Field(..., description="改进幅度")


class AgentDemoRequest(BaseModel):
    """Agent 调用演示请求"""
    stock_code: Optional[str] = Field(None, description="股票代码")
    num_steps: int = Field(30, ge=10, le=200, description="训练步数")
    use_sentiment: bool = Field(True, description="使用情感特征")


class AgentDemoResponse(BaseModel):
    """Agent 调用演示响应"""
    success: bool
    agent_name: str
    tool_name: str
    input_params: Dict[str, Any]
    output: Optional[Dict[str, Any]] = None
    execution_time: float
    logs: List[str] = []


# ============================================================================
# Helper Functions
# ============================================================================

def _get_alpha_mining_components():
    """获取 Alpha Mining 组件"""
    try:
        from ...alpha_mining import (
            AlphaMiningConfig,
            FactorVocab,
            FactorVM,
            AlphaGenerator,
            AlphaTrainer,
            FactorEvaluator,
            generate_mock_data
        )
        
        config = AlphaMiningConfig()
        vocab = FactorVocab()
        vm = FactorVM(vocab=vocab)
        generator = AlphaGenerator(vocab=vocab, config=config)
        evaluator = FactorEvaluator(config=config)
        
        return {
            "config": config,
            "vocab": vocab,
            "vm": vm,
            "generator": generator,
            "evaluator": evaluator,
            "generate_mock_data": generate_mock_data
        }
    except ImportError as e:
        logger.error(f"Failed to import Alpha Mining: {e}")
        raise HTTPException(
            status_code=503,
            detail="Alpha Mining module not available"
        )


async def _run_mining_task(task_id: str, request: MineRequest):
    """后台运行挖掘任务"""
    global _discovered_factors
    
    try:
        _mining_tasks[task_id]["status"] = "running"
        _mining_tasks[task_id]["started_at"] = datetime.utcnow().isoformat()
        
        components = _get_alpha_mining_components()
        
        from ...alpha_mining import AlphaTrainer
        
        # 准备数据
        features, returns = components["generate_mock_data"](
            num_samples=50,
            num_features=6,
            time_steps=252,
            seed=42
        )
        
        # 创建训练器
        config = components["config"]
        config.batch_size = request.batch_size
        
        trainer = AlphaTrainer(
            generator=components["generator"],
            vocab=components["vocab"],
            config=config
        )
        
        # 训练
        result = trainer.train(
            features=features,
            returns=returns,
            num_steps=request.num_steps,
            progress_bar=False
        )
        
        # 保存结果
        if result["best_formula"]:
            factor_info = {
                "formula": result["best_formula"],
                "formula_str": result["best_formula_str"],
                "sortino": result["best_score"],
                "discovered_at": datetime.utcnow().isoformat(),
                "task_id": task_id,
                "stock_code": request.stock_code
            }
            _discovered_factors.append(factor_info)
            
            # 保持只存储最优的 100 个
            _discovered_factors.sort(key=lambda x: x.get("sortino", 0), reverse=True)
            _discovered_factors = _discovered_factors[:100]
        
        _mining_tasks[task_id]["status"] = "completed"
        _mining_tasks[task_id]["progress"] = 100
        _mining_tasks[task_id]["completed_at"] = datetime.utcnow().isoformat()
        _mining_tasks[task_id]["result"] = {
            "best_factor": result["best_formula_str"],
            "best_score": result["best_score"],
            "total_steps": result["total_steps"]
        }
        
    except Exception as e:
        logger.error(f"Mining task {task_id} failed: {e}")
        _mining_tasks[task_id]["status"] = "failed"
        _mining_tasks[task_id]["error"] = str(e)
        _mining_tasks[task_id]["completed_at"] = datetime.utcnow().isoformat()


# ============================================================================
# API Endpoints
# ============================================================================

@router.post("/mine", response_model=MineResponse)
async def mine_factors(
    request: MineRequest,
    background_tasks: BackgroundTasks
):
    """
    启动因子挖掘任务
    
    使用强化学习自动发现有效的交易因子。
    任务在后台执行，可通过 /status/{task_id} 查询进度。
    """
    task_id = str(uuid.uuid4())
    
    # 初始化任务状态
    _mining_tasks[task_id] = {
        "status": "pending",
        "progress": 0,
        "request": request.dict(),
        "created_at": datetime.utcnow().isoformat()
    }
    
    # 添加后台任务
    background_tasks.add_task(_run_mining_task, task_id, request)
    
    return MineResponse(
        success=True,
        task_id=task_id,
        message=f"因子挖掘任务已启动，预计 {request.num_steps} 步训练"
    )


@router.post("/mine/stream")
async def mine_factors_stream(request: MineRequest):
    """
    SSE 流式返回训练进度
    
    实时推送每步训练指标，包括 loss、reward、best_score 等。
    前端可使用 EventSource 订阅。
    """
    async def event_generator() -> AsyncGenerator[str, None]:
        try:
            components = _get_alpha_mining_components()
            
            from ...alpha_mining import AlphaTrainer
            
            # 准备数据
            features, returns = components["generate_mock_data"](
                num_samples=50,
                num_features=6,
                time_steps=252,
                seed=42
            )
            
            # 创建训练器
            config = components["config"]
            config.batch_size = request.batch_size
            
            trainer = AlphaTrainer(
                generator=components["generator"],
                vocab=components["vocab"],
                config=config
            )
            
            # 使用队列在线程间传递数据
            metrics_queue: queue.Queue = queue.Queue()
            training_complete = threading.Event()
            training_error: List[str] = []
            
            def step_callback(metrics: Dict[str, Any]):
                """每步训练回调，将指标放入队列"""
                metrics_queue.put(metrics)
            
            def run_training():
                """在后台线程中运行训练"""
                try:
                    trainer.train(
                        features=features,
                        returns=returns,
                        num_steps=request.num_steps,
                        progress_bar=False,
                        step_callback=step_callback
                    )
                except Exception as e:
                    training_error.append(str(e))
                finally:
                    training_complete.set()
            
            # 启动训练线程
            training_thread = threading.Thread(target=run_training)
            training_thread.start()
            
            # 发送开始事件
            yield f"event: start\ndata: {json.dumps({'status': 'started', 'total_steps': request.num_steps})}\n\n"
            
            # 流式发送训练进度
            while not training_complete.is_set() or not metrics_queue.empty():
                try:
                    metrics = metrics_queue.get(timeout=0.1)
                    event_data = {
                        "step": metrics.get("step", 0),
                        "progress": metrics.get("progress", 0),
                        "loss": round(metrics.get("loss", 0), 6),
                        "avg_reward": round(metrics.get("avg_reward", 0), 6),
                        "max_reward": round(metrics.get("max_reward", 0), 6),
                        "valid_ratio": round(metrics.get("valid_ratio", 0), 4),
                        "best_score": round(metrics.get("best_score", -999), 6),
                        "best_formula": metrics.get("best_formula", ""),
                    }
                    yield f"event: progress\ndata: {json.dumps(event_data)}\n\n"
                except queue.Empty:
                    continue
            
            # 等待训练线程结束
            training_thread.join(timeout=5)
            
            # 发送完成事件
            if training_error:
                yield f"event: error\ndata: {json.dumps({'error': training_error[0]})}\n\n"
            else:
                final_result = {
                    "status": "completed",
                    "best_score": round(trainer.best_score, 6),
                    "best_formula": trainer.best_formula_str,
                    "total_steps": trainer.step_count,
                }
                yield f"event: complete\ndata: {json.dumps(final_result)}\n\n"
                
                # 保存发现的因子
                if trainer.best_formula:
                    _discovered_factors.append({
                        "formula": trainer.best_formula,
                        "formula_str": trainer.best_formula_str,
                        "sortino": trainer.best_score,
                        "discovered_at": datetime.utcnow().isoformat(),
                        "stock_code": request.stock_code
                    })
                    
        except Exception as e:
            logger.error(f"SSE streaming error: {e}")
            yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


@router.post("/compare-sentiment", response_model=SentimentCompareResponse)
async def compare_sentiment_effect(request: SentimentCompareRequest):
    """
    对比有/无情感特征的因子挖掘效果
    
    分别使用纯技术特征和技术+情感特征进行因子挖掘，
    对比最终效果差异。
    """
    try:
        components = _get_alpha_mining_components()
        from ...alpha_mining import AlphaTrainer, AlphaMiningConfig
        
        results = {}
        
        for use_sentiment in [False, True]:
            # 准备数据
            num_features = 6 if use_sentiment else 4  # 4个技术特征 + 2个情感特征
            features, returns = components["generate_mock_data"](
                num_samples=50,
                num_features=num_features,
                time_steps=252,
                seed=42
            )
            
            # 训练
            config = AlphaMiningConfig()
            config.batch_size = request.batch_size
            
            trainer = AlphaTrainer(
                generator=components["generator"],
                vocab=components["vocab"],
                config=config
            )
            
            result = trainer.train(
                features=features,
                returns=returns,
                num_steps=request.num_steps,
                progress_bar=False
            )
            
            key = "with_sentiment" if use_sentiment else "without_sentiment"
            results[key] = {
                "best_score": round(result["best_score"], 6),
                "best_formula": result["best_formula_str"],
                "total_steps": result["total_steps"],
                "num_features": num_features,
            }
        
        # 计算改进幅度
        with_score = results["with_sentiment"]["best_score"]
        without_score = results["without_sentiment"]["best_score"]
        
        if without_score != 0:
            improvement_pct = (with_score - without_score) / abs(without_score) * 100
        else:
            improvement_pct = 0 if with_score == 0 else 100
        
        improvement = {
            "score_diff": round(with_score - without_score, 6),
            "improvement_pct": round(improvement_pct, 2),
        }
        
        return SentimentCompareResponse(
            success=True,
            with_sentiment=results["with_sentiment"],
            without_sentiment=results["without_sentiment"],
            improvement=improvement
        )
        
    except Exception as e:
        logger.error(f"Sentiment comparison failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/agent-demo", response_model=AgentDemoResponse)
async def agent_alpha_mining_demo(request: AgentDemoRequest):
    """
    演示 AgenticX Agent 调用 AlphaMiningTool
    
    展示如何通过 Agent 接口调用因子挖掘功能。
    """
    import time
    start_time = time.time()
    logs = []
    
    try:
        logs.append(f"[{datetime.utcnow().isoformat()}] Agent 初始化...")
        logs.append(f"[{datetime.utcnow().isoformat()}] 调用 AlphaMiningTool...")
        
        # 模拟 Agent 调用
        components = _get_alpha_mining_components()
        from ...alpha_mining import AlphaTrainer
        
        input_params = {
            "stock_code": request.stock_code,
            "num_steps": request.num_steps,
            "use_sentiment": request.use_sentiment,
        }
        logs.append(f"[{datetime.utcnow().isoformat()}] Tool 参数: {json.dumps(input_params)}")
        
        # 准备数据
        features, returns = components["generate_mock_data"](
            num_samples=50,
            num_features=6 if request.use_sentiment else 4,
            time_steps=252,
            seed=42
        )
        logs.append(f"[{datetime.utcnow().isoformat()}] 数据准备完成")
        
        # 训练
        trainer = AlphaTrainer(
            generator=components["generator"],
            vocab=components["vocab"],
            config=components["config"]
        )
        
        logs.append(f"[{datetime.utcnow().isoformat()}] 开始训练...")
        result = trainer.train(
            features=features,
            returns=returns,
            num_steps=request.num_steps,
            progress_bar=False
        )
        logs.append(f"[{datetime.utcnow().isoformat()}] 训练完成")
        
        execution_time = time.time() - start_time
        
        output = {
            "best_formula": result["best_formula_str"],
            "best_score": round(result["best_score"], 6),
            "total_steps": result["total_steps"],
        }
        logs.append(f"[{datetime.utcnow().isoformat()}] 返回结果: {json.dumps(output)}")
        
        return AgentDemoResponse(
            success=True,
            agent_name="QuantitativeAgent",
            tool_name="AlphaMiningTool",
            input_params=input_params,
            output=output,
            execution_time=round(execution_time, 2),
            logs=logs
        )
        
    except Exception as e:
        execution_time = time.time() - start_time
        logs.append(f"[{datetime.utcnow().isoformat()}] 错误: {str(e)}")
        
        return AgentDemoResponse(
            success=False,
            agent_name="QuantitativeAgent",
            tool_name="AlphaMiningTool",
            input_params=request.dict(),
            output=None,
            execution_time=round(execution_time, 2),
            logs=logs
        )


@router.post("/evaluate", response_model=EvaluateResponse)
async def evaluate_factor(request: EvaluateRequest):
    """
    评估因子表达式
    
    对指定的因子表达式进行回测评估，返回各项指标。
    """
    try:
        components = _get_alpha_mining_components()
        vm = components["vm"]
        evaluator = components["evaluator"]
        
        # 解析公式
        tokens = []
        parts = request.formula.replace("(", " ").replace(")", " ").replace(",", " ").split()
        for part in parts:
            part = part.strip()
            if not part:
                continue
            try:
                token = vm.vocab.name_to_token(part)
                tokens.append(token)
            except (ValueError, KeyError):
                continue
        
        if not tokens:
            return EvaluateResponse(
                success=False,
                formula=request.formula,
                error="无法解析因子表达式"
            )
        
        # 准备数据
        features, returns = components["generate_mock_data"](
            num_samples=50,
            num_features=6,
            time_steps=252,
            seed=42
        )
        
        # 执行因子
        factor = vm.execute(tokens, features)
        if factor is None:
            return EvaluateResponse(
                success=False,
                formula=request.formula,
                error="因子执行失败"
            )
        
        # 评估
        metrics = evaluator.evaluate(factor, returns)
        
        return EvaluateResponse(
            success=True,
            formula=request.formula,
            metrics={
                "sortino_ratio": metrics["sortino_ratio"],
                "sharpe_ratio": metrics["sharpe_ratio"],
                "ic": metrics["ic"],
                "rank_ic": metrics["rank_ic"],
                "max_drawdown": metrics["max_drawdown"],
                "turnover": metrics["turnover"],
                "total_return": metrics["total_return"],
                "win_rate": metrics["win_rate"]
            }
        )
        
    except Exception as e:
        logger.error(f"Factor evaluation failed: {e}")
        return EvaluateResponse(
            success=False,
            formula=request.formula,
            error=str(e)
        )


@router.post("/generate", response_model=GenerateResponse)
async def generate_factors(request: GenerateRequest):
    """
    生成候选因子
    
    使用训练好的模型生成一批候选因子表达式。
    """
    try:
        components = _get_alpha_mining_components()
        generator = components["generator"]
        vm = components["vm"]
        evaluator = components["evaluator"]
        
        # 生成因子
        formulas, _ = generator.generate(
            batch_size=request.batch_size,
            max_len=request.max_len
        )
        
        # 准备数据用于评估
        features, returns = components["generate_mock_data"](
            num_samples=50,
            num_features=6,
            time_steps=252,
            seed=42
        )
        
        # 评估每个因子
        results = []
        for formula in formulas:
            factor = vm.execute(formula, features)
            if factor is not None and factor.std() > 1e-6:
                try:
                    metrics = evaluator.evaluate(factor, returns)
                    results.append({
                        "formula": formula,
                        "formula_str": vm.decode(formula),
                        "sortino": round(metrics["sortino_ratio"], 4),
                        "ic": round(metrics["ic"], 4)
                    })
                except Exception:
                    continue
        
        # 按 Sortino 排序
        results.sort(key=lambda x: x["sortino"], reverse=True)
        
        return GenerateResponse(
            success=True,
            generated=len(formulas),
            valid=len(results),
            factors=results[:10]
        )
        
    except Exception as e:
        logger.error(f"Factor generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/factors")
async def get_factors(
    top_k: int = 10,
    stock_code: Optional[str] = None
):
    """
    获取已发现的因子列表
    
    返回按 Sortino Ratio 排序的最优因子。
    """
    factors = _discovered_factors.copy()
    
    # 按股票代码过滤
    if stock_code:
        factors = [f for f in factors if f.get("stock_code") == stock_code]
    
    # 取 top_k
    factors = factors[:top_k]
    
    return {
        "success": True,
        "total": len(_discovered_factors),
        "returned": len(factors),
        "factors": factors
    }


@router.get("/status/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(task_id: str):
    """
    获取挖掘任务状态
    """
    if task_id not in _mining_tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    
    task = _mining_tasks[task_id]
    
    return TaskStatusResponse(
        task_id=task_id,
        status=task["status"],
        progress=task.get("progress", 0),
        result=task.get("result"),
        error=task.get("error"),
        started_at=task.get("started_at"),
        completed_at=task.get("completed_at")
    )


@router.get("/operators")
async def get_operators():
    """
    获取支持的操作符列表
    """
    try:
        from ...alpha_mining.dsl.ops import OPS_CONFIG, get_op_names
        from ...alpha_mining.dsl.vocab import FEATURES
        
        operators = []
        for name, func, arity in OPS_CONFIG:
            operators.append({
                "name": name,
                "arity": arity,
                "description": func.__doc__ or ""
            })
        
        return {
            "success": True,
            "features": FEATURES,
            "operators": operators
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/tasks/{task_id}")
async def delete_task(task_id: str):
    """
    删除任务记录
    """
    if task_id not in _mining_tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    
    del _mining_tasks[task_id]
    
    return {"success": True, "message": f"Task {task_id} deleted"}
