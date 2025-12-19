"""
协作编排器

负责管理多智能体协作流程，支持：
- 并行分析模式（parallel）
- 实时辩论模式（realtime_debate）
- 快速分析模式（quick_analysis）
"""
import logging
import asyncio
from typing import Dict, Any, List, Optional, Callable, AsyncGenerator
from datetime import datetime
from enum import Enum

from ..config import get_mode_config, get_default_mode, DebateModeConfig
from ..llm.provider import get_llm_provider

logger = logging.getLogger(__name__)


class DebatePhase(Enum):
    """辩论阶段"""
    INITIALIZING = "initializing"
    DATA_COLLECTION = "data_collection"
    OPENING = "opening"
    DEBATE = "debate"
    CLOSING = "closing"
    COMPLETED = "completed"
    FAILED = "failed"


class DebateEvent:
    """辩论事件（用于实时流式输出）"""
    def __init__(
        self,
        event_type: str,
        agent_name: str,
        content: str,
        phase: DebatePhase,
        round_number: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        self.event_type = event_type
        self.agent_name = agent_name
        self.content = content
        self.phase = phase
        self.round_number = round_number
        self.metadata = metadata or {}
        self.timestamp = datetime.utcnow().isoformat()
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_type": self.event_type,
            "agent_name": self.agent_name,
            "content": self.content,
            "phase": self.phase.value,
            "round_number": self.round_number,
            "metadata": self.metadata,
            "timestamp": self.timestamp
        }


class DebateOrchestrator:
    """辩论编排器"""
    
    def __init__(self, mode: str = None, llm_provider=None):
        self.mode = mode or get_default_mode()
        self.config = get_mode_config(self.mode)
        if not self.config:
            raise ValueError(f"未知的辩论模式: {self.mode}")
        
        self.llm_provider = llm_provider or get_llm_provider()
        self.current_phase = DebatePhase.INITIALIZING
        self.current_round = 0
        self.start_time: Optional[datetime] = None
        self.events: List[DebateEvent] = []
        self.is_interrupted = False
        
        # 事件回调
        self._event_callbacks: List[Callable[[DebateEvent], None]] = []
        
        logger.info(f"🎭 初始化辩论编排器，模式: {self.mode}")
    
    def on_event(self, callback: Callable[[DebateEvent], None]):
        """注册事件回调"""
        self._event_callbacks.append(callback)
    
    def _emit_event(self, event: DebateEvent):
        """触发事件"""
        self.events.append(event)
        for callback in self._event_callbacks:
            try:
                callback(event)
            except Exception as e:
                logger.error(f"事件回调出错: {e}")
    
    def interrupt(self, reason: str = "manager_decision"):
        """打断辩论"""
        self.is_interrupted = True
        self._emit_event(DebateEvent(
            event_type="interrupt",
            agent_name="InvestmentManager",
            content=f"辩论被打断: {reason}",
            phase=self.current_phase
        ))
        logger.info(f"⚡ 辩论被打断: {reason}")
    
    async def run(
        self,
        stock_code: str,
        stock_name: str,
        context: str = "",
        news_list: List[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """运行辩论流程"""
        self.start_time = datetime.utcnow()
        result = {
            "success": False,
            "mode": self.mode,
            "stock_code": stock_code,
            "stock_name": stock_name,
            "trajectory": [],
            "events": []
        }
        
        try:
            self._emit_event(DebateEvent(
                event_type="start",
                agent_name="Orchestrator",
                content=f"开始 {self.config.name}",
                phase=DebatePhase.INITIALIZING
            ))
            
            # 根据模式选择执行流程
            if self.config.flow.type == "parallel_then_summarize":
                result = await self._run_parallel_mode(stock_code, stock_name, context, news_list)
            elif self.config.flow.type == "orchestrated_debate":
                result = await self._run_realtime_debate_mode(stock_code, stock_name, context, news_list)
            elif self.config.flow.type == "single_agent":
                result = await self._run_quick_mode(stock_code, stock_name, context)
            else:
                raise ValueError(f"未知的流程类型: {self.config.flow.type}")
            
            self.current_phase = DebatePhase.COMPLETED
            self._emit_event(DebateEvent(
                event_type="complete",
                agent_name="Orchestrator",
                content="辩论完成",
                phase=DebatePhase.COMPLETED
            ))
            
        except Exception as e:
            logger.error(f"辩论执行失败: {e}", exc_info=True)
            self.current_phase = DebatePhase.FAILED
            result["error"] = str(e)
            self._emit_event(DebateEvent(
                event_type="error",
                agent_name="Orchestrator",
                content=f"辩论失败: {e}",
                phase=DebatePhase.FAILED
            ))
        
        result["events"] = [e.to_dict() for e in self.events]
        result["execution_time"] = (datetime.utcnow() - self.start_time).total_seconds()
        
        return result
    
    async def _run_parallel_mode(
        self,
        stock_code: str,
        stock_name: str,
        context: str,
        news_list: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """运行并行分析模式"""
        from .debate_agents import BullResearcherAgent, BearResearcherAgent, InvestmentManagerAgent
        
        logger.info("🔄 执行并行分析模式")
        
        # 初始化智能体
        bull_agent = BullResearcherAgent(self.llm_provider)
        bear_agent = BearResearcherAgent(self.llm_provider)
        manager_agent = InvestmentManagerAgent(self.llm_provider)
        
        # 准备新闻摘要
        news_summary = self._prepare_news_summary(news_list)
        full_context = f"{context}\n\n{news_summary}" if context else news_summary
        
        self.current_phase = DebatePhase.DEBATE
        
        # 并行执行Bull和Bear分析
        self._emit_event(DebateEvent(
            event_type="analysis_start",
            agent_name="BullResearcher",
            content="开始看多分析",
            phase=self.current_phase
        ))
        self._emit_event(DebateEvent(
            event_type="analysis_start",
            agent_name="BearResearcher",
            content="开始看空分析",
            phase=self.current_phase
        ))
        
        bull_task = asyncio.create_task(
            bull_agent.analyze(stock_code, stock_name, full_context)
        )
        bear_task = asyncio.create_task(
            bear_agent.analyze(stock_code, stock_name, full_context)
        )
        
        bull_analysis, bear_analysis = await asyncio.gather(bull_task, bear_task)
        
        self._emit_event(DebateEvent(
            event_type="analysis_complete",
            agent_name="BullResearcher",
            content=bull_analysis.get("analysis", "")[:200] + "...",
            phase=self.current_phase
        ))
        self._emit_event(DebateEvent(
            event_type="analysis_complete",
            agent_name="BearResearcher",
            content=bear_analysis.get("analysis", "")[:200] + "...",
            phase=self.current_phase
        ))
        
        # 投资经理做决策
        self.current_phase = DebatePhase.CLOSING
        self._emit_event(DebateEvent(
            event_type="decision_start",
            agent_name="InvestmentManager",
            content="开始综合决策",
            phase=self.current_phase
        ))
        
        final_decision = await manager_agent.make_decision(
            stock_code=stock_code,
            stock_name=stock_name,
            bull_analysis=bull_analysis.get("analysis", ""),
            bear_analysis=bear_analysis.get("analysis", ""),
            context=full_context
        )
        
        self._emit_event(DebateEvent(
            event_type="decision_complete",
            agent_name="InvestmentManager",
            content=f"决策完成: {final_decision.get('rating', 'N/A')}",
            phase=self.current_phase
        ))
        
        return {
            "success": True,
            "mode": self.mode,
            "bull_analysis": bull_analysis,
            "bear_analysis": bear_analysis,
            "final_decision": final_decision,
            "trajectory": [
                {"agent": "BullResearcher", "action": "analyze", "status": "completed"},
                {"agent": "BearResearcher", "action": "analyze", "status": "completed"},
                {"agent": "InvestmentManager", "action": "decide", "status": "completed"}
            ]
        }
    
    async def _run_realtime_debate_mode(
        self,
        stock_code: str,
        stock_name: str,
        context: str,
        news_list: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """运行实时辩论模式"""
        from .debate_agents import BullResearcherAgent, BearResearcherAgent, InvestmentManagerAgent
        from .data_collector import DataCollectorAgent
        
        logger.info("🎭 执行实时辩论模式")
        
        # 初始化智能体
        data_collector = DataCollectorAgent(self.llm_provider)
        bull_agent = BullResearcherAgent(self.llm_provider)
        bear_agent = BearResearcherAgent(self.llm_provider)
        manager_agent = InvestmentManagerAgent(self.llm_provider)
        
        rules = self.config.rules
        max_rounds = rules.max_rounds or 5
        max_time = rules.max_time or 600
        
        trajectory = []
        debate_history = []
        
        # Phase 1: 数据搜集
        if rules.require_data_collection:
            self.current_phase = DebatePhase.DATA_COLLECTION
            self._emit_event(DebateEvent(
                event_type="phase_start",
                agent_name="DataCollector",
                content="开始搜集数据",
                phase=self.current_phase
            ))
            
            collected_data = await data_collector.collect_data(stock_code, stock_name)
            data_summary = collected_data.get("summary", "")
            
            self._emit_event(DebateEvent(
                event_type="data_collected",
                agent_name="DataCollector",
                content=data_summary[:300] + "...",
                phase=self.current_phase
            ))
            
            trajectory.append({
                "agent": "DataCollector",
                "action": "collect_data",
                "status": "completed"
            })
            
            # 合并数据到上下文
            context = f"{context}\n\n{data_summary}" if context else data_summary
        
        # Phase 2: 投资经理开场
        self.current_phase = DebatePhase.OPENING
        opening_prompt = f"""你是投资经理，现在要主持一场关于 {stock_name}({stock_code}) 的多空辩论。

请做开场陈述，说明：
1. 今天辩论的股票背景
2. 辩论的规则（最多{max_rounds}轮，每人每轮1分钟）
3. 请看多研究员先发言

背景资料:
{context[:2000]}"""
        
        self._emit_event(DebateEvent(
            event_type="opening",
            agent_name="InvestmentManager",
            content="投资经理开场中...",
            phase=self.current_phase
        ))
        
        opening = await self.llm_provider.chat(opening_prompt)
        
        self._emit_event(DebateEvent(
            event_type="speech",
            agent_name="InvestmentManager",
            content=opening,
            phase=self.current_phase,
            round_number=0
        ))
        
        trajectory.append({
            "agent": "InvestmentManager",
            "action": "opening",
            "status": "completed",
            "content": opening
        })
        
        debate_history.append({
            "round": 0,
            "agent": "InvestmentManager",
            "type": "opening",
            "content": opening
        })
        
        # Phase 3: 辩论回合
        self.current_phase = DebatePhase.DEBATE
        bull_analysis_full = ""
        bear_analysis_full = ""
        
        for round_num in range(1, max_rounds + 1):
            if self.is_interrupted:
                logger.info(f"辩论在第{round_num}轮被打断")
                break
            
            # 检查时间限制
            elapsed = (datetime.utcnow() - self.start_time).total_seconds()
            if elapsed > max_time:
                logger.info(f"辩论超时，已进行 {elapsed:.0f} 秒")
                break
            
            self.current_round = round_num
            
            # Bull发言
            self._emit_event(DebateEvent(
                event_type="round_start",
                agent_name="BullResearcher",
                content=f"第{round_num}轮 - 看多研究员发言",
                phase=self.current_phase,
                round_number=round_num
            ))
            
            bull_prompt = self._build_debate_prompt(
                agent_role="看多研究员",
                stock_name=stock_name,
                stock_code=stock_code,
                round_num=round_num,
                max_rounds=max_rounds,
                context=context,
                debate_history=debate_history
            )
            
            bull_response = await bull_agent.debate_round(bull_prompt)
            bull_analysis_full += f"\n\n### 第{round_num}轮\n{bull_response}"
            
            self._emit_event(DebateEvent(
                event_type="speech",
                agent_name="BullResearcher",
                content=bull_response,
                phase=self.current_phase,
                round_number=round_num
            ))
            
            debate_history.append({
                "round": round_num,
                "agent": "BullResearcher",
                "type": "argument",
                "content": bull_response
            })
            
            # Bear发言
            self._emit_event(DebateEvent(
                event_type="round_continue",
                agent_name="BearResearcher",
                content=f"第{round_num}轮 - 看空研究员发言",
                phase=self.current_phase,
                round_number=round_num
            ))
            
            bear_prompt = self._build_debate_prompt(
                agent_role="看空研究员",
                stock_name=stock_name,
                stock_code=stock_code,
                round_num=round_num,
                max_rounds=max_rounds,
                context=context,
                debate_history=debate_history
            )
            
            bear_response = await bear_agent.debate_round(bear_prompt)
            bear_analysis_full += f"\n\n### 第{round_num}轮\n{bear_response}"
            
            self._emit_event(DebateEvent(
                event_type="speech",
                agent_name="BearResearcher",
                content=bear_response,
                phase=self.current_phase,
                round_number=round_num
            ))
            
            debate_history.append({
                "round": round_num,
                "agent": "BearResearcher",
                "type": "argument",
                "content": bear_response
            })
            
            trajectory.append({
                "agent": "Debate",
                "action": f"round_{round_num}",
                "status": "completed"
            })
            
            # 投资经理可选择打断
            if rules.manager_can_interrupt and round_num < max_rounds:
                should_interrupt = await self._check_manager_interrupt(
                    manager_agent, debate_history, stock_name
                )
                if should_interrupt:
                    self.interrupt("投资经理认为已有足够信息做决策")
                    break
        
        # Phase 4: 投资经理总结决策
        self.current_phase = DebatePhase.CLOSING
        self._emit_event(DebateEvent(
            event_type="closing_start",
            agent_name="InvestmentManager",
            content="投资经理正在做最终决策...",
            phase=self.current_phase
        ))
        
        final_decision = await manager_agent.make_decision(
            stock_code=stock_code,
            stock_name=stock_name,
            bull_analysis=bull_analysis_full,
            bear_analysis=bear_analysis_full,
            context=f"{context}\n\n辩论历史:\n{self._format_debate_history(debate_history)}"
        )
        
        self._emit_event(DebateEvent(
            event_type="decision",
            agent_name="InvestmentManager",
            content=final_decision.get("summary", ""),
            phase=self.current_phase,
            metadata={"rating": final_decision.get("rating")}
        ))
        
        trajectory.append({
            "agent": "InvestmentManager",
            "action": "final_decision",
            "status": "completed"
        })
        
        return {
            "success": True,
            "mode": self.mode,
            "bull_analysis": {"analysis": bull_analysis_full, "success": True},
            "bear_analysis": {"analysis": bear_analysis_full, "success": True},
            "final_decision": final_decision,
            "debate_history": debate_history,
            "total_rounds": self.current_round,
            "was_interrupted": self.is_interrupted,
            "trajectory": trajectory
        }
    
    async def _run_quick_mode(
        self,
        stock_code: str,
        stock_name: str,
        context: str
    ) -> Dict[str, Any]:
        """运行快速分析模式"""
        from .data_collector import QuickAnalystAgent
        
        logger.info("🚀 执行快速分析模式")
        
        quick_analyst = QuickAnalystAgent(self.llm_provider)
        
        self.current_phase = DebatePhase.DEBATE
        self._emit_event(DebateEvent(
            event_type="quick_analysis_start",
            agent_name="QuickAnalyst",
            content="开始快速分析",
            phase=self.current_phase
        ))
        
        result = await quick_analyst.quick_analyze(stock_code, stock_name, context)
        
        self._emit_event(DebateEvent(
            event_type="quick_analysis_complete",
            agent_name="QuickAnalyst",
            content=result.get("analysis", "")[:200] + "...",
            phase=self.current_phase
        ))
        
        return {
            "success": result.get("success", False),
            "mode": self.mode,
            "quick_analysis": result,
            "trajectory": [
                {"agent": "QuickAnalyst", "action": "analyze", "status": "completed"}
            ]
        }
    
    def _prepare_news_summary(self, news_list: List[Dict[str, Any]]) -> str:
        """准备新闻摘要"""
        if not news_list:
            return "暂无相关新闻数据"
        
        summary_parts = ["## 相关新闻摘要\n"]
        for i, news in enumerate(news_list[:10], 1):
            title = news.get("title", "无标题")
            content = news.get("content", "")[:200]
            source = news.get("source", "未知来源")
            date = news.get("published_at", "")
            
            summary_parts.append(f"{i}. **{title}** ({source}, {date})\n   {content}...\n")
        
        return "\n".join(summary_parts)
    
    def _build_debate_prompt(
        self,
        agent_role: str,
        stock_name: str,
        stock_code: str,
        round_num: int,
        max_rounds: int,
        context: str,
        debate_history: List[Dict]
    ) -> str:
        """构建辩论提示词"""
        history_text = self._format_debate_history(debate_history[-4:])  # 只取最近4条
        
        return f"""你是{agent_role}，正在参与关于 {stock_name}({stock_code}) 的多空辩论。

当前是第 {round_num}/{max_rounds} 轮辩论。

背景资料:
{context[:1500]}

最近的辩论历史:
{history_text}

请发表你的观点（约200字）：
1. 如果是第一轮，阐述你的核心论点
2. 如果不是第一轮，先反驳对方观点，再补充新论据
3. 用数据和事实支持你的论点
4. 语气专业但有说服力"""
    
    def _format_debate_history(self, history: List[Dict]) -> str:
        """格式化辩论历史"""
        if not history:
            return "（尚无辩论历史）"
        
        lines = []
        for item in history:
            agent = item.get("agent", "Unknown")
            content = item.get("content", "")[:300]
            round_num = item.get("round", 0)
            lines.append(f"[第{round_num}轮 - {agent}]: {content}")
        
        return "\n\n".join(lines)
    
    async def _check_manager_interrupt(
        self,
        manager_agent,
        debate_history: List[Dict],
        stock_name: str
    ) -> bool:
        """检查投资经理是否要打断辩论"""
        if len(debate_history) < 4:
            return False
        
        check_prompt = f"""你是投资经理，正在主持关于 {stock_name} 的辩论。

目前的辩论历史:
{self._format_debate_history(debate_history[-4:])}

请判断：你是否已经获得足够的信息来做出投资决策？
如果是，回复"是"；如果还需要更多辩论，回复"否"。
只回复一个字。"""
        
        try:
            response = await self.llm_provider.chat(check_prompt)
            return "是" in response[:5]
        except Exception:
            return False


def create_orchestrator(mode: str = None, llm_provider=None) -> DebateOrchestrator:
    """创建辩论编排器"""
    return DebateOrchestrator(mode=mode, llm_provider=llm_provider)

