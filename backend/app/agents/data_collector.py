"""
数据专员智能体

负责在辩论前搜集和整理相关数据资料，包括：
- 新闻数据（从数据库或BochaAI搜索）
- 财务数据（从AkShare获取）
- 行情数据（实时行情、K线等）
"""
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

from agenticx.core.agent import Agent
from ..services.llm_service import get_llm_provider

logger = logging.getLogger(__name__)


class DataCollectorAgent(Agent):
    """数据专员智能体"""
    
    def __init__(self, llm_provider=None, organization_id: str = "finnews"):
        super().__init__(
            name="DataCollector",
            role="数据专员",
            goal="搜集和整理股票相关的新闻、财务和行情数据，为辩论提供全面的信息支持",
            backstory="""你是一位专业的金融数据分析师，擅长从多个数据源搜集和整理信息。
你的职责是在辩论开始前，为Bull/Bear研究员提供全面、准确、及时的数据支持。
你需要：
1. 搜集最新的相关新闻
2. 获取关键财务指标
3. 分析资金流向
4. 整理行情数据
你的工作质量直接影响辩论的深度和专业性。""",
            organization_id=organization_id
        )
        if llm_provider is None:
            llm_provider = get_llm_provider()
        object.__setattr__(self, '_llm_provider', llm_provider)
        logger.info(f"Initialized {self.name} agent")
    
    async def collect_data(
        self,
        stock_code: str,
        stock_name: str,
        data_requirements: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        搜集股票相关数据
        
        Args:
            stock_code: 股票代码
            stock_name: 股票名称
            data_requirements: 数据需求配置
            
        Returns:
            包含各类数据的字典
        """
        logger.info(f"📊 DataCollector: 开始搜集 {stock_name}({stock_code}) 的数据...")
        
        result = {
            "stock_code": stock_code,
            "stock_name": stock_name,
            "collected_at": datetime.utcnow().isoformat(),
            "news": [],
            "financial": {},
            "fund_flow": {},
            "realtime_quote": {},
            "summary": ""
        }
        
        try:
            # 1. 搜集新闻数据
            news_data = await self._collect_news(stock_code, stock_name)
            result["news"] = news_data
            logger.info(f"📰 DataCollector: 搜集到 {len(news_data)} 条新闻")
            
            # 2. 搜集财务数据
            financial_data = await self._collect_financial(stock_code)
            result["financial"] = financial_data
            logger.info(f"💰 DataCollector: 搜集到财务数据")
            
            # 3. 搜集资金流向
            fund_flow = await self._collect_fund_flow(stock_code)
            result["fund_flow"] = fund_flow
            logger.info(f"💸 DataCollector: 搜集到资金流向数据")
            
            # 4. 搜集实时行情
            realtime = await self._collect_realtime_quote(stock_code)
            result["realtime_quote"] = realtime
            logger.info(f"📈 DataCollector: 搜集到实时行情")
            
            # 5. 生成数据摘要
            result["summary"] = await self._generate_summary(result)
            logger.info(f"📋 DataCollector: 数据摘要生成完成")
            
        except Exception as e:
            logger.error(f"DataCollector 搜集数据时出错: {e}", exc_info=True)
            result["error"] = str(e)
        
        return result
    
    async def _collect_news(self, stock_code: str, stock_name: str) -> List[Dict[str, Any]]:
        """搜集新闻数据"""
        from ..services.news_service import news_service
        
        try:
            # 从数据库获取已有新闻
            news_list = await news_service.get_news_by_stock(stock_code, limit=20)
            return [
                {
                    "title": news.title,
                    "content": news.content[:500] if news.content else "",
                    "source": news.source,
                    "published_at": news.published_at.isoformat() if news.published_at else None,
                    "sentiment": news.sentiment
                }
                for news in news_list
            ]
        except Exception as e:
            logger.warning(f"从数据库获取新闻失败: {e}")
            return []
    
    async def _collect_financial(self, stock_code: str) -> Dict[str, Any]:
        """搜集财务数据"""
        from ..services.stock_data_service import stock_data_service
        
        try:
            return await stock_data_service.get_financial_indicators(stock_code) or {}
        except Exception as e:
            logger.warning(f"获取财务数据失败: {e}")
            return {}
    
    async def _collect_fund_flow(self, stock_code: str) -> Dict[str, Any]:
        """搜集资金流向数据"""
        from ..services.stock_data_service import stock_data_service
        
        try:
            return await stock_data_service.get_fund_flow(stock_code) or {}
        except Exception as e:
            logger.warning(f"获取资金流向失败: {e}")
            return {}
    
    async def _collect_realtime_quote(self, stock_code: str) -> Dict[str, Any]:
        """搜集实时行情"""
        from ..services.stock_data_service import stock_data_service
        
        try:
            return await stock_data_service.get_realtime_quote(stock_code) or {}
        except Exception as e:
            logger.warning(f"获取实时行情失败: {e}")
            return {}
    
    async def _generate_summary(self, data: Dict[str, Any]) -> str:
        """使用LLM生成数据摘要"""
        try:
            # 准备摘要内容
            news_summary = ""
            if data.get("news"):
                news_titles = [n["title"] for n in data["news"][:5]]
                news_summary = f"最新新闻（{len(data['news'])}条）:\n" + "\n".join(f"- {t}" for t in news_titles)
            
            financial_summary = ""
            if data.get("financial"):
                f = data["financial"]
                financial_summary = f"""财务指标:
- PE: {f.get('pe', 'N/A')}
- PB: {f.get('pb', 'N/A')}
- ROE: {f.get('roe', 'N/A')}
- 净利润增长率: {f.get('net_profit_growth', 'N/A')}"""
            
            fund_flow_summary = ""
            if data.get("fund_flow"):
                ff = data["fund_flow"]
                fund_flow_summary = f"""资金流向:
- 主力净流入: {ff.get('main_net_inflow', 'N/A')}
- 散户净流入: {ff.get('retail_net_inflow', 'N/A')}"""
            
            realtime_summary = ""
            if data.get("realtime_quote"):
                rt = data["realtime_quote"]
                realtime_summary = f"""实时行情:
- 当前价: {rt.get('price', 'N/A')}
- 涨跌幅: {rt.get('change_pct', 'N/A')}%
- 成交量: {rt.get('volume', 'N/A')}"""
            
            summary = f"""## {data['stock_name']}({data['stock_code']}) 数据摘要

{realtime_summary}

{financial_summary}

{fund_flow_summary}

{news_summary}

数据搜集时间: {data['collected_at']}"""
            
            return summary
            
        except Exception as e:
            logger.error(f"生成数据摘要失败: {e}")
            return f"数据搜集完成，但生成摘要时出错: {e}"
    
    async def analyze_data_quality(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """分析数据质量和完整性"""
        quality = {
            "score": 0,
            "max_score": 100,
            "details": [],
            "recommendations": []
        }
        
        # 检查新闻数据
        news_count = len(data.get("news", []))
        if news_count >= 10:
            quality["score"] += 30
            quality["details"].append(f"✅ 新闻数据充足（{news_count}条）")
        elif news_count >= 5:
            quality["score"] += 20
            quality["details"].append(f"⚠️ 新闻数据较少（{news_count}条）")
            quality["recommendations"].append("建议搜集更多新闻以支持分析")
        elif news_count > 0:
            quality["score"] += 10
            quality["details"].append(f"⚠️ 新闻数据不足（{news_count}条）")
            quality["recommendations"].append("新闻数据偏少，分析可能不够全面")
        else:
            quality["details"].append("❌ 无新闻数据")
            quality["recommendations"].append("缺少新闻数据，建议先进行定向爬取")
        
        # 检查财务数据
        if data.get("financial"):
            quality["score"] += 25
            quality["details"].append("✅ 财务数据完整")
        else:
            quality["details"].append("❌ 缺少财务数据")
            quality["recommendations"].append("无法获取财务指标")
        
        # 检查资金流向
        if data.get("fund_flow"):
            quality["score"] += 20
            quality["details"].append("✅ 资金流向数据完整")
        else:
            quality["details"].append("⚠️ 缺少资金流向数据")
        
        # 检查实时行情
        if data.get("realtime_quote"):
            quality["score"] += 25
            quality["details"].append("✅ 实时行情数据完整")
        else:
            quality["details"].append("⚠️ 缺少实时行情数据")
        
        return quality


# 快速分析师（用于快速分析模式）
class QuickAnalystAgent(Agent):
    """快速分析师智能体"""
    
    def __init__(self, llm_provider=None, organization_id: str = "finnews"):
        super().__init__(
            name="QuickAnalyst",
            role="快速分析师",
            goal="快速综合多角度给出投资建议",
            backstory="""你是一位经验丰富的量化分析师，擅长快速分析和决策。
你能够在短时间内综合考虑多空因素，给出简洁明了的投资建议。
你的分析风格是：快速、准确、实用。""",
            organization_id=organization_id
        )
        if llm_provider is None:
            llm_provider = get_llm_provider()
        object.__setattr__(self, '_llm_provider', llm_provider)
        logger.info(f"Initialized {self.name} agent")
    
    async def quick_analyze(
        self,
        stock_code: str,
        stock_name: str,
        context: str
    ) -> Dict[str, Any]:
        """快速分析"""
        # 获取当前系统时间
        current_time = datetime.now().strftime("%Y年%m月%d日 %H:%M")
        
        prompt = f"""请对 {stock_name}({stock_code}) 进行快速投资分析。

【当前时间】
{current_time}

背景资料:
{context}

请在1分钟内给出：
1. 核心观点（一句话）
2. 看多因素（3点）
3. 看空因素（3点）
4. 投资建议（买入/持有/卖出）
5. 目标价位和止损价位

请用简洁的语言，直接给出结论。"""

        try:
            response = await self._llm_provider.chat(prompt)
            return {
                "success": True,
                "analysis": response,
                "timestamp": datetime.utcnow().isoformat()
            }
        except Exception as e:
            logger.error(f"Quick analysis failed: {e}")
            return {
                "success": False,
                "error": str(e)
            }

