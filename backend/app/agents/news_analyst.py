"""
新闻分析师智能体
"""
import logging
from typing import List, Dict, Any, Optional
from agenticx import Agent, Task, BaseTool
from agenticx.core.agent_executor import AgentExecutor

from ..services.llm_service import get_llm_provider
from ..tools import TextCleanerTool

logger = logging.getLogger(__name__)


class NewsAnalystAgent(Agent):
    """
    新闻分析师智能体
    职责：分析金融新闻的情感、影响和关键信息
    """
    
    def __init__(
        self,
        llm_provider=None,
        tools: Optional[List[BaseTool]] = None,
        organization_id: str = "finnews",
        **kwargs
    ):
        """
        初始化新闻分析师智能体
        
        Args:
            llm_provider: LLM 提供者
            tools: 工具列表
            organization_id: 组织ID（用于多租户隔离），默认 "finnews"
            **kwargs: 额外参数
        """
        # 如果没有提供 LLM，使用默认的
        if llm_provider is None:
            llm_provider = get_llm_provider()
        
        # 如果没有提供工具，使用默认工具
        if tools is None:
            tools = [TextCleanerTool()]
        
        # 保存 LLM 和工具供后续使用（在 super().__init__ 之前保存）
        self._llm_provider = llm_provider
        self._tools = tools
        
        # 定义智能体属性（Agent 基类）
        super().__init__(
            name="NewsAnalyst",
            role="金融新闻分析师",
            goal="深度分析金融新闻，提取关键信息，评估市场影响",
            backstory="""你是一位经验丰富的金融新闻分析专家，具有10年以上的证券市场分析经验。
你擅长从新闻中提取关键信息，准确判断新闻对股票市场的影响，并能够识别潜在的投资机会和风险。
你的分析报告准确、专业，深受投资者信赖。""",
            organization_id=organization_id,
            **kwargs
        )
        
        # 创建 AgentExecutor（在 super().__init__ 之后）
        self._executor = None
        self._init_executor(llm_provider, tools)
        
        logger.info(f"Initialized {self.name} agent")
    
    def _init_executor(self, llm_provider=None, tools=None):
        """初始化 AgentExecutor（延迟初始化）"""
        if self._executor is None:
            if llm_provider is None:
                llm_provider = getattr(self, '_llm_provider', None) or get_llm_provider()
            if tools is None:
                tools = getattr(self, '_tools', None) or [TextCleanerTool()]
            
            self._llm_provider = llm_provider
            self._tools = tools
            self._executor = AgentExecutor(
                llm_provider=llm_provider,
                tools=tools
            )
    
    @property
    def executor(self):
        """获取 AgentExecutor（延迟初始化）"""
        if self._executor is None:
            self._init_executor()
        return self._executor
    
    def analyze_news(
        self,
        news_title: str,
        news_content: str,
        news_url: str = "",
        stock_codes: List[str] = None
    ) -> Dict[str, Any]:
        """
        分析单条新闻
        
        Args:
            news_title: 新闻标题
            news_content: 新闻内容
            news_url: 新闻URL
            stock_codes: 关联股票代码
            
        Returns:
            分析结果字典
        """
        # 构建分析提示词
        prompt = f"""你是一位经验丰富的金融新闻分析专家，具有10年以上的证券市场分析经验。
你擅长从新闻中提取关键信息，准确判断新闻对股票市场的影响，并能够识别潜在的投资机会和风险。

请深度分析以下金融新闻，并提供结构化的分析报告：

【新闻标题】
{news_title}

【新闻内容】
{news_content[:2000]}

【关联股票】
{', '.join(stock_codes) if stock_codes else '无'}

请从以下几个维度进行分析：

1. **情感倾向**: 判断新闻对市场/股票的情感倾向（利好/利空/中性），并给出评分（-1到1）
   - 利好：正面消息，可能推动股价上涨，评分范围 0.1 到 1.0
   - 利空：负面消息，可能推动股价下跌，评分范围 -1.0 到 -0.1
   - 中性：无明显影响，评分接近 0

2. **关键信息**: 提取新闻中的关键信息点（人物、事件、数据等）

3. **市场影响**: 分析新闻可能对市场/相关股票造成的影响

4. **投资建议**: 基于分析给出简要的投资建议

5. **置信度**: 对本次分析的置信度评估（0-1）

请以清晰、专业的方式组织你的分析报告，确保情感倾向和评分准确反映新闻的实际影响。
"""
        
        try:
            # 确保 LLM provider 已初始化
            if not hasattr(self, '_llm_provider') or self._llm_provider is None:
                self._llm_provider = get_llm_provider()
            
            logger.info(f"Calling LLM provider: {type(self._llm_provider).__name__}, model: {getattr(self._llm_provider, 'model', 'unknown')}")
            
            # 直接调用 LLM（不使用 AgentExecutor，避免审批暂停）
            response = self._llm_provider.invoke([
                {"role": "system", "content": f"你是{self.role}，{self.backstory}"},
                {"role": "user", "content": prompt}
            ])
            
            logger.info("LLM response received")
            
            # 获取分析结果
            analysis_text = response.content if hasattr(response, 'content') else str(response)
            
            # 尝试提取结构化信息
            structured_result = self._extract_structured_info(analysis_text)
            
            return {
                "success": True,
                "analysis_result": analysis_text,
                "structured_data": structured_result,
                "agent_name": self.name,
                "agent_role": self.role,
            }
        
        except Exception as e:
            logger.error(f"News analysis failed: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "agent_name": self.name,
            }
    
    def _extract_structured_info(self, analysis_text: str) -> Dict[str, Any]:
        """
        从分析文本中提取结构化信息
        
        Args:
            analysis_text: 分析文本
            
        Returns:
            结构化数据
        """
        import re
        
        result = {
            "sentiment": "neutral",
            "sentiment_score": 0.0,
            "confidence": 0.5,
            "key_points": [],
            "market_impact": "",
            "investment_advice": "",
        }
        
        try:
            # 提取情感倾向（支持多种格式）
            # 匹配：利好、利空、中性、显著利好、显著利空等
            sentiment_patterns = [
                r'情感倾向[：:]\s*\*?\*?(显著|明显)?(利好|利空|中性)',
                r'(显著|明显)?(利好|利空|中性)',  # 备用模式
            ]
            for pattern in sentiment_patterns:
                sentiment_match = re.search(pattern, analysis_text)
                if sentiment_match:
                    # 提取最后一个匹配的词（利好/利空/中性）
                    groups = [g for g in sentiment_match.groups() if g]
                    if groups:
                        sentiment_word = groups[-1]
                        sentiment_map = {"利好": "positive", "利空": "negative", "中性": "neutral"}
                        result["sentiment"] = sentiment_map.get(sentiment_word, "neutral")
                        break
            
            # 提取情感评分（支持多种格式）
            # 匹配：-0.92、**-0.92**、-0.92 / -1.0 等格式
            score_patterns = [
                r'情感评分[：:]\s*\*?\*?([-+]?\d*\.?\d+)',  # 情感评分：-0.92
                r'评分[：:]\s*\*?\*?([-+]?\d*\.?\d+)',       # 评分：-0.92
                r'([-+]?\d*\.?\d+)\s*/\s*[-+]?\d*\.?\d+',   # -0.92 / -1.0
            ]
            for pattern in score_patterns:
                score_match = re.search(pattern, analysis_text)
                if score_match:
                    result["sentiment_score"] = float(score_match.group(1))
                    logger.info(f"Extracted sentiment score: {result['sentiment_score']}")
                    break
            
            # 如果未提取到评分，尝试从情感倾向推断
            if result["sentiment_score"] == 0.0 and result["sentiment"] != "neutral":
                if result["sentiment"] == "positive":
                    result["sentiment_score"] = 0.5  # 默认中等利好
                elif result["sentiment"] == "negative":
                    result["sentiment_score"] = -0.5  # 默认中等利空
            
            # 提取置信度
            confidence_match = re.search(r'置信度[：:]\s*\*?\*?(\d*\.?\d+)', analysis_text)
            if confidence_match:
                result["confidence"] = float(confidence_match.group(1))
            
            # 提取关键信息点（简单实现：查找列表）
            key_points_section = re.search(r'关键信息[：:](.*?)(?=市场影响|投资建议|$)', analysis_text, re.DOTALL)
            if key_points_section:
                points_text = key_points_section.group(1)
                points = re.findall(r'[•\-\*]\s*(.+)', points_text)
                result["key_points"] = [p.strip() for p in points if p.strip()]
            
            # 提取市场影响
            impact_match = re.search(r'市场影响[：:](.*?)(?=投资建议|置信度|$)', analysis_text, re.DOTALL)
            if impact_match:
                result["market_impact"] = impact_match.group(1).strip()
            
            # 提取投资建议
            advice_match = re.search(r'投资建议[：:](.*?)(?=置信度|$)', analysis_text, re.DOTALL)
            if advice_match:
                result["investment_advice"] = advice_match.group(1).strip()
        
        except Exception as e:
            logger.warning(f"Failed to extract structured info: {e}")
        
        # 日志记录提取结果
        logger.info(
            f"Extracted sentiment: {result['sentiment']}, "
            f"score: {result['sentiment_score']}, "
            f"confidence: {result['confidence']}"
        )
        
        return result
    
    def batch_analyze(
        self,
        news_list: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        批量分析新闻
        
        Args:
            news_list: 新闻列表
            
        Returns:
            分析结果列表
        """
        results = []
        
        for news in news_list:
            try:
                result = self.analyze_news(
                    news_title=news.get("title", ""),
                    news_content=news.get("content", ""),
                    news_url=news.get("url", ""),
                    stock_codes=news.get("stock_codes", [])
                )
                results.append(result)
            except Exception as e:
                logger.error(f"Failed to analyze news: {e}")
                results.append({
                    "success": False,
                    "error": str(e),
                    "news_url": news.get("url", "")
                })
        
        return results


def create_news_analyst(
    llm_provider=None,
    tools: Optional[List[BaseTool]] = None,
    organization_id: str = "finnews"
) -> NewsAnalystAgent:
    """
    创建新闻分析师智能体实例
    
    Args:
        llm_provider: LLM 提供者
        tools: 工具列表
        organization_id: 组织ID（用于多租户隔离），默认 "finnews"
        
    Returns:
        NewsAnalystAgent 实例
    """
    return NewsAnalystAgent(
        llm_provider=llm_provider, 
        tools=tools,
        organization_id=organization_id
    )

