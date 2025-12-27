"""
搜索分析师智能体 (SearchAnalystAgent)

负责在辩论过程中动态搜集数据，支持多种数据源：
- AkShare: 财务指标、K线数据、资金流向、机构持仓
- BochaAI: 实时新闻搜索、分析师报告
- InteractiveCrawler: 多引擎网页搜索 (百度、搜狗、360等)
- Knowledge Base: 历史新闻和上下文 (向量数据库)
"""
import logging
import re
import asyncio
from typing import Dict, Any, List, Optional, ClassVar, Pattern
from datetime import datetime
from enum import Enum

from agenticx.core.agent import Agent
from ..services.llm_service import get_llm_provider
from ..services.stock_data_service import stock_data_service
from ..tools.bochaai_search import bochaai_search, SearchResult
from ..tools.interactive_crawler import InteractiveCrawler

logger = logging.getLogger(__name__)


class SearchSource(Enum):
    """搜索数据源类型"""
    AKSHARE = "akshare"           # AkShare 财务/行情数据
    BOCHAAI = "bochaai"           # BochaAI Web搜索
    BROWSER = "browser"           # 交互式浏览器搜索
    KNOWLEDGE_BASE = "kb"         # 内部知识库
    ALL = "all"                   # 所有来源


class SearchAnalystAgent(Agent):
    """
    搜索分析师智能体
    
    在辩论过程中被其他智能体调用，动态获取所需数据。
    支持解析结构化搜索请求，并返回格式化的数据。
    """
    
    # 搜索请求的正则模式 [SEARCH: "query" source:xxx]
    # 使用 ClassVar 避免 Pydantic 将其视为模型字段
    SEARCH_PATTERN: ClassVar[Pattern] = re.compile(
        r'\[SEARCH:\s*["\']([^"\']+)["\']\s*(?:source:(\w+))?\]',
        re.IGNORECASE
    )
    
    def __init__(self, llm_provider=None, organization_id: str = "finnews"):
        super().__init__(
            name="SearchAnalyst",
            role="搜索分析师",
            goal="根据辩论中的数据需求，快速从多个数据源获取相关信息",
            backstory="""你是一位专业的金融数据搜索专家，精通各类金融数据源的使用。
你的职责是：
1. 解析辩论智能体的数据请求
2. 选择最合适的数据源进行查询
3. 整理并格式化数据，使其便于辩论使用
4. 对数据质量进行初步评估

你能够访问的数据源包括：
- AkShare: 股票财务指标、K线行情、资金流向、机构持仓等
- BochaAI: 实时新闻搜索、财经报道
- 多引擎搜索: 百度资讯、搜狗、360等
- 内部知识库: 历史新闻和分析数据""",
            organization_id=organization_id
        )
        
        if llm_provider is None:
            llm_provider = get_llm_provider()
        object.__setattr__(self, '_llm_provider', llm_provider)
        
        # 初始化搜索工具
        self._interactive_crawler = InteractiveCrawler(timeout=20)
        
        logger.info(f"✅ Initialized {self.name} agent with multi-source search capabilities")
    
    def extract_search_requests(self, text: str) -> List[Dict[str, Any]]:
        """
        从文本中提取搜索请求
        
        支持格式:
        - [SEARCH: "query"]
        - [SEARCH: "query" source:akshare]
        - [SEARCH: "query" source:bochaai]
        - [SEARCH: "query" source:browser]
        
        Args:
            text: 包含搜索请求的文本
            
        Returns:
            搜索请求列表 [{"query": "...", "source": "..."}]
        """
        requests = []
        matches = self.SEARCH_PATTERN.findall(text)
        
        for match in matches:
            query = match[0].strip()
            source = match[1].lower() if match[1] else "all"
            
            # 验证 source
            valid_sources = [s.value for s in SearchSource]
            if source not in valid_sources:
                source = "all"
            
            requests.append({
                "query": query,
                "source": source
            })
            logger.info(f"🔍 提取搜索请求: query='{query}', source={source}")
        
        return requests
    
    async def search(
        self,
        query: str,
        source: str = "all",
        stock_code: Optional[str] = None,
        stock_name: Optional[str] = None,
        context: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        执行搜索请求
        
        Args:
            query: 搜索查询
            source: 数据源 (akshare, bochaai, browser, kb, all)
            stock_code: 股票代码 (用于 akshare 查询)
            stock_name: 股票名称 (用于新闻搜索)
            context: 额外上下文
            
        Returns:
            搜索结果字典
        """
        logger.info(f"🔍 SearchAnalyst: 执行搜索 query='{query}', source={source}")
        
        result = {
            "query": query,
            "source": source,
            "timestamp": datetime.utcnow().isoformat(),
            "data": {},
            "summary": "",
            "success": False
        }
        
        try:
            if source == SearchSource.AKSHARE.value or source == SearchSource.ALL.value:
                akshare_data = await self._search_akshare(query, stock_code)
                if akshare_data:
                    result["data"]["akshare"] = akshare_data
            
            if source == SearchSource.BOCHAAI.value or source == SearchSource.ALL.value:
                bochaai_data = await self._search_bochaai(query, stock_name)
                if bochaai_data:
                    result["data"]["bochaai"] = bochaai_data
            
            if source == SearchSource.BROWSER.value or source == SearchSource.ALL.value:
                browser_data = await self._search_browser(query)
                if browser_data:
                    result["data"]["browser"] = browser_data
            
            if source == SearchSource.KNOWLEDGE_BASE.value or source == SearchSource.ALL.value:
                kb_data = await self._search_knowledge_base(query, stock_code, stock_name)
                if kb_data:
                    result["data"]["knowledge_base"] = kb_data
            
            # 生成摘要
            if result["data"]:
                result["summary"] = await self._generate_summary(query, result["data"])
                result["success"] = True
            else:
                result["summary"] = f"未找到与'{query}'相关的数据"
            
        except Exception as e:
            logger.error(f"SearchAnalyst 搜索失败: {e}", exc_info=True)
            result["error"] = str(e)
        
        return result
    
    async def _search_akshare(
        self,
        query: str,
        stock_code: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """从 AkShare 获取数据"""
        if not stock_code:
            logger.debug("AkShare 搜索需要股票代码，跳过")
            return None
        
        data = {}
        query_lower = query.lower()
        
        try:
            # 根据查询内容决定获取哪些数据
            if any(kw in query_lower for kw in ["财务", "pe", "pb", "roe", "利润", "估值", "市盈", "市净"]):
                financial = await stock_data_service.get_financial_indicators(stock_code)
                if financial:
                    data["financial_indicators"] = financial
            
            if any(kw in query_lower for kw in ["资金", "主力", "流入", "流出", "散户", "机构"]):
                fund_flow = await stock_data_service.get_fund_flow(stock_code, days=10)
                if fund_flow:
                    data["fund_flow"] = fund_flow
            
            if any(kw in query_lower for kw in ["行情", "价格", "涨跌", "成交", "量"]):
                realtime = await stock_data_service.get_realtime_quote(stock_code)
                if realtime:
                    data["realtime_quote"] = realtime
            
            if any(kw in query_lower for kw in ["k线", "走势", "历史", "均线", "趋势"]):
                kline = await stock_data_service.get_kline_data(stock_code, period="daily", limit=30)
                if kline:
                    # 只返回最近10天的简要数据
                    data["kline_summary"] = {
                        "period": "daily",
                        "count": len(kline),
                        "latest": kline[-1] if kline else None,
                        "recent_5": kline[-5:] if len(kline) >= 5 else kline
                    }
            
            # 如果没有匹配到特定查询，获取综合数据
            if not data:
                context_data = await stock_data_service.get_debate_context(stock_code)
                if context_data:
                    data = context_data
            
            if data:
                logger.info(f"✅ AkShare 返回数据: {list(data.keys())}")
                return data
            
        except Exception as e:
            logger.warning(f"AkShare 搜索出错: {e}")
        
        return None
    
    async def _search_bochaai(
        self,
        query: str,
        stock_name: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """从 BochaAI 搜索新闻"""
        if not bochaai_search.is_available():
            logger.debug("BochaAI 未配置，跳过")
            return None
        
        try:
            # 构建搜索查询
            search_query = query
            if stock_name and stock_name not in query:
                search_query = f"{stock_name} {query}"
            
            results = bochaai_search.search(
                query=search_query,
                freshness="oneWeek",
                count=10
            )
            
            if results:
                news_list = [
                    {
                        "title": r.title,
                        "snippet": r.snippet[:200] if r.snippet else "",
                        "url": r.url,
                        "source": r.site_name or "unknown",
                        "date": r.date_published or ""
                    }
                    for r in results
                ]
                logger.info(f"✅ BochaAI 返回 {len(news_list)} 条新闻")
                return {"news": news_list, "count": len(news_list)}
        
        except Exception as e:
            logger.warning(f"BochaAI 搜索出错: {e}")
        
        return None
    
    async def _search_browser(self, query: str) -> Optional[Dict[str, Any]]:
        """使用交互式爬虫搜索"""
        try:
            loop = asyncio.get_event_loop()
            results = await loop.run_in_executor(
                None,
                lambda: self._interactive_crawler.interactive_search(
                    query=query,
                    engines=["baidu_news", "sogou"],
                    num_results=10,
                    search_type="news"
                )
            )
            
            if results:
                news_list = [
                    {
                        "title": r.get("title", ""),
                        "snippet": r.get("snippet", "")[:200],
                        "url": r.get("url", ""),
                        "source": "browser_search"
                    }
                    for r in results
                ]
                logger.info(f"✅ Browser 返回 {len(news_list)} 条结果")
                return {"search_results": news_list, "count": len(news_list)}
        
        except Exception as e:
            logger.warning(f"Browser 搜索出错: {e}")
        
        return None
    
    async def _search_knowledge_base(
        self,
        query: str,
        stock_code: Optional[str] = None,
        stock_name: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """从知识库搜索历史数据"""
        try:
            # 尝试导入 news_service（可能不存在）
            try:
                from ..services.news_service import news_service
            except ImportError:
                logger.debug("news_service 未配置，跳过知识库搜索")
                return None
            
            # 尝试从数据库获取相关新闻
            if stock_code and news_service:
                news_list = await news_service.get_news_by_stock(stock_code, limit=10)
                if news_list:
                    kb_news = [
                        {
                            "title": getattr(news, 'title', ''),
                            "content": (getattr(news, 'content', '') or '')[:300],
                            "source": getattr(news, 'source', ''),
                            "date": news.published_at.isoformat() if hasattr(news, 'published_at') and news.published_at else ""
                        }
                        for news in news_list
                    ]
                    logger.info(f"✅ KB 返回 {len(kb_news)} 条历史新闻")
                    return {"historical_news": kb_news, "count": len(kb_news)}
        
        except Exception as e:
            logger.debug(f"KB 搜索出错: {e}")
        
        return None
    
    async def _generate_summary(self, query: str, data: Dict[str, Any]) -> str:
        """生成数据摘要"""
        summary_parts = [f"## 搜索结果: {query}\n"]
        
        # AkShare 数据摘要
        if "akshare" in data:
            ak_data = data["akshare"]
            summary_parts.append("### 📊 财务/行情数据 (AkShare)\n")
            
            if "financial_indicators" in ak_data:
                fi = ak_data["financial_indicators"]
                summary_parts.append(f"- PE: {fi.get('pe_ratio', 'N/A')}, PB: {fi.get('pb_ratio', 'N/A')}")
                summary_parts.append(f"- ROE: {fi.get('roe', 'N/A')}%, 净利润同比: {fi.get('profit_yoy', 'N/A')}%")
            
            if "realtime_quote" in ak_data:
                rt = ak_data["realtime_quote"]
                summary_parts.append(f"- 当前价: {rt.get('price', 'N/A')}元, 涨跌幅: {rt.get('change_percent', 'N/A')}%")
            
            if "fund_flow" in ak_data:
                ff = ak_data["fund_flow"]
                main_net = ff.get('total_main_net', 0)
                trend = ff.get('main_flow_trend', 'N/A')
                summary_parts.append(f"- 资金流向: 近{ff.get('period_days', 5)}日主力{trend}")
            
            summary_parts.append("")
        
        # BochaAI 新闻摘要
        if "bochaai" in data:
            news = data["bochaai"].get("news", [])
            if news:
                summary_parts.append("### 📰 最新新闻 (BochaAI)\n")
                for i, n in enumerate(news[:5], 1):
                    summary_parts.append(f"{i}. **{n['title'][:50]}**")
                    if n.get('snippet'):
                        summary_parts.append(f"   {n['snippet'][:100]}...")
                summary_parts.append("")
        
        # Browser 搜索结果摘要
        if "browser" in data:
            results = data["browser"].get("search_results", [])
            if results:
                summary_parts.append("### 🌐 网页搜索结果\n")
                for i, r in enumerate(results[:5], 1):
                    summary_parts.append(f"{i}. {r['title'][:50]}")
                summary_parts.append("")
        
        # KB 历史数据摘要
        if "knowledge_base" in data:
            kb_news = data["knowledge_base"].get("historical_news", [])
            if kb_news:
                summary_parts.append("### 📚 历史资料 (知识库)\n")
                for i, n in enumerate(kb_news[:3], 1):
                    summary_parts.append(f"{i}. {n['title'][:50]}")
                summary_parts.append("")
        
        return "\n".join(summary_parts)
    
    async def process_debate_speech(
        self,
        speech_text: str,
        stock_code: str,
        stock_name: str,
        agent_name: str = "Unknown"
    ) -> Dict[str, Any]:
        """
        处理辩论发言中的搜索请求
        
        Args:
            speech_text: 辩论发言文本
            stock_code: 股票代码
            stock_name: 股票名称
            agent_name: 发言智能体名称
            
        Returns:
            处理结果，包含所有搜索结果和综合摘要
        """
        logger.info(f"🔍 SearchAnalyst: 处理 {agent_name} 的发言，检测搜索请求...")
        
        result = {
            "agent_name": agent_name,
            "requests_found": 0,
            "search_results": [],
            "combined_summary": "",
            "success": False
        }
        
        # 提取搜索请求
        requests = self.extract_search_requests(speech_text)
        result["requests_found"] = len(requests)
        
        if not requests:
            logger.info(f"📝 {agent_name} 的发言中未包含搜索请求")
            result["success"] = True
            return result
        
        logger.info(f"📋 从 {agent_name} 的发言中提取到 {len(requests)} 个搜索请求")
        
        # 并行执行所有搜索
        search_tasks = []
        for req in requests:
            task = self.search(
                query=req["query"],
                source=req["source"],
                stock_code=stock_code,
                stock_name=stock_name
            )
            search_tasks.append(task)
        
        search_results = await asyncio.gather(*search_tasks, return_exceptions=True)
        
        # 收集结果
        summaries = []
        for i, res in enumerate(search_results):
            if isinstance(res, Exception):
                logger.error(f"搜索请求 {i+1} 失败: {res}")
                continue
            
            if res.get("success"):
                result["search_results"].append(res)
                summaries.append(res.get("summary", ""))
        
        # 生成综合摘要
        if summaries:
            result["combined_summary"] = "\n---\n".join(summaries)
            result["success"] = True
        
        logger.info(f"✅ SearchAnalyst: 为 {agent_name} 完成 {len(result['search_results'])} 个搜索请求")
        
        return result
    
    async def smart_data_supplement(
        self,
        stock_code: str,
        stock_name: str,
        existing_context: str,
        debate_history: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        智能数据补充
        
        分析辩论历史和现有上下文，主动识别缺失的关键数据并补充
        
        Args:
            stock_code: 股票代码
            stock_name: 股票名称
            existing_context: 现有上下文
            debate_history: 辩论历史
            
        Returns:
            补充的数据和摘要
        """
        logger.info(f"🧠 SearchAnalyst: 智能分析数据缺口...")
        
        # 使用 LLM 分析需要什么数据
        analysis_prompt = f"""你是一位金融数据分析专家。请分析以下辩论情况，判断还需要哪些数据支撑：

【股票】{stock_name} ({stock_code})

【现有数据】
{existing_context[:1500]}

【辩论历史】
{self._format_debate_history(debate_history[-4:])}

请判断：
1. 看多方缺少什么关键数据？
2. 看空方缺少什么关键数据？
3. 还需要搜索什么信息？

请按以下格式输出需要搜索的内容（每行一个）：
[SEARCH: "搜索内容" source:数据源]

可用数据源：akshare（财务/行情）, bochaai（新闻）, browser（网页搜索）

只输出3-5个最关键的搜索请求。"""

        try:
            response = self._llm_provider.invoke([
                {"role": "system", "content": f"你是{self.role}，{self.backstory}"},
                {"role": "user", "content": analysis_prompt}
            ])
            
            llm_response = response.content if hasattr(response, 'content') else str(response)
            
            # 处理 LLM 建议的搜索
            return await self.process_debate_speech(
                speech_text=llm_response,
                stock_code=stock_code,
                stock_name=stock_name,
                agent_name="SmartSupplement"
            )
            
        except Exception as e:
            logger.error(f"智能数据补充失败: {e}")
            return {"success": False, "error": str(e)}
    
    def _format_debate_history(self, history: List[Dict[str, Any]]) -> str:
        """格式化辩论历史"""
        if not history:
            return "（暂无辩论历史）"
        
        lines = []
        for item in history:
            agent = item.get("agent", "Unknown")
            content = item.get("content", "")[:300]
            lines.append(f"[{agent}]: {content}")
        
        return "\n\n".join(lines)


# 工厂函数
def create_search_analyst(llm_provider=None) -> SearchAnalystAgent:
    """创建搜索分析师实例"""
    return SearchAnalystAgent(llm_provider=llm_provider)

