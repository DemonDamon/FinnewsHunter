"""
智能体 API 路由 - Phase 2
提供辩论功能、执行日志、性能监控等接口
"""
import logging
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query, Body
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc, or_

from ...core.database import get_db
from ...models.news import News
from ...models.analysis import Analysis
from ...agents.debate_agents import create_debate_workflow
from ...services.llm_service import get_llm_provider

logger = logging.getLogger(__name__)

router = APIRouter()


# ============ 模拟数据存储（生产环境应使用数据库） ============

# 存储执行日志
execution_logs: List[Dict[str, Any]] = []

# 存储辩论结果
debate_results: Dict[str, Dict[str, Any]] = {}


# ============ Pydantic 模型 ============

class DebateRequest(BaseModel):
    """辩论请求"""
    stock_code: str = Field(..., description="股票代码")
    stock_name: Optional[str] = Field(None, description="股票名称")
    context: Optional[str] = Field(None, description="额外背景信息")
    provider: Optional[str] = Field(None, description="LLM提供商")
    model: Optional[str] = Field(None, description="模型名称")


class DebateResponse(BaseModel):
    """辩论响应"""
    success: bool
    debate_id: Optional[str] = None
    stock_code: str
    stock_name: Optional[str] = None
    bull_analysis: Optional[Dict[str, Any]] = None
    bear_analysis: Optional[Dict[str, Any]] = None
    final_decision: Optional[Dict[str, Any]] = None
    trajectory: Optional[List[Dict[str, Any]]] = None
    execution_time: Optional[float] = None
    error: Optional[str] = None


class AgentLogEntry(BaseModel):
    """智能体日志条目"""
    id: str
    timestamp: str
    agent_name: str
    agent_role: Optional[str] = None
    action: str
    status: str  # "started", "completed", "failed"
    details: Optional[Dict[str, Any]] = None
    execution_time: Optional[float] = None


class AgentMetrics(BaseModel):
    """智能体性能指标"""
    total_executions: int
    successful_executions: int
    failed_executions: int
    avg_execution_time: float
    agent_stats: Dict[str, Dict[str, Any]]
    recent_activity: List[Dict[str, Any]]


class TrajectoryStep(BaseModel):
    """执行轨迹步骤"""
    step_id: str
    step_name: str
    timestamp: str
    agent_name: Optional[str] = None
    input_data: Optional[Dict[str, Any]] = None
    output_data: Optional[Dict[str, Any]] = None
    duration: Optional[float] = None
    status: str


# ============ API 端点 ============

@router.post("/debate", response_model=DebateResponse)
async def run_stock_debate(
    request: DebateRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    触发股票辩论分析（Bull vs Bear）
    
    - **stock_code**: 股票代码
    - **stock_name**: 股票名称（可选）
    - **context**: 额外背景信息（可选）
    - **provider**: LLM提供商（可选）
    - **model**: 模型名称（可选）
    """
    start_time = datetime.utcnow()
    debate_id = f"debate_{start_time.strftime('%Y%m%d%H%M%S')}_{request.stock_code}"
    
    try:
        # 记录开始
        log_entry = {
            "id": debate_id,
            "timestamp": start_time.isoformat(),
            "agent_name": "DebateWorkflow",
            "action": "debate_start",
            "status": "started",
            "details": {
                "stock_code": request.stock_code,
                "stock_name": request.stock_name
            }
        }
        execution_logs.append(log_entry)
        
        # 标准化股票代码
        code = request.stock_code.upper()
        if code.startswith("SH") or code.startswith("SZ"):
            short_code = code[2:]
        else:
            short_code = code
            code = f"SH{code}" if code.startswith("6") else f"SZ{code}"
        
        # 获取关联新闻 - 使用 PostgreSQL 原生 ARRAY 查询语法
        from sqlalchemy import text
        stock_codes_filter = text(
            "stock_codes @> ARRAY[:code1]::varchar[] OR stock_codes @> ARRAY[:code2]::varchar[]"
        ).bindparams(code1=short_code, code2=code)
        
        news_query = select(News).where(stock_codes_filter).order_by(desc(News.publish_time)).limit(10)
        
        result = await db.execute(news_query)
        news_list = result.scalars().all()
        
        news_data = [
            {
                "id": n.id,
                "title": n.title,
                "content": n.content[:500],
                "sentiment_score": n.sentiment_score,
                "publish_time": n.publish_time.isoformat() if n.publish_time else None
            }
            for n in news_list
        ]
        
        # 创建 LLM provider（如果指定了自定义配置）
        llm_provider = None
        if request.provider or request.model:
            llm_provider = get_llm_provider(
                provider=request.provider,
                model=request.model
            )
        
        # 运行辩论工作流
        workflow = create_debate_workflow(llm_provider)
        debate_result = await workflow.run_debate(
            stock_code=code,
            stock_name=request.stock_name or code,
            news_list=news_data,
            context=request.context or ""
        )
        
        end_time = datetime.utcnow()
        execution_time = (end_time - start_time).total_seconds()
        
        # 存储结果
        debate_results[debate_id] = debate_result
        
        # 记录完成
        log_entry = {
            "id": f"{debate_id}_complete",
            "timestamp": end_time.isoformat(),
            "agent_name": "DebateWorkflow",
            "action": "debate_complete",
            "status": "completed" if debate_result.get("success") else "failed",
            "details": {
                "stock_code": request.stock_code,
                "rating": debate_result.get("final_decision", {}).get("rating", "unknown")
            },
            "execution_time": execution_time
        }
        execution_logs.append(log_entry)
        
        if debate_result.get("success"):
            return DebateResponse(
                success=True,
                debate_id=debate_id,
                stock_code=code,
                stock_name=request.stock_name,
                bull_analysis=debate_result.get("bull_analysis"),
                bear_analysis=debate_result.get("bear_analysis"),
                final_decision=debate_result.get("final_decision"),
                trajectory=debate_result.get("trajectory"),
                execution_time=execution_time
            )
        else:
            return DebateResponse(
                success=False,
                debate_id=debate_id,
                stock_code=code,
                error=debate_result.get("error", "Unknown error")
            )
    
    except Exception as e:
        logger.error(f"Debate failed: {e}", exc_info=True)
        
        # 记录失败
        log_entry = {
            "id": f"{debate_id}_error",
            "timestamp": datetime.utcnow().isoformat(),
            "agent_name": "DebateWorkflow",
            "action": "debate_error",
            "status": "failed",
            "details": {"error": str(e)}
        }
        execution_logs.append(log_entry)
        
        return DebateResponse(
            success=False,
            debate_id=debate_id,
            stock_code=request.stock_code,
            error=str(e)
        )


@router.get("/debate/{debate_id}", response_model=DebateResponse)
async def get_debate_result(debate_id: str):
    """
    获取辩论结果
    
    - **debate_id**: 辩论ID
    """
    if debate_id not in debate_results:
        raise HTTPException(status_code=404, detail="Debate not found")
    
    result = debate_results[debate_id]
    
    return DebateResponse(
        success=result.get("success", False),
        debate_id=debate_id,
        stock_code=result.get("stock_code", ""),
        stock_name=result.get("stock_name"),
        bull_analysis=result.get("bull_analysis"),
        bear_analysis=result.get("bear_analysis"),
        final_decision=result.get("final_decision"),
        trajectory=result.get("trajectory"),
        execution_time=result.get("execution_time")
    )


@router.get("/logs", response_model=List[AgentLogEntry])
async def get_agent_logs(
    limit: int = Query(50, le=200),
    agent_name: Optional[str] = Query(None, description="按智能体名称筛选"),
    status: Optional[str] = Query(None, description="按状态筛选: started, completed, failed")
):
    """
    获取智能体执行日志
    
    - **limit**: 返回数量限制
    - **agent_name**: 按智能体名称筛选
    - **status**: 按状态筛选
    """
    logs = execution_logs.copy()
    
    # 筛选
    if agent_name:
        logs = [log for log in logs if log.get("agent_name") == agent_name]
    if status:
        logs = [log for log in logs if log.get("status") == status]
    
    # 按时间倒序
    logs.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    
    # 限制数量
    logs = logs[:limit]
    
    return [AgentLogEntry(**log) for log in logs]


@router.get("/metrics", response_model=AgentMetrics)
async def get_agent_metrics():
    """
    获取智能体性能指标
    """
    total = len(execution_logs)
    successful = len([log for log in execution_logs if log.get("status") == "completed"])
    failed = len([log for log in execution_logs if log.get("status") == "failed"])
    
    # 计算平均执行时间
    execution_times = [
        log.get("execution_time", 0) 
        for log in execution_logs 
        if log.get("execution_time") is not None
    ]
    avg_time = sum(execution_times) / len(execution_times) if execution_times else 0
    
    # 按智能体统计
    agent_stats = {}
    for log in execution_logs:
        agent_name = log.get("agent_name", "Unknown")
        if agent_name not in agent_stats:
            agent_stats[agent_name] = {
                "total": 0,
                "successful": 0,
                "failed": 0,
                "avg_time": 0,
                "times": []
            }
        agent_stats[agent_name]["total"] += 1
        if log.get("status") == "completed":
            agent_stats[agent_name]["successful"] += 1
        elif log.get("status") == "failed":
            agent_stats[agent_name]["failed"] += 1
        if log.get("execution_time"):
            agent_stats[agent_name]["times"].append(log["execution_time"])
    
    # 计算每个智能体的平均时间
    for agent_name, stats in agent_stats.items():
        if stats["times"]:
            stats["avg_time"] = sum(stats["times"]) / len(stats["times"])
        del stats["times"]  # 不返回原始时间列表
    
    # 最近活动
    recent_logs = sorted(
        execution_logs, 
        key=lambda x: x.get("timestamp", ""), 
        reverse=True
    )[:10]
    
    recent_activity = [
        {
            "timestamp": log.get("timestamp"),
            "agent_name": log.get("agent_name"),
            "action": log.get("action"),
            "status": log.get("status")
        }
        for log in recent_logs
    ]
    
    return AgentMetrics(
        total_executions=total,
        successful_executions=successful,
        failed_executions=failed,
        avg_execution_time=round(avg_time, 2),
        agent_stats=agent_stats,
        recent_activity=recent_activity
    )


@router.get("/trajectory/{debate_id}", response_model=List[TrajectoryStep])
async def get_debate_trajectory(debate_id: str):
    """
    获取辩论执行轨迹
    
    - **debate_id**: 辩论ID
    """
    if debate_id not in debate_results:
        raise HTTPException(status_code=404, detail="Debate not found")
    
    result = debate_results[debate_id]
    trajectory = result.get("trajectory", [])
    
    steps = []
    for i, step in enumerate(trajectory):
        steps.append(TrajectoryStep(
            step_id=f"{debate_id}_step_{i}",
            step_name=step.get("step", "unknown"),
            timestamp=step.get("timestamp", ""),
            agent_name=step.get("data", {}).get("agent"),
            input_data=None,  # 可以扩展
            output_data=step.get("data"),
            duration=None,
            status="completed"
        ))
    
    return steps


@router.delete("/logs")
async def clear_logs():
    """
    清空执行日志（仅用于开发测试）
    """
    global execution_logs
    count = len(execution_logs)
    execution_logs = []
    return {"message": f"Cleared {count} logs"}


@router.get("/available")
async def get_available_agents():
    """
    获取可用的智能体列表
    """
    return {
        "agents": [
            {
                "name": "NewsAnalyst",
                "role": "金融新闻分析师",
                "description": "分析金融新闻的情感、影响和关键信息",
                "status": "active"
            },
            {
                "name": "BullResearcher",
                "role": "看多研究员",
                "description": "从积极角度分析股票，发现投资机会",
                "status": "active"
            },
            {
                "name": "BearResearcher",
                "role": "看空研究员",
                "description": "从风险角度分析股票，识别潜在问题",
                "status": "active"
            },
            {
                "name": "InvestmentManager",
                "role": "投资经理",
                "description": "综合多方观点，做出投资决策",
                "status": "active"
            }
        ],
        "workflows": [
            {
                "name": "NewsAnalysisWorkflow",
                "description": "新闻分析工作流：爬取 -> 清洗 -> 情感分析",
                "agents": ["NewsAnalyst"],
                "status": "active"
            },
            {
                "name": "InvestmentDebateWorkflow",
                "description": "投资辩论工作流：Bull vs Bear 多智能体辩论",
                "agents": ["BullResearcher", "BearResearcher", "InvestmentManager"],
                "status": "active"
            }
        ]
    }

