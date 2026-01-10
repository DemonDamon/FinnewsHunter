"""
数据专员智能体 V2 (DataCollectorAgent)

统一负责所有数据获取任务，支持：
- 辩论前的初始数据收集
- 辩论中的动态数据补充
- 用户追问时的按需搜索

核心特性：
1. 计划/执行分离：先生成搜索计划，用户确认后再执行
2. 多数据源支持：AkShare、BochaAI、网页搜索、知识库
3. 智能意图识别：根据用户问题自动选择数据源
"""
import logging
import re
import asyncio
from typing import Dict, Any, List, Optional, ClassVar, Pattern
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field

from agenticx.core.agent import Agent
from ..services.llm_service import get_llm_provider
from ..services.stock_data_service import stock_data_service
from ..tools.bochaai_search import bochaai_search, SearchResult
from ..tools.interactive_crawler import InteractiveCrawler

logger = logging.getLogger(__name__)


class SearchSource(str, Enum):
    """搜索数据源类型"""
    AKSHARE = "akshare"           # AkShare 财务/行情数据
    BOCHAAI = "bochaai"           # BochaAI Web搜索
    BROWSER = "browser"           # 交互式浏览器搜索
    KNOWLEDGE_BASE = "kb"         # 内部知识库
    ALL = "all"                   # 所有来源


class SearchTask(BaseModel):
    """单个搜索任务"""
    id: str = Field(..., description="任务ID")
    source: SearchSource = Field(..., description="数据源")
    query: str = Field(..., description="搜索查询")
    description: str = Field("", description="任务描述（用于展示给用户）")
    data_type: Optional[str] = Field(None, description="数据类型（如 financial, news, kline）")
    icon: str = Field("🔍", description="图标（用于UI展示）")
    estimated_time: int = Field(3, description="预计耗时（秒）")


class SearchPlan(BaseModel):
    """搜索计划"""
    plan_id: str = Field(..., description="计划ID")
    stock_code: str = Field(..., description="股票代码")
    stock_name: str = Field("", description="股票名称")
    user_query: str = Field(..., description="用户原始问题")
    tasks: List[SearchTask] = Field(default_factory=list, description="搜索任务列表")
    total_estimated_time: int = Field(0, description="总预计耗时（秒）")
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    status: str = Field("pending", description="状态：pending, confirmed, executing, completed, cancelled")


class SearchResult(BaseModel):
    """搜索结果"""
    task_id: str
    source: str
    success: bool
    data: Dict[str, Any] = Field(default_factory=dict)
    summary: str = ""
    error: Optional[str] = None
    execution_time: float = 0


class DataCollectorAgentV2(Agent):
    """
    数据专员智能体 V2
    
    支持"确认优先"模式：
    1. 用户 @数据专员 提问
    2. 生成搜索计划（不执行）
    3. 用户确认后执行
    4. 返回结果
    """
    
    # 关键词到数据源的映射
    KEYWORD_SOURCE_MAP: ClassVar[Dict[str, tuple]] = {
        # 财务相关 -> AkShare
        "财务": (SearchSource.AKSHARE, "financial", "📊"),
        "pe": (SearchSource.AKSHARE, "financial", "📊"),
        "pb": (SearchSource.AKSHARE, "financial", "📊"),
        "roe": (SearchSource.AKSHARE, "financial", "📊"),
        "利润": (SearchSource.AKSHARE, "financial", "📊"),
        "营收": (SearchSource.AKSHARE, "financial", "📊"),
        "估值": (SearchSource.AKSHARE, "financial", "📊"),
        "市盈": (SearchSource.AKSHARE, "financial", "📊"),
        "市净": (SearchSource.AKSHARE, "financial", "📊"),
        "报表": (SearchSource.AKSHARE, "financial", "📊"),
        
        # 资金/行情 -> AkShare
        "资金": (SearchSource.AKSHARE, "fund_flow", "💰"),
        "主力": (SearchSource.AKSHARE, "fund_flow", "💰"),
        "流入": (SearchSource.AKSHARE, "fund_flow", "💰"),
        "流出": (SearchSource.AKSHARE, "fund_flow", "💰"),
        "行情": (SearchSource.AKSHARE, "realtime", "📈"),
        "价格": (SearchSource.AKSHARE, "realtime", "📈"),
        "涨跌": (SearchSource.AKSHARE, "realtime", "📈"),
        "k线": (SearchSource.AKSHARE, "kline", "📈"),
        "走势": (SearchSource.AKSHARE, "kline", "📈"),
        
        # 新闻相关 -> BochaAI
        "新闻": (SearchSource.BOCHAAI, "news", "📰"),
        "资讯": (SearchSource.BOCHAAI, "news", "📰"),
        "报道": (SearchSource.BOCHAAI, "news", "📰"),
        "公告": (SearchSource.BOCHAAI, "news", "📰"),
        "消息": (SearchSource.BOCHAAI, "news", "📰"),
        
        # 上下游/产业链 -> 多源搜索
        "上下游": (SearchSource.BROWSER, "industry", "🔗"),
        "供应链": (SearchSource.BROWSER, "industry", "🔗"),
        "客户": (SearchSource.BROWSER, "industry", "🔗"),
        "供应商": (SearchSource.BROWSER, "industry", "🔗"),
        "合作": (SearchSource.BROWSER, "industry", "🔗"),
        "产业链": (SearchSource.BROWSER, "industry", "🔗"),
    }
    
    def __init__(self, llm_provider=None, organization_id: str = "finnews"):
        super().__init__(
            name="DataCollector",
            role="数据专员",
            goal="根据用户需求，从多个数据源搜集和整理相关信息，支持辩论前准备和辩论中追问",
            backstory="""你是一位专业的金融数据专家，精通各类金融数据源的使用。
你的职责是：
1. 理解用户的数据需求
2. 制定合理的搜索计划
3. 从多个数据源获取数据
4. 整理并格式化数据

你能够访问的数据源包括：
- AkShare: 股票财务指标、K线行情、资金流向等
- BochaAI: 实时新闻搜索、财经报道
- 网页搜索: 百度资讯、搜狗等
- 知识库: 历史新闻和分析数据""",
            organization_id=organization_id
        )
        
        if llm_provider is None:
            llm_provider = get_llm_provider()
        object.__setattr__(self, '_llm_provider', llm_provider)
        
        # 初始化搜索工具
        self._interactive_crawler = InteractiveCrawler(timeout=20)
        
        logger.info(f"✅ Initialized DataCollectorV2 with multi-source search capabilities")
    
    async def generate_search_plan(
        self,
        query: str,
        stock_code: str,
        stock_name: str = ""
    ) -> SearchPlan:
        """
        生成搜索计划（不执行）
        
        根据用户问题分析需要哪些数据，生成待确认的搜索计划
        
        Args:
            query: 用户问题
            stock_code: 股票代码
            stock_name: 股票名称
            
        Returns:
            SearchPlan 对象
        """
        logger.info(f"📋 DataCollector: 为 '{query}' 生成搜索计划...")
        
        plan_id = f"plan_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{stock_code}"
        
        plan = SearchPlan(
            plan_id=plan_id,
            stock_code=stock_code,
            stock_name=stock_name or stock_code,
            user_query=query,
            tasks=[],
            status="pending"
        )
        
        query_lower = query.lower()
        
        # 1. 基于关键词匹配生成任务
        matched_sources = set()
        for keyword, (source, data_type, icon) in self.KEYWORD_SOURCE_MAP.items():
            if keyword in query_lower:
                if (source, data_type) not in matched_sources:
                    matched_sources.add((source, data_type))
                    task = self._create_task(
                        source=source,
                        data_type=data_type,
                        icon=icon,
                        query=query,
                        stock_code=stock_code,
                        stock_name=stock_name
                    )
                    plan.tasks.append(task)
        
        # 2. 如果没有匹配到任何关键词，使用 LLM 分析
        if not plan.tasks:
            plan.tasks = await self._analyze_with_llm(query, stock_code, stock_name)
        
        # 3. 如果还是没有任务，添加默认的综合搜索
        if not plan.tasks:
            plan.tasks = [
                SearchTask(
                    id=f"task_{plan_id}_1",
                    source=SearchSource.BOCHAAI,
                    query=f"{stock_name or stock_code} {query}",
                    description=f"搜索 {stock_name} 相关新闻",
                    icon="📰",
                    estimated_time=3
                ),
                SearchTask(
                    id=f"task_{plan_id}_2",
                    source=SearchSource.AKSHARE,
                    query=query,
                    description="获取最新财务和行情数据",
                    data_type="overview",
                    icon="📊",
                    estimated_time=2
                )
            ]
        
        # 计算总耗时
        plan.total_estimated_time = sum(t.estimated_time for t in plan.tasks)
        
        logger.info(f"✅ 生成搜索计划: {len(plan.tasks)} 个任务，预计耗时 {plan.total_estimated_time}s")
        
        return plan
    
    def _create_task(
        self,
        source: SearchSource,
        data_type: str,
        icon: str,
        query: str,
        stock_code: str,
        stock_name: str
    ) -> SearchTask:
        """创建搜索任务"""
        task_id = f"task_{datetime.utcnow().strftime('%H%M%S%f')}"
        
        # 根据数据类型生成描述
        descriptions = {
            "financial": f"获取 {stock_name or stock_code} 财务指标（PE/PB/ROE等）",
            "fund_flow": f"获取 {stock_name or stock_code} 资金流向（主力/散户）",
            "realtime": f"获取 {stock_name or stock_code} 实时行情",
            "kline": f"获取 {stock_name or stock_code} K线走势",
            "news": f"搜索 {stock_name or stock_code} 最新新闻",
            "industry": f"搜索 {stock_name or stock_code} 产业链/上下游信息",
        }
        
        # 根据数据类型生成查询
        queries = {
            "financial": stock_code,
            "fund_flow": stock_code,
            "realtime": stock_code,
            "kline": stock_code,
            "news": f"{stock_name or stock_code} {query}",
            "industry": f"{stock_name or stock_code} {query}",
        }
        
        return SearchTask(
            id=task_id,
            source=source,
            query=queries.get(data_type, query),
            description=descriptions.get(data_type, f"搜索: {query}"),
            data_type=data_type,
            icon=icon,
            estimated_time=3 if source != SearchSource.BROWSER else 5
        )
    
    async def _analyze_with_llm(
        self,
        query: str,
        stock_code: str,
        stock_name: str
    ) -> List[SearchTask]:
        """使用 LLM 分析需要哪些数据"""
        try:
            prompt = f"""分析以下用户问题，判断需要搜索哪些数据：

用户问题: "{query}"
股票: {stock_name}({stock_code})

可用数据源:
1. akshare - 财务数据（PE/PB/ROE等）、资金流向、实时行情、K线
2. bochaai - 新闻搜索、财经报道
3. browser - 网页搜索（适合搜索产业链、上下游、合作方等）
4. kb - 历史新闻数据库

请返回需要搜索的内容，格式如下（每行一个）:
SOURCE:数据源|TYPE:数据类型|QUERY:搜索词|DESC:描述

示例:
SOURCE:bochaai|TYPE:news|QUERY:ST国华 上下游|DESC:搜索ST国华上下游相关新闻
SOURCE:akshare|TYPE:financial|QUERY:002074|DESC:获取国轩高科财务数据

只输出2-4个最相关的搜索任务。"""

            response = self._llm_provider.invoke([
                {"role": "system", "content": "你是数据搜索专家，帮助分析需要哪些数据。"},
                {"role": "user", "content": prompt}
            ])
            
            content = response.content if hasattr(response, 'content') else str(response)
            
            tasks = []
            for line in content.strip().split('\n'):
                if 'SOURCE:' in line:
                    try:
                        parts = {}
                        for part in line.split('|'):
                            if ':' in part:
                                key, value = part.split(':', 1)
                                parts[key.strip().upper()] = value.strip()
                        
                        if 'SOURCE' in parts:
                            source_str = parts['SOURCE'].lower()
                            source = SearchSource(source_str) if source_str in [s.value for s in SearchSource] else SearchSource.BOCHAAI
                            
                            tasks.append(SearchTask(
                                id=f"task_llm_{len(tasks)+1}",
                                source=source,
                                query=parts.get('QUERY', query),
                                description=parts.get('DESC', f"搜索: {query}"),
                                data_type=parts.get('TYPE', 'general'),
                                icon=self._get_icon_for_source(source),
                                estimated_time=3
                            ))
                    except Exception as e:
                        logger.debug(f"解析 LLM 响应行失败: {e}")
            
            return tasks
            
        except Exception as e:
            logger.warning(f"LLM 分析失败: {e}")
            return []
    
    def _get_icon_for_source(self, source: SearchSource) -> str:
        """获取数据源对应的图标"""
        icons = {
            SearchSource.AKSHARE: "📊",
            SearchSource.BOCHAAI: "📰",
            SearchSource.BROWSER: "🌐",
            SearchSource.KNOWLEDGE_BASE: "📚",
            SearchSource.ALL: "🔍"
        }
        return icons.get(source, "🔍")
    
    async def execute_search_plan(
        self,
        plan: SearchPlan
    ) -> Dict[str, Any]:
        """
        执行搜索计划
        
        Args:
            plan: 已确认的搜索计划
            
        Returns:
            搜索结果汇总
        """
        logger.info(f"🚀 DataCollector: 开始执行搜索计划 {plan.plan_id}...")
        
        plan.status = "executing"
        start_time = datetime.utcnow()
        
        results = {
            "plan_id": plan.plan_id,
            "stock_code": plan.stock_code,
            "stock_name": plan.stock_name,
            "user_query": plan.user_query,
            "task_results": [],
            "combined_data": {},
            "summary": "",
            "success": False,
            "execution_time": 0
        }
        
        # 并行执行所有任务
        async_tasks = []
        for task in plan.tasks:
            async_tasks.append(self._execute_task(task, plan.stock_code, plan.stock_name))
        
        task_results = await asyncio.gather(*async_tasks, return_exceptions=True)
        
        # 收集结果
        for i, result in enumerate(task_results):
            if isinstance(result, Exception):
                logger.error(f"任务执行失败: {result}")
                results["task_results"].append(SearchResult(
                    task_id=plan.tasks[i].id,
                    source=plan.tasks[i].source.value,
                    success=False,
                    error=str(result)
                ).dict())
            else:
                results["task_results"].append(result.dict() if hasattr(result, 'dict') else result)
                if result.get("success"):
                    # 合并数据
                    source = result.get("source", "unknown")
                    if source not in results["combined_data"]:
                        results["combined_data"][source] = {}
                    results["combined_data"][source].update(result.get("data", {}))
        
        # 生成综合摘要
        results["summary"] = await self._generate_combined_summary(
            plan.user_query,
            results["combined_data"],
            plan.stock_name
        )
        
        # 计算执行时间
        end_time = datetime.utcnow()
        results["execution_time"] = (end_time - start_time).total_seconds()
        results["success"] = any(r.get("success") for r in results["task_results"])
        
        plan.status = "completed"
        
        logger.info(f"✅ 搜索计划执行完成，耗时 {results['execution_time']:.1f}s")
        
        return results
    
    async def _execute_task(
        self,
        task: SearchTask,
        stock_code: str,
        stock_name: str
    ) -> Dict[str, Any]:
        """执行单个搜索任务"""
        logger.info(f"🔍 执行任务: {task.description}")
        
        start_time = datetime.utcnow()
        result = {
            "task_id": task.id,
            "source": task.source.value,
            "success": False,
            "data": {},
            "summary": "",
            "execution_time": 0
        }
        
        try:
            if task.source == SearchSource.AKSHARE:
                data = await self._search_akshare(task.query, stock_code, task.data_type)
                result["data"] = data or {}
                result["success"] = bool(data)
                
            elif task.source == SearchSource.BOCHAAI:
                data = await self._search_bochaai(task.query, stock_name)
                result["data"] = data or {}
                result["success"] = bool(data)
                
            elif task.source == SearchSource.BROWSER:
                data = await self._search_browser(task.query)
                result["data"] = data or {}
                result["success"] = bool(data)
                
            elif task.source == SearchSource.KNOWLEDGE_BASE:
                data = await self._search_knowledge_base(task.query, stock_code)
                result["data"] = data or {}
                result["success"] = bool(data)
            
        except Exception as e:
            logger.error(f"任务 {task.id} 执行失败: {e}")
            result["error"] = str(e)
        
        end_time = datetime.utcnow()
        result["execution_time"] = (end_time - start_time).total_seconds()
        
        return result
    
    async def _search_akshare(
        self,
        query: str,
        stock_code: str,
        data_type: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """从 AkShare 获取数据"""
        data = {}
        
        try:
            if data_type == "financial" or data_type == "overview":
                financial = await stock_data_service.get_financial_indicators(stock_code)
                if financial:
                    data["financial_indicators"] = financial
            
            if data_type == "fund_flow" or data_type == "overview":
                fund_flow = await stock_data_service.get_fund_flow(stock_code, days=10)
                if fund_flow:
                    data["fund_flow"] = fund_flow
            
            if data_type == "realtime" or data_type == "overview":
                realtime = await stock_data_service.get_realtime_quote(stock_code)
                if realtime:
                    data["realtime_quote"] = realtime
            
            if data_type == "kline":
                kline = await stock_data_service.get_kline_data(stock_code, period="daily", limit=30)
                if kline:
                    data["kline_summary"] = {
                        "period": "daily",
                        "count": len(kline),
                        "latest": kline[-1] if kline else None,
                        "recent_5": kline[-5:] if len(kline) >= 5 else kline
                    }
            
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
            results = bochaai_search.search(
                query=query,
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
        stock_code: str
    ) -> Optional[Dict[str, Any]]:
        """从知识库搜索历史数据"""
        try:
            from ..services.news_service import news_service
            
            if stock_code and news_service:
                news_list = await news_service.get_news_by_stock(stock_code, limit=10)
                if news_list:
                    kb_news = [
                        {
                            "title": getattr(news, 'title', ''),
                            "content": (getattr(news, 'content', '') or '')[:300],
                            "source": getattr(news, 'source', ''),
                            "date": news.publish_time.isoformat() if hasattr(news, 'publish_time') and news.publish_time else ""
                        }
                        for news in news_list
                    ]
                    logger.info(f"✅ KB 返回 {len(kb_news)} 条历史新闻")
                    return {"historical_news": kb_news, "count": len(kb_news)}
        
        except Exception as e:
            logger.debug(f"KB 搜索出错: {e}")
        
        return None
    
    async def _generate_combined_summary(
        self,
        query: str,
        data: Dict[str, Any],
        stock_name: str
    ) -> str:
        """生成综合摘要"""
        summary_parts = [f"## 搜索结果: {query}\n"]
        summary_parts.append(f"**股票**: {stock_name}\n")
        
        # AkShare 数据
        if "akshare" in data:
            ak_data = data["akshare"]
            summary_parts.append("### 📊 财务/行情数据\n")
            
            if "financial_indicators" in ak_data:
                fi = ak_data["financial_indicators"]
                summary_parts.append(f"- PE: {fi.get('pe_ratio', 'N/A')}, PB: {fi.get('pb_ratio', 'N/A')}")
                summary_parts.append(f"- ROE: {fi.get('roe', 'N/A')}%")
            
            if "realtime_quote" in ak_data:
                rt = ak_data["realtime_quote"]
                summary_parts.append(f"- 当前价: {rt.get('price', 'N/A')}元, 涨跌幅: {rt.get('change_percent', 'N/A')}%")
            
            if "fund_flow" in ak_data:
                ff = ak_data["fund_flow"]
                summary_parts.append(f"- 资金流向: {ff.get('main_flow_trend', 'N/A')}")
            
            summary_parts.append("")
        
        # BochaAI 新闻
        if "bochaai" in data:
            news = data["bochaai"].get("news", [])
            if news:
                summary_parts.append("### 📰 最新新闻\n")
                for i, n in enumerate(news[:5], 1):
                    summary_parts.append(f"{i}. **{n['title'][:50]}**")
                    if n.get('snippet'):
                        summary_parts.append(f"   {n['snippet'][:100]}...")
                summary_parts.append("")
        
        # Browser 结果
        if "browser" in data:
            results = data["browser"].get("search_results", [])
            if results:
                summary_parts.append("### 🌐 网页搜索结果\n")
                for i, r in enumerate(results[:5], 1):
                    summary_parts.append(f"{i}. {r['title'][:50]}")
                summary_parts.append("")
        
        # KB 历史数据
        if "kb" in data:
            kb_news = data["kb"].get("historical_news", [])
            if kb_news:
                summary_parts.append("### 📚 历史资料\n")
                for i, n in enumerate(kb_news[:3], 1):
                    summary_parts.append(f"{i}. {n['title'][:50]}")
                summary_parts.append("")
        
        return "\n".join(summary_parts)
    
    # ============ 兼容旧 API ============
    
    async def collect_data(
        self,
        stock_code: str,
        stock_name: str,
        data_requirements: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        搜集股票相关数据（兼容旧 API）
        """
        # 创建并执行一个全面的搜索计划
        plan = await self.generate_search_plan(
            query="综合数据搜集",
            stock_code=stock_code,
            stock_name=stock_name
        )
        
        # 添加所有基础数据任务
        plan.tasks = [
            SearchTask(
                id=f"task_init_1",
                source=SearchSource.AKSHARE,
                query=stock_code,
                description="获取财务和行情数据",
                data_type="overview",
                icon="📊",
                estimated_time=3
            ),
            SearchTask(
                id=f"task_init_2",
                source=SearchSource.KNOWLEDGE_BASE,
                query=stock_code,
                description="获取历史新闻",
                data_type="news",
                icon="📚",
                estimated_time=2
            )
        ]
        
        return await self.execute_search_plan(plan)


# 快速分析师（保持不变）
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
            response = self._llm_provider.invoke([
                {"role": "system", "content": "你是快速分析师，擅长快速给出投资建议。"},
                {"role": "user", "content": prompt}
            ])
            content = response.content if hasattr(response, 'content') else str(response)
            return {
                "success": True,
                "analysis": content,
                "timestamp": datetime.utcnow().isoformat()
            }
        except Exception as e:
            logger.error(f"Quick analysis failed: {e}")
            return {
                "success": False,
                "error": str(e)
            }


# 工厂函数
def create_data_collector(llm_provider=None) -> DataCollectorAgentV2:
    """创建数据专员实例"""
    return DataCollectorAgentV2(llm_provider=llm_provider)

