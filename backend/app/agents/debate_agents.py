"""
辩论智能体 - Phase 2
实现 Bull vs Bear 多智能体辩论机制
"""
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from agenticx import Agent

from ..services.llm_service import get_llm_provider

logger = logging.getLogger(__name__)


class BullResearcherAgent(Agent):
    """
    看多研究员智能体
    职责：基于新闻和数据，生成看多观点和投资建议
    """
    
    def __init__(self, llm_provider=None, organization_id: str = "finnews"):
        # 先调用父类初始化（Pydantic BaseModel）
        super().__init__(
            name="BullResearcher",
            role="看多研究员",
            goal="从积极角度分析股票，发现投资机会和增长潜力",
            backstory="""你是一位乐观但理性的股票研究员，擅长发现被低估的投资机会。
你善于从新闻和数据中提取正面信息，分析公司的增长潜力、竞争优势和市场机遇。
你的分析注重长期价值，但也关注短期催化剂。""",
            organization_id=organization_id
        )
        
        # 在 super().__init__() 之后设置 _llm_provider（避免被 Pydantic 清除）
        if llm_provider is None:
            llm_provider = get_llm_provider()
        object.__setattr__(self, '_llm_provider', llm_provider)
        
        logger.info(f"Initialized {self.name} agent")
    
    def analyze(
        self,
        stock_code: str,
        stock_name: str,
        news_list: List[Dict[str, Any]],
        context: str = ""
    ) -> Dict[str, Any]:
        """
        生成看多分析报告
        """
        news_summary = self._summarize_news(news_list)
        
        prompt = f"""你是一位看多研究员，请从积极角度分析以下股票：

【股票信息】
代码：{stock_code}
名称：{stock_name}

【相关新闻摘要】
{news_summary}

【分析背景】
{context if context else "无额外背景信息"}

请从以下角度进行看多分析：

## 1. 核心看多逻辑
- 列出3-5个看多的核心理由
- 每个理由需要有数据或新闻支撑

## 2. 增长催化剂
- 短期催化剂（1-3个月内可能发生的利好）
- 中长期催化剂（3-12个月的增长驱动力）

## 3. 估值分析
- 当前估值是否具有吸引力
- 与同行业对比的优势

## 4. 目标预期
- 给出合理的预期收益空间
- 说明达成条件

## 5. 风险提示
- 虽然看多，但也需要指出可能的风险

请确保分析客观、有理有据，避免盲目乐观。
"""
        
        try:
            response = self._llm_provider.invoke([
                {"role": "system", "content": f"你是{self.role}，{self.backstory}"},
                {"role": "user", "content": prompt}
            ])
            
            analysis_text = response.content if hasattr(response, 'content') else str(response)
            
            return {
                "success": True,
                "agent_name": self.name,
                "agent_role": self.role,
                "stance": "bull",
                "analysis": analysis_text,
                "timestamp": datetime.utcnow().isoformat()
            }
        
        except Exception as e:
            logger.error(f"Bull analysis failed: {e}")
            return {
                "success": False,
                "agent_name": self.name,
                "stance": "bull",
                "error": str(e)
            }
    
    def _summarize_news(self, news_list: List[Dict[str, Any]]) -> str:
        """汇总新闻信息"""
        if not news_list:
            return "暂无相关新闻"
        
        summaries = []
        for i, news in enumerate(news_list[:5], 1):
            title = news.get("title", "")
            sentiment = news.get("sentiment_score")
            sentiment_text = ""
            if sentiment is not None:
                if sentiment > 0.1:
                    sentiment_text = "（利好）"
                elif sentiment < -0.1:
                    sentiment_text = "（利空）"
                else:
                    sentiment_text = "（中性）"
            summaries.append(f"{i}. {title} {sentiment_text}")
        
        return "\n".join(summaries)


class BearResearcherAgent(Agent):
    """
    看空研究员智能体
    职责：基于新闻和数据，识别风险和潜在问题
    """
    
    def __init__(self, llm_provider=None, organization_id: str = "finnews"):
        # 先调用父类初始化（Pydantic BaseModel）
        super().__init__(
            name="BearResearcher",
            role="看空研究员",
            goal="从风险角度分析股票，识别潜在问题和下行风险",
            backstory="""你是一位谨慎的股票研究员，擅长发现被忽视的风险。
你善于从新闻和数据中提取负面信号，分析公司的潜在问题、竞争威胁和市场风险。
你的分析注重风险控制，帮助投资者避免损失。""",
            organization_id=organization_id
        )
        
        # 在 super().__init__() 之后设置 _llm_provider（避免被 Pydantic 清除）
        if llm_provider is None:
            llm_provider = get_llm_provider()
        object.__setattr__(self, '_llm_provider', llm_provider)
        
        logger.info(f"Initialized {self.name} agent")
    
    def analyze(
        self,
        stock_code: str,
        stock_name: str,
        news_list: List[Dict[str, Any]],
        context: str = ""
    ) -> Dict[str, Any]:
        """
        生成看空分析报告
        """
        news_summary = self._summarize_news(news_list)
        
        prompt = f"""你是一位看空研究员，请从风险角度分析以下股票：

【股票信息】
代码：{stock_code}
名称：{stock_name}

【相关新闻摘要】
{news_summary}

【分析背景】
{context if context else "无额外背景信息"}

请从以下角度进行风险分析：

## 1. 核心风险因素
- 列出3-5个主要风险点
- 每个风险需要有数据或新闻支撑

## 2. 负面催化剂
- 短期可能出现的利空事件
- 中长期的结构性风险

## 3. 估值风险
- 当前估值是否过高
- 与同行业对比的劣势

## 4. 下行空间
- 分析可能的下跌幅度
- 触发下跌的条件

## 5. 反驳看多观点
- 针对常见的看多逻辑提出质疑
- 指出乐观预期的不确定性

请确保分析客观、有理有据，避免无根据的悲观。
"""
        
        try:
            response = self._llm_provider.invoke([
                {"role": "system", "content": f"你是{self.role}，{self.backstory}"},
                {"role": "user", "content": prompt}
            ])
            
            analysis_text = response.content if hasattr(response, 'content') else str(response)
            
            return {
                "success": True,
                "agent_name": self.name,
                "agent_role": self.role,
                "stance": "bear",
                "analysis": analysis_text,
                "timestamp": datetime.utcnow().isoformat()
            }
        
        except Exception as e:
            logger.error(f"Bear analysis failed: {e}")
            return {
                "success": False,
                "agent_name": self.name,
                "stance": "bear",
                "error": str(e)
            }
    
    def _summarize_news(self, news_list: List[Dict[str, Any]]) -> str:
        """汇总新闻信息"""
        if not news_list:
            return "暂无相关新闻"
        
        summaries = []
        for i, news in enumerate(news_list[:5], 1):
            title = news.get("title", "")
            sentiment = news.get("sentiment_score")
            sentiment_text = ""
            if sentiment is not None:
                if sentiment > 0.1:
                    sentiment_text = "（利好）"
                elif sentiment < -0.1:
                    sentiment_text = "（利空）"
                else:
                    sentiment_text = "（中性）"
            summaries.append(f"{i}. {title} {sentiment_text}")
        
        return "\n".join(summaries)


class InvestmentManagerAgent(Agent):
    """
    投资经理智能体
    职责：综合 Bull/Bear 观点，做出最终投资决策
    """
    
    def __init__(self, llm_provider=None, organization_id: str = "finnews"):
        # 先调用父类初始化（Pydantic BaseModel）
        super().__init__(
            name="InvestmentManager",
            role="投资经理",
            goal="综合多方观点，做出理性的投资决策",
            backstory="""你是一位经验丰富的投资经理，擅长在多方观点中找到平衡。
你善于综合看多和看空的分析，结合市场环境，做出最优的投资决策。
你的决策注重风险收益比，追求稳健的长期回报。""",
            organization_id=organization_id
        )
        
        # 在 super().__init__() 之后设置 _llm_provider（避免被 Pydantic 清除）
        if llm_provider is None:
            llm_provider = get_llm_provider()
        object.__setattr__(self, '_llm_provider', llm_provider)
        
        logger.info(f"Initialized {self.name} agent")
    
    def make_decision(
        self,
        stock_code: str,
        stock_name: str,
        bull_analysis: str,
        bear_analysis: str,
        context: str = ""
    ) -> Dict[str, Any]:
        """
        综合双方观点，做出投资决策
        """
        prompt = f"""你是一位投资经理，请综合以下看多和看空观点，做出投资决策：

【股票信息】
代码：{stock_code}
名称：{stock_name}

【看多观点】
{bull_analysis}

【看空观点】
{bear_analysis}

【市场背景】
{context if context else "当前市场处于正常波动区间"}

请按以下结构给出最终决策：

## 1. 观点评估

### 看多方论点质量
- 评估看多论点的说服力（1-10分）
- 指出最有力的看多论据
- 指出看多方忽视的问题

### 看空方论点质量
- 评估看空论点的说服力（1-10分）
- 指出最有力的看空论据
- 指出看空方过于悲观的地方

## 2. 综合判断
- 当前股票的核心矛盾是什么
- 短期（1-3个月）和中长期（6-12个月）的观点

## 3. 投资决策

**最终评级**：[强烈推荐 / 推荐 / 中性 / 谨慎 / 回避]

**决策理由**：
（详细说明决策依据）

**建议操作**：
- 对于持仓者：持有/加仓/减仓/清仓
- 对于观望者：买入/观望/规避

**关键监测指标**：
- 列出需要持续关注的信号
- 什么情况下需要调整决策

## 4. 风险收益比
- 预期收益空间
- 潜在下行风险
- 风险收益比评估

请确保决策客观、理性，充分考虑双方观点。
"""
        
        try:
            response = self._llm_provider.invoke([
                {"role": "system", "content": f"你是{self.role}，{self.backstory}"},
                {"role": "user", "content": prompt}
            ])
            
            decision_text = response.content if hasattr(response, 'content') else str(response)
            
            # 提取评级
            rating = self._extract_rating(decision_text)
            
            return {
                "success": True,
                "agent_name": self.name,
                "agent_role": self.role,
                "decision": decision_text,
                "rating": rating,
                "timestamp": datetime.utcnow().isoformat()
            }
        
        except Exception as e:
            logger.error(f"Investment decision failed: {e}")
            return {
                "success": False,
                "agent_name": self.name,
                "error": str(e)
            }
    
    def _extract_rating(self, text: str) -> str:
        """从决策文本中提取评级"""
        import re
        
        ratings = ["强烈推荐", "推荐", "中性", "谨慎", "回避"]
        for rating in ratings:
            if rating in text:
                return rating
        return "中性"


class DebateWorkflow:
    """
    辩论工作流
    协调 Bull/Bear/InvestmentManager 进行多轮辩论
    """
    
    def __init__(self, llm_provider=None):
        self.bull_agent = BullResearcherAgent(llm_provider)
        self.bear_agent = BearResearcherAgent(llm_provider)
        self.manager_agent = InvestmentManagerAgent(llm_provider)
        
        # 执行轨迹记录
        self.trajectory = []
        
        logger.info("Initialized DebateWorkflow")
    
    async def run_debate(
        self,
        stock_code: str,
        stock_name: str,
        news_list: List[Dict[str, Any]],
        context: str = "",
        rounds: int = 1
    ) -> Dict[str, Any]:
        """
        执行完整的辩论流程
        
        Args:
            stock_code: 股票代码
            stock_name: 股票名称
            news_list: 相关新闻列表
            context: 额外上下文
            rounds: 辩论轮数
        
        Returns:
            辩论结果
        """
        start_time = datetime.utcnow()
        self.trajectory = []
        
        logger.info(f"🚀 辩论工作流开始: {stock_name}({stock_code}), 新闻数量={len(news_list)}")
        
        try:
            # 第一阶段：独立分析
            self._log_step("debate_start", {
                "stock_code": stock_code,
                "stock_name": stock_name,
                "news_count": len(news_list)
            })
            
            # Bull 分析
            logger.info("📈 开始看多分析 (BullResearcher)...")
            self._log_step("bull_analysis_start", {"agent": "BullResearcher"})
            bull_result = self.bull_agent.analyze(stock_code, stock_name, news_list, context)
            logger.info(f"📈 看多分析完成: success={bull_result.get('success', False)}")
            self._log_step("bull_analysis_complete", {
                "agent": "BullResearcher",
                "success": bull_result.get("success", False)
            })
            
            # Bear 分析
            logger.info("📉 开始看空分析 (BearResearcher)...")
            self._log_step("bear_analysis_start", {"agent": "BearResearcher"})
            bear_result = self.bear_agent.analyze(stock_code, stock_name, news_list, context)
            logger.info(f"📉 看空分析完成: success={bear_result.get('success', False)}")
            self._log_step("bear_analysis_complete", {
                "agent": "BearResearcher",
                "success": bear_result.get("success", False)
            })
            
            # 第二阶段：投资经理决策
            logger.info("⚖️ 开始投资经理决策 (InvestmentManager)...")
            self._log_step("decision_start", {"agent": "InvestmentManager"})
            decision_result = self.manager_agent.make_decision(
                stock_code=stock_code,
                stock_name=stock_name,
                bull_analysis=bull_result.get("analysis", ""),
                bear_analysis=bear_result.get("analysis", ""),
                context=context
            )
            logger.info(f"⚖️ 投资经理决策完成: rating={decision_result.get('rating', 'unknown')}")
            self._log_step("decision_complete", {
                "agent": "InvestmentManager",
                "rating": decision_result.get("rating", "unknown")
            })
            
            end_time = datetime.utcnow()
            execution_time = (end_time - start_time).total_seconds()
            
            logger.info(f"✅ 辩论工作流完成! 耗时={execution_time:.2f}秒, 评级={decision_result.get('rating', 'unknown')}")
            
            self._log_step("debate_complete", {
                "execution_time": execution_time,
                "final_rating": decision_result.get("rating", "unknown")
            })
            
            return {
                "success": True,
                "stock_code": stock_code,
                "stock_name": stock_name,
                "bull_analysis": bull_result,
                "bear_analysis": bear_result,
                "final_decision": decision_result,
                "trajectory": self.trajectory,
                "execution_time": execution_time,
                "timestamp": start_time.isoformat()
            }
        
        except Exception as e:
            logger.error(f"❌ 辩论工作流失败: {e}", exc_info=True)
            self._log_step("debate_failed", {"error": str(e)})
            return {
                "success": False,
                "error": str(e),
                "trajectory": self.trajectory
            }
    
    def _log_step(self, step_name: str, data: Dict[str, Any]):
        """记录执行步骤"""
        step = {
            "step": step_name,
            "timestamp": datetime.utcnow().isoformat(),
            "data": data
        }
        self.trajectory.append(step)
        logger.info(f"Debate step: {step_name} - {data}")


# 工厂函数
def create_debate_workflow(llm_provider=None) -> DebateWorkflow:
    """创建辩论工作流实例"""
    return DebateWorkflow(llm_provider)

