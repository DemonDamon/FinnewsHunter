"""
智能体 API 路由 - Phase 2
提供辩论功能、执行日志、性能监控等接口
"""
import logging
import json
import asyncio
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any, AsyncGenerator
from fastapi import APIRouter, Depends, HTTPException, Query, Body
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc, or_

from ...core.database import get_db
from ...models.news import News
from ...models.analysis import Analysis
from ...agents.debate_agents import create_debate_workflow
from ...agents.orchestrator import create_orchestrator
from ...services.llm_service import get_llm_provider
from ...services.stock_data_service import stock_data_service

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
    mode: Optional[str] = Field("parallel", description="辩论模式: parallel, realtime_debate, quick_analysis")


class DebateResponse(BaseModel):
    """辩论响应"""
    success: bool
    debate_id: Optional[str] = None
    stock_code: str
    stock_name: Optional[str] = None
    mode: Optional[str] = None  # 辩论模式
    bull_analysis: Optional[Dict[str, Any]] = None
    bear_analysis: Optional[Dict[str, Any]] = None
    final_decision: Optional[Dict[str, Any]] = None
    quick_analysis: Optional[Dict[str, Any]] = None  # 快速分析结果
    debate_history: Optional[List[Dict[str, Any]]] = None  # 实时辩论历史
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
    logger.info(f"🎯 收到辩论请求: stock_code={request.stock_code}, stock_name={request.stock_name}")
    
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
        
        logger.info(f"🔍 查询股票 {code} 的关联新闻...")
        
        # 获取关联新闻 - 使用 PostgreSQL 原生 ARRAY 查询语法
        from sqlalchemy import text
        stock_codes_filter = text(
            "stock_codes @> ARRAY[:code1]::varchar[] OR stock_codes @> ARRAY[:code2]::varchar[]"
        ).bindparams(code1=short_code, code2=code)
        
        news_query = select(News).where(stock_codes_filter).order_by(desc(News.publish_time)).limit(10)
        
        result = await db.execute(news_query)
        news_list = result.scalars().all()
        
        logger.info(f"📰 找到 {len(news_list)} 条关联新闻")
        
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
        
        # 如果没有关联新闻，给出警告
        if not news_data:
            logger.warning(f"⚠️ 股票 {code} 没有关联新闻，辩论将基于空数据进行")
        
        # 获取财务数据和资金流向（用于增强辩论上下文）
        logger.info(f"📊 获取 {code} 的财务数据和资金流向...")
        try:
            debate_context = await stock_data_service.get_debate_context(code)
            akshare_context = debate_context.get("summary", "")
            logger.info(f"📊 获取到额外数据: {akshare_context[:100]}...")
        except Exception as e:
            logger.warning(f"⚠️ 获取财务数据失败: {e}")
            akshare_context = ""
        
        # 合并用户提供的上下文和 akshare 数据
        full_context = ""
        if request.context:
            full_context += f"【用户补充信息】\n{request.context}\n\n"
        if akshare_context:
            full_context += f"【实时数据】\n{akshare_context}"
        
        # 创建 LLM provider（如果指定了自定义配置）
        llm_provider = None
        if request.provider or request.model:
            logger.info(f"🤖 使用自定义模型: provider={request.provider}, model={request.model}")
            llm_provider = get_llm_provider(
                provider=request.provider,
                model=request.model
            )
        else:
            logger.info("🤖 使用默认 LLM 配置")
        
        # 选择辩论模式
        mode = request.mode or "parallel"
        logger.info(f"⚔️ 开始辩论工作流，模式: {mode}")
        
        if mode == "parallel":
            # 使用原有的并行工作流
            workflow = create_debate_workflow(llm_provider)
            debate_result = await workflow.run_debate(
                stock_code=code,
                stock_name=request.stock_name or code,
                news_list=news_data,
                context=full_context
            )
        else:
            # 使用新的编排器（支持 realtime_debate 和 quick_analysis）
            orchestrator = create_orchestrator(mode=mode, llm_provider=llm_provider)
            debate_result = await orchestrator.run(
                stock_code=code,
                stock_name=request.stock_name or code,
                context=full_context,
                news_list=news_data
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
                mode=mode,
                bull_analysis=debate_result.get("bull_analysis"),
                bear_analysis=debate_result.get("bear_analysis"),
                final_decision=debate_result.get("final_decision"),
                quick_analysis=debate_result.get("quick_analysis"),
                debate_history=debate_result.get("debate_history"),
                trajectory=debate_result.get("trajectory"),
                execution_time=execution_time
            )
        else:
            return DebateResponse(
                success=False,
                debate_id=debate_id,
                stock_code=code,
                mode=mode,
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


# ============ SSE 流式辩论 ============

async def generate_debate_stream(
    stock_code: str,
    stock_name: str,
    mode: str,
    context: str,
    news_data: List[Dict],
    llm_provider
) -> AsyncGenerator[str, None]:
    """
    生成辩论的 SSE 流
    
    事件类型:
    - phase: 阶段变化
    - agent: 智能体发言
    - progress: 进度更新
    - result: 最终结果
    - error: 错误信息
    """
    debate_id = f"debate_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
    
    def sse_event(event_type: str, data: Dict) -> str:
        """格式化 SSE 事件"""
        return f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
    
    try:
        # 发送开始事件
        yield sse_event("phase", {
            "phase": "start",
            "message": f"开始{mode}模式分析",
            "debate_id": debate_id
        })
        
        if mode == "quick_analysis":
            # 快速分析模式 - 使用流式输出
            yield sse_event("phase", {"phase": "analyzing", "message": "快速分析师正在分析..."})
            
            prompt = f"""请对 {stock_name}({stock_code}) 进行快速投资分析。

背景资料:
{context[:2000]}

相关新闻:
{json.dumps([n.get('title', '') for n in news_data[:5]], ensure_ascii=False)}

请快速给出：
1. 核心观点（一句话）
2. 看多因素（3点）
3. 看空因素（3点）
4. 投资建议（买入/持有/卖出）
5. 风险提示"""
            
            messages = [
                {"role": "system", "content": "你是一位专业的股票分析师，擅长快速分析和决策。"},
                {"role": "user", "content": prompt}
            ]
            
            full_response = ""
            for chunk in llm_provider.stream(messages):
                full_response += chunk
                yield sse_event("agent", {
                    "agent": "QuickAnalyst",
                    "role": "快速分析师",
                    "content": chunk,
                    "is_chunk": True
                })
                await asyncio.sleep(0)  # 让出控制权
            
            # 发送完成事件
            yield sse_event("result", {
                "success": True,
                "mode": mode,
                "quick_analysis": {
                    "analysis": full_response,
                    "success": True
                },
                "execution_time": 0
            })
            
        elif mode == "realtime_debate":
            # 实时辩论模式 - 多轮交锋
            max_rounds = 3  # 最大辩论轮数
            
            yield sse_event("phase", {"phase": "data_collection", "message": "数据专员正在搜集资料..."})
            await asyncio.sleep(0.3)
            
            # 数据搜集
            yield sse_event("agent", {
                "agent": "DataCollector",
                "role": "数据专员",
                "content": f"📊 已搜集 {stock_name} 的相关数据：{len(news_data)} 条新闻，财务数据已就绪。\n\n辩论即将开始，共 {max_rounds} 轮。",
                "is_chunk": False
            })
            
            # 辩论历史（用于上下文）
            debate_history = []
            bull_full = ""
            bear_full = ""
            
            # 多轮辩论
            for round_num in range(1, max_rounds + 1):
                yield sse_event("phase", {
                    "phase": "debate",
                    "message": f"第 {round_num}/{max_rounds} 轮辩论",
                    "round": round_num,
                    "max_rounds": max_rounds
                })
                
                # === Bull 发言 ===
                yield sse_event("agent", {
                    "agent": "BullResearcher",
                    "role": "看多研究员",
                    "content": "",
                    "is_start": True,
                    "round": round_num
                })
                
                if round_num == 1:
                    # 第一轮：开场陈述
                    bull_prompt = f"""你是看多研究员，正在参与关于 {stock_name}({stock_code}) 的多空辩论。

背景资料: {context[:800]}
新闻: {json.dumps([n.get('title', '') for n in news_data[:3]], ensure_ascii=False)}

这是第1轮辩论，请做开场陈述（约150字）：
1. 表明你的核心看多观点
2. 给出2-3个关键论据"""
                else:
                    # 后续轮次：反驳对方
                    last_bear = debate_history[-1]["content"] if debate_history else ""
                    bull_prompt = f"""你是看多研究员，正在与看空研究员辩论 {stock_name}。

这是第{round_num}轮辩论。

对方（看空研究员）刚才说：
"{last_bear[:300]}"

请反驳对方观点并补充新论据（约120字）：
1. 指出对方论据的漏洞
2. 补充新的看多理由"""
                
                bull_messages = [
                    {"role": "system", "content": "你是一位辩论中的看多研究员。言简意赅，有理有据，语气自信但不傲慢。"},
                    {"role": "user", "content": bull_prompt}
                ]
                
                bull_response = ""
                for chunk in llm_provider.stream(bull_messages):
                    bull_response += chunk
                    yield sse_event("agent", {
                        "agent": "BullResearcher",
                        "role": "看多研究员",
                        "content": chunk,
                        "is_chunk": True,
                        "round": round_num
                    })
                    await asyncio.sleep(0)
                
                bull_full += f"\n\n**【第{round_num}轮】**\n{bull_response}"
                debate_history.append({"agent": "Bull", "round": round_num, "content": bull_response})
                
                yield sse_event("agent", {
                    "agent": "BullResearcher",
                    "role": "看多研究员",
                    "content": "",
                    "is_end": True,
                    "round": round_num
                })
                
                # === Bear 发言（反驳） ===
                yield sse_event("agent", {
                    "agent": "BearResearcher",
                    "role": "看空研究员",
                    "content": "",
                    "is_start": True,
                    "round": round_num
                })
                
                if round_num == 1:
                    bear_prompt = f"""你是看空研究员，正在与看多研究员辩论 {stock_name}({stock_code})。

背景资料: {context[:800]}

对方（看多研究员）刚才说：
"{bull_response[:300]}"

这是第1轮辩论，请反驳对方并陈述你的看空观点（约150字）：
1. 指出对方论据的问题
2. 给出2-3个风险因素"""
                else:
                    bear_prompt = f"""你是看空研究员，正在与看多研究员辩论 {stock_name}。

这是第{round_num}轮辩论。

对方（看多研究员）刚才说：
"{bull_response[:300]}"

请反驳对方观点并补充新论据（约120字）：
1. 驳斥对方的新论据
2. 强化你的风险警示"""
                
                bear_messages = [
                    {"role": "system", "content": "你是一位辩论中的看空研究员。言简意赅，善于发现风险，语气谨慎但有说服力。"},
                    {"role": "user", "content": bear_prompt}
                ]
                
                bear_response = ""
                for chunk in llm_provider.stream(bear_messages):
                    bear_response += chunk
                    yield sse_event("agent", {
                        "agent": "BearResearcher",
                        "role": "看空研究员",
                        "content": chunk,
                        "is_chunk": True,
                        "round": round_num
                    })
                    await asyncio.sleep(0)
                
                bear_full += f"\n\n**【第{round_num}轮】**\n{bear_response}"
                debate_history.append({"agent": "Bear", "round": round_num, "content": bear_response})
                
                yield sse_event("agent", {
                    "agent": "BearResearcher",
                    "role": "看空研究员",
                    "content": "",
                    "is_end": True,
                    "round": round_num
                })
            
            # === 投资经理总结决策 ===
            yield sse_event("phase", {"phase": "decision", "message": "辩论结束，投资经理正在做最终决策..."})
            
            yield sse_event("agent", {
                "agent": "InvestmentManager",
                "role": "投资经理",
                "content": "",
                "is_start": True
            })
            
            # 整理辩论历史
            debate_summary = "\n".join([
                f"【第{h['round']}轮-{'看多' if h['agent']=='Bull' else '看空'}】{h['content'][:150]}..."
                for h in debate_history
            ])
            
            decision_prompt = f"""你是投资经理，刚刚主持了一场关于 {stock_name}({stock_code}) 的多空辩论。

辩论回顾：
{debate_summary}

请做出最终投资决策（约200字）：
1. 评价双方辩论表现
2. 指出最有说服力的论点
3. **最终评级**：[强烈推荐/推荐/中性/谨慎/回避]
4. 给出操作建议"""
            
            decision_messages = [
                {"role": "system", "content": "你是一位经验丰富的投资经理，善于在多空观点中做出理性决策。"},
                {"role": "user", "content": decision_prompt}
            ]
            
            decision = ""
            for chunk in llm_provider.stream(decision_messages):
                decision += chunk
                yield sse_event("agent", {
                    "agent": "InvestmentManager",
                    "role": "投资经理",
                    "content": chunk,
                    "is_chunk": True
                })
                await asyncio.sleep(0)
            
            yield sse_event("agent", {
                "agent": "InvestmentManager",
                "role": "投资经理",
                "content": "",
                "is_end": True
            })
            
            # 提取评级
            rating = "中性"
            for r in ["强烈推荐", "推荐", "中性", "谨慎", "回避"]:
                if r in decision:
                    rating = r
                    break
            
            # 发送完成事件
            yield sse_event("result", {
                "success": True,
                "mode": mode,
                "debate_id": debate_id,
                "total_rounds": max_rounds,
                "bull_analysis": {"analysis": bull_full.strip(), "success": True, "agent_name": "BullResearcher", "agent_role": "看多研究员"},
                "bear_analysis": {"analysis": bear_full.strip(), "success": True, "agent_name": "BearResearcher", "agent_role": "看空研究员"},
                "final_decision": {"decision": decision, "rating": rating, "success": True, "agent_name": "InvestmentManager", "agent_role": "投资经理"},
                "debate_history": debate_history
            })
            
        else:
            # parallel 模式 - 也使用流式，但并行展示
            yield sse_event("phase", {"phase": "parallel_analysis", "message": "Bull/Bear 并行分析中..."})
            
            # 由于是并行，我们交替输出
            bull_prompt = f"""你是看多研究员，请从积极角度分析 {stock_name}({stock_code})：
背景资料: {context[:1500]}
新闻: {json.dumps([n.get('title', '') for n in news_data[:5]], ensure_ascii=False)}
请给出完整的看多分析报告。"""

            bear_prompt = f"""你是看空研究员，请从风险角度分析 {stock_name}({stock_code})：
背景资料: {context[:1500]}
新闻: {json.dumps([n.get('title', '') for n in news_data[:5]], ensure_ascii=False)}
请给出完整的看空分析报告。"""

            # Bull 流式输出
            yield sse_event("agent", {"agent": "BullResearcher", "role": "看多研究员", "content": "", "is_start": True})
            bull_analysis = ""
            for chunk in llm_provider.stream([
                {"role": "system", "content": "你是一位乐观但理性的股票研究员。"},
                {"role": "user", "content": bull_prompt}
            ]):
                bull_analysis += chunk
                yield sse_event("agent", {"agent": "BullResearcher", "role": "看多研究员", "content": chunk, "is_chunk": True})
                await asyncio.sleep(0)
            yield sse_event("agent", {"agent": "BullResearcher", "role": "看多研究员", "content": "", "is_end": True})
            
            # Bear 流式输出
            yield sse_event("agent", {"agent": "BearResearcher", "role": "看空研究员", "content": "", "is_start": True})
            bear_analysis = ""
            for chunk in llm_provider.stream([
                {"role": "system", "content": "你是一位谨慎的股票研究员。"},
                {"role": "user", "content": bear_prompt}
            ]):
                bear_analysis += chunk
                yield sse_event("agent", {"agent": "BearResearcher", "role": "看空研究员", "content": chunk, "is_chunk": True})
                await asyncio.sleep(0)
            yield sse_event("agent", {"agent": "BearResearcher", "role": "看空研究员", "content": "", "is_end": True})
            
            # 投资经理决策
            yield sse_event("phase", {"phase": "decision", "message": "投资经理决策中..."})
            yield sse_event("agent", {"agent": "InvestmentManager", "role": "投资经理", "content": "", "is_start": True})
            
            decision_prompt = f"""综合以下多空观点，对 {stock_name} 做出投资决策：
【看多】{bull_analysis[:800]}
【看空】{bear_analysis[:800]}
请给出评级[强烈推荐/推荐/中性/谨慎/回避]和决策理由。"""
            
            decision = ""
            for chunk in llm_provider.stream([
                {"role": "system", "content": "你是投资经理。"},
                {"role": "user", "content": decision_prompt}
            ]):
                decision += chunk
                yield sse_event("agent", {"agent": "InvestmentManager", "role": "投资经理", "content": chunk, "is_chunk": True})
                await asyncio.sleep(0)
            yield sse_event("agent", {"agent": "InvestmentManager", "role": "投资经理", "content": "", "is_end": True})
            
            rating = "中性"
            for r in ["强烈推荐", "推荐", "中性", "谨慎", "回避"]:
                if r in decision:
                    rating = r
                    break
            
            yield sse_event("result", {
                "success": True,
                "mode": mode,
                "bull_analysis": {"analysis": bull_analysis, "success": True, "agent_name": "BullResearcher", "agent_role": "看多研究员"},
                "bear_analysis": {"analysis": bear_analysis, "success": True, "agent_name": "BearResearcher", "agent_role": "看空研究员"},
                "final_decision": {"decision": decision, "rating": rating, "success": True, "agent_name": "InvestmentManager", "agent_role": "投资经理"}
            })
        
        yield sse_event("phase", {"phase": "complete", "message": "分析完成"})
        
    except Exception as e:
        logger.error(f"SSE Debate error: {e}", exc_info=True)
        yield sse_event("error", {"message": str(e)})


@router.post("/debate/stream")
async def run_stock_debate_stream(
    request: DebateRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    流式辩论分析（SSE）
    
    使用 Server-Sent Events 实时推送辩论过程
    """
    logger.info(f"🎯 收到流式辩论请求: stock_code={request.stock_code}, mode={request.mode}")
    
    # 标准化股票代码
    code = request.stock_code.upper()
    if code.startswith("SH") or code.startswith("SZ"):
        short_code = code[2:]
    else:
        short_code = code
        code = f"SH{code}" if code.startswith("6") else f"SZ{code}"
    
    # 获取关联新闻
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
            "content": n.content[:500] if n.content else "",
            "sentiment_score": n.sentiment_score,
            "publish_time": n.publish_time.isoformat() if n.publish_time else None
        }
        for n in news_list
    ]
    
    # 获取额外上下文
    try:
        debate_context = await stock_data_service.get_debate_context(code)
        akshare_context = debate_context.get("summary", "")
    except Exception as e:
        logger.warning(f"获取财务数据失败: {e}")
        akshare_context = ""
    
    full_context = ""
    if request.context:
        full_context += f"【用户补充】{request.context}\n\n"
    if akshare_context:
        full_context += f"【实时数据】{akshare_context}"
    
    # 创建 LLM provider
    llm_provider = get_llm_provider(
        provider=request.provider,
        model=request.model
    ) if request.provider or request.model else get_llm_provider()
    
    mode = request.mode or "parallel"
    stock_name = request.stock_name or code
    
    return StreamingResponse(
        generate_debate_stream(code, stock_name, mode, full_context, news_data, llm_provider),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"  # 禁用 nginx 缓冲
        }
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

