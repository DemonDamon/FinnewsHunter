"""
智能体模块
"""
from .news_analyst import NewsAnalystAgent, create_news_analyst
from .debate_agents import (
    BullResearcherAgent,
    BearResearcherAgent,
    InvestmentManagerAgent,
    DebateWorkflow,
    create_debate_workflow,
)
from .data_collector_v2 import DataCollectorAgentV2, QuickAnalystAgent, create_data_collector
from .orchestrator import DebateOrchestrator, create_orchestrator

__all__ = [
    "NewsAnalystAgent",
    "create_news_analyst",
    "BullResearcherAgent",
    "BearResearcherAgent",
    "InvestmentManagerAgent",
    "DebateWorkflow",
    "create_debate_workflow",
    "DataCollectorAgentV2",
    "QuickAnalystAgent",
    "create_data_collector",
    "DebateOrchestrator",
    "create_orchestrator",
]

