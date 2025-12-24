"""
知识图谱数据模型
定义公司知识图谱的节点和关系结构
"""
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum


class NodeType(str, Enum):
    """节点类型枚举"""
    COMPANY = "Company"                # 公司
    NAME_VARIANT = "NameVariant"       # 名称变体
    BUSINESS = "Business"              # 业务线
    INDUSTRY = "Industry"              # 行业
    PRODUCT = "Product"                # 产品/服务
    KEYWORD = "Keyword"                # 检索关键词
    CONCEPT = "Concept"                # 概念/主题
    PARTNER = "Partner"                # 合作伙伴


class RelationType(str, Enum):
    """关系类型枚举"""
    HAS_VARIANT = "HAS_VARIANT"        # 有变体
    OPERATES_IN = "OPERATES_IN"        # 运营于（业务线）
    BELONGS_TO = "BELONGS_TO"          # 属于（行业）
    PROVIDES = "PROVIDES"              # 提供（产品）
    RELATES_TO = "RELATES_TO"          # 关联（关键词）
    INVOLVES = "INVOLVES"              # 涉及（概念）
    COOPERATES_WITH = "COOPERATES_WITH"  # 合作（伙伴）
    UPSTREAM = "UPSTREAM"              # 上游
    DOWNSTREAM = "DOWNSTREAM"          # 下游


class CompanyNode(BaseModel):
    """公司节点"""
    stock_code: str = Field(description="股票代码（如 SZ300634）")
    stock_name: str = Field(description="股票全称（如 彩讯股份）")
    short_code: str = Field(description="纯数字代码（如 300634）")
    industry: Optional[str] = Field(default=None, description="所属行业")
    sector: Optional[str] = Field(default=None, description="所属板块")
    market_cap: Optional[float] = Field(default=None, description="市值")
    listed_date: Optional[str] = Field(default=None, description="上市日期")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class NameVariantNode(BaseModel):
    """名称变体节点"""
    variant: str = Field(description="变体名称（如 彩讯、彩讯科技）")
    variant_type: str = Field(description="变体类型: abbreviation, alias, full_name")
    created_at: datetime = Field(default_factory=datetime.utcnow)


class BusinessNode(BaseModel):
    """业务线节点"""
    business_name: str = Field(description="业务名称")
    business_type: str = Field(description="业务类型: main, new, stopped")
    description: Optional[str] = Field(default=None, description="业务描述")
    start_date: Optional[str] = Field(default=None, description="开始日期")
    end_date: Optional[str] = Field(default=None, description="结束日期（如果停止）")
    status: str = Field(default="active", description="状态: active, stopped, planned")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class IndustryNode(BaseModel):
    """行业节点"""
    industry_name: str = Field(description="行业名称")
    industry_code: Optional[str] = Field(default=None, description="行业代码")
    level: int = Field(default=1, description="层级: 1=一级行业, 2=二级行业")
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ProductNode(BaseModel):
    """产品/服务节点"""
    product_name: str = Field(description="产品名称")
    product_type: str = Field(description="产品类型: software, hardware, service")
    description: Optional[str] = Field(default=None, description="产品描述")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class KeywordNode(BaseModel):
    """检索关键词节点"""
    keyword: str = Field(description="关键词")
    keyword_type: str = Field(description="类型: business, product, industry, general")
    weight: float = Field(default=1.0, description="权重（检索时的重要性）")
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ConceptNode(BaseModel):
    """概念/主题节点"""
    concept_name: str = Field(description="概念名称（如 AI大模型、元宇宙）")
    description: Optional[str] = Field(default=None, description="概念描述")
    hot_level: int = Field(default=0, description="热度等级 0-10")
    created_at: datetime = Field(default_factory=datetime.utcnow)


class CompanyKnowledgeGraph(BaseModel):
    """公司知识图谱完整结构（用于导入导出）"""
    company: CompanyNode
    name_variants: List[NameVariantNode] = Field(default_factory=list)
    businesses: List[BusinessNode] = Field(default_factory=list)
    industries: List[IndustryNode] = Field(default_factory=list)
    products: List[ProductNode] = Field(default_factory=list)
    keywords: List[KeywordNode] = Field(default_factory=list)
    concepts: List[ConceptNode] = Field(default_factory=list)


class SearchKeywordSet(BaseModel):
    """检索关键词集合（用于定向爬取）"""
    stock_code: str
    stock_name: str
    
    # 名称相关
    name_keywords: List[str] = Field(default_factory=list, description="名称变体")
    
    # 业务相关
    business_keywords: List[str] = Field(default_factory=list, description="业务线关键词")
    
    # 行业相关
    industry_keywords: List[str] = Field(default_factory=list, description="行业关键词")
    
    # 产品相关
    product_keywords: List[str] = Field(default_factory=list, description="产品关键词")
    
    # 概念相关
    concept_keywords: List[str] = Field(default_factory=list, description="概念关键词")
    
    # 组合查询
    combined_queries: List[str] = Field(default_factory=list, description="预组合的查询串")
    
    def get_all_keywords(self) -> List[str]:
        """获取所有关键词（去重）"""
        all_kw = (
            self.name_keywords +
            self.business_keywords +
            self.industry_keywords +
            self.product_keywords +
            self.concept_keywords
        )
        return list(set(all_kw))
    
    def generate_search_queries(self, max_queries: int = 10) -> List[str]:
        """
        生成多样化的搜索查询组合
        
        Args:
            max_queries: 最大查询数量
            
        Returns:
            查询字符串列表
        """
        queries = []
        
        # 1. 核心查询：股票名称 + 股票代码
        if self.name_keywords:
            queries.append(f"{self.stock_name} {self.stock_code}")
            queries.append(f"{self.name_keywords[0]} 股票")
        
        # 2. 业务线查询
        for business in self.business_keywords[:3]:  # 最多3个业务线
            queries.append(f"{self.stock_name} {business}")
            if len(self.name_keywords) > 1:
                queries.append(f"{self.name_keywords[0]} {business}")
        
        # 3. 概念查询
        for concept in self.concept_keywords[:2]:  # 最多2个概念
            queries.append(f"{self.stock_name} {concept}")
        
        # 4. 产品查询
        for product in self.product_keywords[:2]:  # 最多2个产品
            queries.append(f"{self.stock_name} {product}")
        
        # 5. 使用预组合查询
        queries.extend(self.combined_queries)
        
        # 去重并限制数量
        unique_queries = list(dict.fromkeys(queries))  # 保持顺序的去重
        return unique_queries[:max_queries]

