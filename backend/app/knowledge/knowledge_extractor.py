"""
知识提取器
从多种数据源提取公司知识并构建图谱
"""
import logging
import json
from typing import List, Dict, Any, Optional
from datetime import datetime

from agenticx import Agent
from ..services.llm_service import get_llm_provider
from .graph_models import (
    CompanyNode,
    NameVariantNode,
    BusinessNode,
    IndustryNode,
    ProductNode,
    KeywordNode,
    ConceptNode,
    CompanyKnowledgeGraph
)

logger = logging.getLogger(__name__)


class KnowledgeExtractorAgent(Agent):
    """
    知识提取智能体
    从多种数据源提取公司信息并构建知识图谱
    """
    
    def __init__(self, llm_provider=None, organization_id: str = "finnews"):
        super().__init__(
            name="KnowledgeExtractor",
            role="知识提取专家",
            goal="从多种数据源提取公司信息，构建全面的知识图谱",
            backstory="""你是一位专业的企业分析师和知识工程师。
你擅长从各类数据源（财务数据、新闻、公告、研报）中提取关键信息，
识别公司的业务线、产品、行业归属、关联概念等，
并将这些信息结构化为知识图谱，用于后续的智能检索和分析。""",
            organization_id=organization_id
        )
        
        if llm_provider is None:
            llm_provider = get_llm_provider()
        object.__setattr__(self, '_llm_provider', llm_provider)
        
        logger.info(f"Initialized {self.name} agent")
    
    async def extract_from_akshare(
        self,
        stock_code: str,
        stock_name: str,
        stock_info: Dict[str, Any]
    ) -> CompanyKnowledgeGraph:
        """
        从 akshare 数据提取基础信息
        
        Args:
            stock_code: 股票代码
            stock_name: 股票名称
            stock_info: akshare 返回的股票信息
            
        Returns:
            公司知识图谱
        """
        # 获取当前时间
        current_time = datetime.now().strftime("%Y年%m月%d日 %H:%M")
        
        # 提取纯数字代码
        short_code = stock_code
        if stock_code.startswith("SH") or stock_code.startswith("SZ"):
            short_code = stock_code[2:]
        
        # 创建公司节点
        company = CompanyNode(
            stock_code=stock_code,
            stock_name=stock_name,
            short_code=short_code,
            industry=stock_info.get("industry"),
            sector=stock_info.get("sector"),
            market_cap=stock_info.get("market_cap"),
            listed_date=stock_info.get("listed_date")
        )
        
        # 生成名称变体（通过 LLM 推理）
        name_variants_prompt = f"""请为以下公司生成可能的名称变体（简称、别名等）：

【当前时间】
{current_time}

【公司信息】
股票代码: {stock_code}
公司全称: {stock_name}
所属行业: {stock_info.get('industry', '未知')}

请以JSON格式返回名称变体列表，每个变体包含：
- variant: 变体名称
- variant_type: 类型（abbreviation=简称, alias=别名, full_name=全称）

示例：
```json
[
    {{"variant": "彩讯", "variant_type": "abbreviation"}},
    {{"variant": "彩讯科技", "variant_type": "alias"}},
    {{"variant": "{stock_name}", "variant_type": "full_name"}}
]
```

只返回JSON，不要其他解释。"""
        
        try:
            response = self._llm_provider.invoke([
                {"role": "system", "content": f"你是{self.role}，{self.backstory}"},
                {"role": "user", "content": name_variants_prompt}
            ])
            
            content = response.content if hasattr(response, 'content') else str(response)
            
            # 提取JSON
            import re
            json_match = re.search(r'\[.*\]', content, re.DOTALL)
            if json_match:
                variants_data = json.loads(json_match.group())
                name_variants = [NameVariantNode(**v) for v in variants_data]
            else:
                # 默认变体
                name_variants = [
                    NameVariantNode(variant=stock_name, variant_type="full_name"),
                    NameVariantNode(variant=stock_name[:2], variant_type="abbreviation")
                ]
                logger.warning("LLM 未返回有效JSON，使用默认变体")
        except Exception as e:
            logger.error(f"名称变体提取失败: {e}")
            name_variants = [
                NameVariantNode(variant=stock_name, variant_type="full_name")
            ]
        
        # 生成业务线（通过 LLM 推理 + akshare 数据）
        business_prompt = f"""请分析以下公司的主营业务线：

【当前时间】
{current_time}

【公司信息】
股票代码: {stock_code}
公司名称: {stock_name}
所属行业: {stock_info.get('industry', '未知')}
主营业务: {stock_info.get('main_business', '未知')}

请以JSON格式返回业务线列表，每个业务包含：
- business_name: 业务名称（简洁）
- business_type: 类型（main=主营, new=新增, stopped=已停止）
- description: 业务描述
- status: 状态（active=活跃, stopped=已停止）

示例：
```json
[
    {{"business_name": "运营商增值服务", "business_type": "main", "description": "为运营商提供增值业务", "status": "active"}},
    {{"business_name": "AI大模型应用", "business_type": "new", "description": "AI应用开发与落地", "status": "active"}}
]
```

只返回JSON数组，不要其他解释。"""
        
        try:
            response = self._llm_provider.invoke([
                {"role": "system", "content": f"你是{self.role}，{self.backstory}"},
                {"role": "user", "content": business_prompt}
            ])
            
            content = response.content if hasattr(response, 'content') else str(response)
            
            # 提取JSON
            json_match = re.search(r'\[.*\]', content, re.DOTALL)
            if json_match:
                businesses_data = json.loads(json_match.group())
                businesses = [BusinessNode(**b) for b in businesses_data]
            else:
                businesses = []
                logger.warning("LLM 未返回有效业务线JSON")
        except Exception as e:
            logger.error(f"业务线提取失败: {e}")
            businesses = []
        
        # 行业节点
        industries = []
        if stock_info.get('industry'):
            industries.append(IndustryNode(
                industry_name=stock_info['industry'],
                level=1
            ))
        
        # 返回基础图谱
        return CompanyKnowledgeGraph(
            company=company,
            name_variants=name_variants,
            businesses=businesses,
            industries=industries,
            products=[],
            keywords=[],
            concepts=[]
        )
    
    async def extract_from_news(
        self,
        stock_code: str,
        stock_name: str,
        news_list: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        从新闻中提取业务变化和概念
        
        Args:
            stock_code: 股票代码
            stock_name: 股票名称
            news_list: 新闻列表
            
        Returns:
            提取的信息
        """
        if not news_list:
            return {
                "new_businesses": [],
                "stopped_businesses": [],
                "new_products": [],
                "new_concepts": []
            }
        
        # 获取当前时间
        current_time = datetime.now().strftime("%Y年%m月%d日 %H:%M")
        
        # 汇总新闻
        news_summary = "\n\n".join([
            f"【{i+1}】{news.get('title', '')}\n{news.get('content', '')[:300]}..."
            for i, news in enumerate(news_list[:10])
        ])
        
        prompt = f"""请分析以下新闻，提取{stock_name}公司的业务变化和相关概念：

【当前时间】
{current_time}

【公司】{stock_name}({stock_code})

【近期新闻】
{news_summary}

请从新闻中提取：
1. **新增业务线**：公司新开拓的业务方向
2. **停止业务线**：公司明确表示停止或退出的业务
3. **新产品/服务**：公司推出的新产品或服务
4. **关联概念**：新闻中提到的热门概念（如 AI大模型、云计算、元宇宙等）

以JSON格式返回：
```json
{{
    "new_businesses": ["业务1", "业务2"],
    "stopped_businesses": ["业务3"],
    "new_products": ["产品1", "产品2"],
    "new_concepts": ["概念1", "概念2"]
}}
```

注意：
- 只提取明确的信息，不要臆测
- 如果没有相关信息，返回空数组
- 只返回JSON，不要其他文字

JSON:"""
        
        try:
            response = self._llm_provider.invoke([
                {"role": "system", "content": f"你是{self.role}，{self.backstory}"},
                {"role": "user", "content": prompt}
            ])
            
            content = response.content if hasattr(response, 'content') else str(response)
            
            # 提取JSON
            import re
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                extracted = json.loads(json_match.group())
                logger.info(f"✅ 从新闻提取信息: {extracted}")
                return extracted
            else:
                logger.warning("LLM 未返回有效JSON")
                return {
                    "new_businesses": [],
                    "stopped_businesses": [],
                    "new_products": [],
                    "new_concepts": []
                }
        except Exception as e:
            logger.error(f"新闻信息提取失败: {e}")
            return {
                "new_businesses": [],
                "stopped_businesses": [],
                "new_products": [],
                "new_concepts": []
            }
    
    async def extract_from_document(
        self,
        stock_code: str,
        stock_name: str,
        document_content: str,
        document_type: str = "annual_report"
    ) -> Dict[str, Any]:
        """
        从PDF/Word文档提取深度信息
        
        Args:
            stock_code: 股票代码
            stock_name: 股票名称
            document_content: 文档内容（已通过MinerU解析）
            document_type: 文档类型（annual_report=年报, announcement=公告）
            
        Returns:
            提取的信息
        """
        # 获取当前时间
        current_time = datetime.now().strftime("%Y年%m月%d日 %H:%M")
        
        prompt = f"""请从以下{stock_name}的{document_type}中提取详细的业务信息：

【当前时间】
{current_time}

【公司】{stock_name}({stock_code})

【文档内容】（前3000字）
{document_content[:3000]}

请提取：
1. **主营业务**：公司当前的核心业务（详细）
2. **新增业务**：文档中提到的新业务拓展
3. **主要产品**：公司的主要产品或服务
4. **行业定位**：所属行业和细分领域
5. **战略方向**：未来战略和关注的热点领域

以JSON格式返回：
```json
{{
    "main_businesses": [
        {{"name": "业务1", "description": "详细描述"}}
    ],
    "new_businesses": [
        {{"name": "业务2", "description": "详细描述"}}
    ],
    "products": [
        {{"name": "产品1", "type": "software/hardware/service", "description": "描述"}}
    ],
    "industries": ["一级行业", "二级行业"],
    "concepts": ["概念1", "概念2"],
    "keywords": ["关键词1", "关键词2"]
}}
```

只返回JSON，不要其他解释。"""
        
        try:
            response = self._llm_provider.invoke([
                {"role": "system", "content": f"你是{self.role}，{self.backstory}"},
                {"role": "user", "content": prompt}
            ])
            
            content = response.content if hasattr(response, 'content') else str(response)
            
            # 提取JSON
            import re
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                extracted = json.loads(json_match.group())
                logger.info(f"✅ 从文档提取信息: {len(extracted.get('products', []))}个产品, {len(extracted.get('concepts', []))}个概念")
                return extracted
            else:
                logger.warning("LLM 未返回有效JSON")
                return {}
        except Exception as e:
            logger.error(f"文档信息提取失败: {e}")
            return {}


class AkshareKnowledgeExtractor:
    """
    从 akshare 提取基础信息，构建简单图谱并生成搜索关键词
    """
    
    @staticmethod
    def extract_company_info(stock_code: str) -> Optional[Dict[str, Any]]:
        """
        从 akshare 获取公司基础信息
        
        Args:
            stock_code: 股票代码
            
        Returns:
            公司信息字典
        """
        try:
            import akshare as ak
            
            # 提取纯数字代码
            pure_code = stock_code
            if stock_code.startswith("SH") or stock_code.startswith("SZ"):
                pure_code = stock_code[2:]
            
            logger.info(f"🔍 从 akshare 获取公司信息: {pure_code}")
            
            # 获取个股信息
            try:
                # 尝试获取实时行情（包含基本信息）
                stock_df = ak.stock_individual_info_em(symbol=pure_code)
                
                if stock_df is not None and not stock_df.empty:
                    # 打印 DataFrame 结构用于调试
                    logger.info(f"📋 akshare 返回 DataFrame: columns={list(stock_df.columns)}, rows={len(stock_df)}")
                    
                    # 转换为字典 - 兼容不同的列名格式
                    info_dict = {}
                    
                    # 确定列名
                    columns = list(stock_df.columns)
                    key_col = None
                    value_col = None
                    
                    # 尝试找到 key 列
                    for col in ['item', '属性', 'name', '项目']:
                        if col in columns:
                            key_col = col
                            break
                    
                    # 尝试找到 value 列
                    for col in ['value', '值', 'data', '数值']:
                        if col in columns:
                            value_col = col
                            break
                    
                    # 如果只有两列，直接使用
                    if len(columns) == 2 and (key_col is None or value_col is None):
                        key_col, value_col = columns[0], columns[1]
                    
                    if key_col and value_col:
                        for _, row in stock_df.iterrows():
                            try:
                                key = str(row[key_col]) if row[key_col] is not None else ''
                                value = str(row[value_col]) if row[value_col] is not None else ''
                                if key and value and key != 'nan' and value != 'nan':
                                    info_dict[key] = value
                            except Exception as row_err:
                                logger.debug(f"跳过行: {row_err}")
                                continue
                    else:
                        logger.warning(f"⚠️ 无法识别 DataFrame 列结构: {columns}")
                    
                    logger.info(f"📊 解析到 {len(info_dict)} 个字段: {list(info_dict.keys())[:10]}...")
                    
                    # 提取关键字段
                    result = {
                        "industry": info_dict.get("行业") or info_dict.get("所属行业"),
                        "sector": info_dict.get("板块") or info_dict.get("所属板块"),
                        "main_business": info_dict.get("主营业务") or info_dict.get("经营范围"),
                        "total_market_cap": info_dict.get("总市值"),
                        "listed_date": info_dict.get("上市时间"),
                        "raw_data": info_dict
                    }
                    
                    main_business_preview = (result.get('main_business') or '')[:30]
                    logger.info(f"✅ 获取到公司信息: 行业={result.get('industry')}, 主营={main_business_preview}...")
                    return result
                else:
                    logger.warning(f"⚠️ akshare 未返回数据: {pure_code}")
                    return None
                    
            except Exception as e:
                logger.error(f"❌ akshare 查询失败: {e}", exc_info=True)
                return None
                
        except ImportError:
            logger.error("akshare 未安装")
            return None
        except Exception as e:
            logger.error(f"提取公司信息失败: {e}")
            return None
    
    @staticmethod
    def generate_search_keywords(
        stock_code: str,
        stock_name: str,
        akshare_info: Optional[Dict[str, Any]] = None
    ) -> Dict[str, List[str]]:
        """
        基于股票信息生成分层关键词
        
        返回两类关键词：
        - core_keywords: 核心关键词（公司名、代码等，必须包含）
        - extension_keywords: 扩展关键词（行业、业务、人名等，用于组合）
        
        Args:
            stock_code: 股票代码（如 SZ000004）
            stock_name: 股票名称（如 *ST国华）
            akshare_info: akshare 返回的公司信息（可选）
            
        Returns:
            {"core_keywords": [...], "extension_keywords": [...]}
        """
        core_keywords = []
        extension_keywords = []
        
        # 提取纯数字代码
        pure_code = stock_code
        if stock_code.startswith("SH") or stock_code.startswith("SZ"):
            pure_code = stock_code[2:]
        
        # === 1. 核心关键词（必须包含，用于确保相关性）===
        # 原始名称（如 *ST国华）
        core_keywords.append(stock_name)
        
        # 去除 ST 标记的名称（如 国华）
        clean_name = stock_name
        for prefix in ["*ST", "ST", "S*ST", "S"]:
            if clean_name.startswith(prefix):
                clean_name = clean_name[len(prefix):]
                break
        if clean_name != stock_name and len(clean_name) >= 2:
            core_keywords.append(clean_name)
        
        # 股票代码
        core_keywords.append(pure_code)  # 000004
        core_keywords.append(stock_code)  # SZ000004
        
        # 小写变体（如 st国华）
        core_keywords.append(stock_name.lower())
        if clean_name != stock_name:
            core_keywords.append(clean_name.lower())
        
        # === 2. 扩展关键词（用于组合搜索，扩大范围）===
        if akshare_info:
            raw_data = akshare_info.get("raw_data", {})
            
            # 公司全称（从 raw_data 中提取）
            company_full_name = raw_data.get("公司名称", raw_data.get("公司全称"))
            if company_full_name and len(company_full_name) > 4:
                extension_keywords.append(company_full_name)
            
            # 行业（但不单独搜索）
            industry = akshare_info.get("industry")
            if industry:
                extension_keywords.append(industry)
            
            # 主营业务（提取关键词）
            main_business = akshare_info.get("main_business", "")
            if main_business:
                import re
                business_parts = re.split(r'[，,、；;。\s]+', main_business)
                for part in business_parts[:3]:  # 只取前3个
                    if 3 <= len(part) <= 10:  # 长度适中的词
                        extension_keywords.append(part)
            
            # 董事长、总经理等关键人物
            ceo = raw_data.get("董事长", raw_data.get("总经理"))
            if ceo and 2 <= len(str(ceo)) <= 4:
                extension_keywords.append(str(ceo))
        
        # 去重
        core_keywords = list(dict.fromkeys(core_keywords))
        extension_keywords = list(dict.fromkeys(extension_keywords))
        
        logger.info(
            f"📋 生成分层关键词: 核心={len(core_keywords)}个{core_keywords[:5]}, "
            f"扩展={len(extension_keywords)}个{extension_keywords[:5]}"
        )
        
        return {
            "core_keywords": core_keywords,
            "extension_keywords": extension_keywords
        }
    
    @staticmethod
    def build_simple_graph_from_info(
        stock_code: str,
        stock_name: str,
        akshare_info: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        基于 akshare 信息构建简单的知识图谱结构
        
        即使 akshare 调用失败，也能基于股票名称构建基础图谱
        
        Args:
            stock_code: 股票代码
            stock_name: 股票名称
            akshare_info: akshare 返回的公司信息（可选）
            
        Returns:
            简单图谱结构
        """
        # 提取纯数字代码
        pure_code = stock_code
        if stock_code.startswith("SH") or stock_code.startswith("SZ"):
            pure_code = stock_code[2:]
        
        # 构建基础图谱
        graph = {
            "company": {
                "stock_code": stock_code,
                "stock_name": stock_name,
                "pure_code": pure_code
            },
            "name_variants": [],
            "industries": [],
            "businesses": [],
            "keywords": []
        }
        
        # === 1. 名称变体 ===
        graph["name_variants"].append(stock_name)
        
        # 去除 ST 标记
        clean_name = stock_name
        for prefix in ["*ST", "ST", "S*ST", "S"]:
            if clean_name.startswith(prefix):
                clean_name = clean_name[len(prefix):]
                break
        if clean_name != stock_name:
            graph["name_variants"].append(clean_name)
        
        # 简称（取前两个字）
        if len(clean_name) >= 2:
            graph["name_variants"].append(clean_name[:2])
        
        # === 2. 基于 akshare 信息填充 ===
        if akshare_info:
            # 行业
            industry = akshare_info.get("industry")
            if industry:
                graph["industries"].append(industry)
            
            # 板块
            sector = akshare_info.get("sector")
            if sector:
                graph["industries"].append(sector)
            
            # 主营业务
            main_business = akshare_info.get("main_business", "")
            if main_business:
                graph["businesses"].append(main_business[:100])  # 截取前100字
                
                # 提取业务关键词
                import re
                business_parts = re.split(r'[，,、；;。\s]+', main_business)
                for part in business_parts[:5]:
                    if 2 <= len(part) <= 10:
                        graph["keywords"].append(part)
        
        # === 3. 生成搜索关键词（分层：核心 + 扩展） ===
        keyword_groups = AkshareKnowledgeExtractor.generate_search_keywords(
            stock_code, stock_name, akshare_info
        )
        graph["core_keywords"] = keyword_groups["core_keywords"]
        graph["extension_keywords"] = keyword_groups["extension_keywords"]
        
        logger.info(f"📊 构建简单图谱: 公司={stock_name}, 名称变体={len(graph['name_variants'])}个, "
                   f"行业={len(graph['industries'])}个, "
                   f"核心词={len(graph['core_keywords'])}个, 扩展词={len(graph['extension_keywords'])}个")
        
        return graph


class NewsKnowledgeExtractor:
    """
    从新闻中提取业务变化
    """
    
    def __init__(self, extractor_agent: KnowledgeExtractorAgent):
        self.agent = extractor_agent
    
    async def extract_business_changes(
        self,
        stock_code: str,
        stock_name: str,
        news_list: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        从新闻列表中提取业务变化
        
        Args:
            stock_code: 股票代码
            stock_name: 股票名称
            news_list: 新闻列表
            
        Returns:
            业务变化信息
        """
        return await self.agent.extract_from_news(stock_code, stock_name, news_list)


# 工厂函数
def create_knowledge_extractor(llm_provider=None) -> KnowledgeExtractorAgent:
    """创建知识提取智能体"""
    return KnowledgeExtractorAgent(llm_provider)

