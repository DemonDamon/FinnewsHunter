"""
知识图谱服务
提供公司知识图谱的创建、查询、更新操作
"""
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

from ..core.neo4j_client import get_neo4j_client
from .graph_models import (
    CompanyNode,
    NameVariantNode,
    BusinessNode,
    IndustryNode,
    ProductNode,
    KeywordNode,
    ConceptNode,
    CompanyKnowledgeGraph,
    SearchKeywordSet,
    NodeType,
    RelationType
)

logger = logging.getLogger(__name__)


class KnowledgeGraphService:
    """知识图谱服务"""
    
    def __init__(self):
        self.neo4j = get_neo4j_client()
        self._ensure_constraints()
    
    def _ensure_constraints(self):
        """确保数据库约束和索引存在"""
        constraints = [
            # 公司节点唯一约束
            "CREATE CONSTRAINT company_code IF NOT EXISTS FOR (c:Company) REQUIRE c.stock_code IS UNIQUE",
            # 索引加速查询
            "CREATE INDEX company_name IF NOT EXISTS FOR (c:Company) ON (c.stock_name)",
            "CREATE INDEX business_name IF NOT EXISTS FOR (b:Business) ON (b.business_name)",
            "CREATE INDEX keyword_text IF NOT EXISTS FOR (k:Keyword) ON (k.keyword)",
        ]
        
        for constraint in constraints:
            try:
                self.neo4j.execute_write(constraint)
            except Exception as e:
                # 约束可能已存在，忽略错误
                logger.debug(f"Constraint creation skipped: {e}")
    
    # ============ 公司节点操作 ============
    
    def create_or_update_company(self, company: CompanyNode) -> bool:
        """
        创建或更新公司节点
        
        Args:
            company: 公司节点数据
            
        Returns:
            是否成功
        """
        query = """
        MERGE (c:Company {stock_code: $stock_code})
        SET c.stock_name = $stock_name,
            c.short_code = $short_code,
            c.industry = $industry,
            c.sector = $sector,
            c.market_cap = $market_cap,
            c.listed_date = $listed_date,
            c.updated_at = datetime(),
            c.created_at = coalesce(c.created_at, datetime())
        RETURN c
        """
        
        params = company.model_dump()
        params['created_at'] = company.created_at.isoformat()
        params['updated_at'] = datetime.utcnow().isoformat()
        
        try:
            self.neo4j.execute_write(query, params)
            logger.info(f"✅ 公司节点已创建/更新: {company.stock_name}({company.stock_code})")
            return True
        except Exception as e:
            logger.error(f"❌ 公司节点创建失败: {e}")
            return False
    
    def get_company(self, stock_code: str) -> Optional[Dict[str, Any]]:
        """获取公司节点"""
        query = """
        MATCH (c:Company {stock_code: $stock_code})
        RETURN c
        """
        
        results = self.neo4j.execute_query(query, {"stock_code": stock_code})
        return results[0]['c'] if results else None
    
    # ============ 名称变体操作 ============
    
    def add_name_variants(
        self,
        stock_code: str,
        variants: List[NameVariantNode]
    ) -> bool:
        """
        添加名称变体
        
        Args:
            stock_code: 股票代码
            variants: 名称变体列表
            
        Returns:
            是否成功
        """
        for variant in variants:
            query = """
            MATCH (c:Company {stock_code: $stock_code})
            MERGE (v:NameVariant {variant: $variant})
            SET v.variant_type = $variant_type,
                v.created_at = $created_at
            MERGE (c)-[r:HAS_VARIANT]->(v)
            RETURN v
            """
            
            params = {
                "stock_code": stock_code,
                "variant": variant.variant,
                "variant_type": variant.variant_type,
                "created_at": variant.created_at.isoformat()
            }
            
            try:
                self.neo4j.execute_write(query, params)
            except Exception as e:
                logger.error(f"添加名称变体失败 {variant.variant}: {e}")
                return False
        
        logger.info(f"✅ 已添加 {len(variants)} 个名称变体")
        return True
    
    # ============ 业务线操作 ============
    
    def add_business(
        self,
        stock_code: str,
        business: BusinessNode
    ) -> bool:
        """添加业务线"""
        query = """
        MATCH (c:Company {stock_code: $stock_code})
        MERGE (b:Business {business_name: $business_name})
        SET b.business_type = $business_type,
            b.description = $description,
            b.start_date = $start_date,
            b.end_date = $end_date,
            b.status = $status,
            b.updated_at = datetime(),
            b.created_at = coalesce(b.created_at, datetime())
        MERGE (c)-[r:OPERATES_IN]->(b)
        RETURN b
        """
        
        params = business.model_dump()
        params['stock_code'] = stock_code
        
        try:
            self.neo4j.execute_write(query, params)
            logger.info(f"✅ 业务线已添加: {business.business_name}")
            return True
        except Exception as e:
            logger.error(f"❌ 业务线添加失败: {e}")
            return False
    
    def stop_business(
        self,
        stock_code: str,
        business_name: str,
        end_date: str = None
    ) -> bool:
        """停止业务线"""
        query = """
        MATCH (c:Company {stock_code: $stock_code})-[:OPERATES_IN]->(b:Business {business_name: $business_name})
        SET b.status = 'stopped',
            b.end_date = $end_date,
            b.updated_at = datetime()
        RETURN b
        """
        
        params = {
            "stock_code": stock_code,
            "business_name": business_name,
            "end_date": end_date or datetime.utcnow().strftime("%Y-%m-%d")
        }
        
        try:
            self.neo4j.execute_write(query, params)
            logger.info(f"✅ 业务线已停止: {business_name}")
            return True
        except Exception as e:
            logger.error(f"❌ 业务线停止失败: {e}")
            return False
    
    # ============ 关键词操作 ============
    
    def add_keywords(
        self,
        stock_code: str,
        keywords: List[KeywordNode],
        relation_type: str = "RELATES_TO"
    ) -> bool:
        """添加检索关键词"""
        for keyword in keywords:
            query = """
            MATCH (c:Company {stock_code: $stock_code})
            MERGE (k:Keyword {keyword: $keyword})
            SET k.keyword_type = $keyword_type,
                k.weight = $weight,
                k.created_at = $created_at
            MERGE (c)-[r:RELATES_TO]->(k)
            RETURN k
            """
            
            params = {
                "stock_code": stock_code,
                "keyword": keyword.keyword,
                "keyword_type": keyword.keyword_type,
                "weight": keyword.weight,
                "created_at": keyword.created_at.isoformat()
            }
            
            try:
                self.neo4j.execute_write(query, params)
            except Exception as e:
                logger.error(f"添加关键词失败 {keyword.keyword}: {e}")
                return False
        
        logger.info(f"✅ 已添加 {len(keywords)} 个关键词")
        return True
    
    # ============ 概念操作 ============
    
    def add_concepts(
        self,
        stock_code: str,
        concepts: List[ConceptNode]
    ) -> bool:
        """添加概念/主题"""
        for concept in concepts:
            query = """
            MATCH (c:Company {stock_code: $stock_code})
            MERGE (con:Concept {concept_name: $concept_name})
            SET con.description = $description,
                con.hot_level = $hot_level,
                con.created_at = $created_at
            MERGE (c)-[r:INVOLVES]->(con)
            RETURN con
            """
            
            params = {
                "stock_code": stock_code,
                "concept_name": concept.concept_name,
                "description": concept.description,
                "hot_level": concept.hot_level,
                "created_at": concept.created_at.isoformat()
            }
            
            try:
                self.neo4j.execute_write(query, params)
            except Exception as e:
                logger.error(f"添加概念失败 {concept.concept_name}: {e}")
                return False
        
        logger.info(f"✅ 已添加 {len(concepts)} 个概念")
        return True
    
    # ============ 完整图谱操作 ============
    
    def build_company_graph(self, graph: CompanyKnowledgeGraph) -> bool:
        """
        构建完整的公司知识图谱
        
        Args:
            graph: 公司知识图谱数据
            
        Returns:
            是否成功
        """
        try:
            # 1. 创建公司节点
            self.create_or_update_company(graph.company)
            
            # 2. 添加名称变体
            if graph.name_variants:
                self.add_name_variants(graph.company.stock_code, graph.name_variants)
            
            # 3. 添加业务线
            for business in graph.businesses:
                self.add_business(graph.company.stock_code, business)
            
            # 4. 添加行业
            for industry in graph.industries:
                self._add_industry(graph.company.stock_code, industry)
            
            # 5. 添加产品
            for product in graph.products:
                self._add_product(graph.company.stock_code, product)
            
            # 6. 添加关键词
            if graph.keywords:
                self.add_keywords(graph.company.stock_code, graph.keywords)
            
            # 7. 添加概念
            if graph.concepts:
                self.add_concepts(graph.company.stock_code, graph.concepts)
            
            logger.info(f"✅ 知识图谱构建完成: {graph.company.stock_name}")
            return True
            
        except Exception as e:
            logger.error(f"❌ 知识图谱构建失败: {e}")
            return False
    
    def _add_industry(self, stock_code: str, industry: IndustryNode) -> bool:
        """添加行业节点（内部方法）"""
        query = """
        MATCH (c:Company {stock_code: $stock_code})
        MERGE (i:Industry {industry_name: $industry_name})
        SET i.industry_code = $industry_code,
            i.level = $level,
            i.created_at = $created_at
        MERGE (c)-[r:BELONGS_TO]->(i)
        RETURN i
        """
        
        params = industry.model_dump()
        params['stock_code'] = stock_code
        
        try:
            self.neo4j.execute_write(query, params)
            return True
        except Exception as e:
            logger.error(f"行业添加失败: {e}")
            return False
    
    def _add_product(self, stock_code: str, product: ProductNode) -> bool:
        """添加产品节点（内部方法）"""
        query = """
        MATCH (c:Company {stock_code: $stock_code})
        MERGE (p:Product {product_name: $product_name})
        SET p.product_type = $product_type,
            p.description = $description,
            p.updated_at = datetime(),
            p.created_at = coalesce(p.created_at, datetime())
        MERGE (c)-[r:PROVIDES]->(p)
        RETURN p
        """
        
        params = product.model_dump()
        params['stock_code'] = stock_code
        
        try:
            self.neo4j.execute_write(query, params)
            return True
        except Exception as e:
            logger.error(f"产品添加失败: {e}")
            return False
    
    # ============ 查询操作 ============
    
    def get_company_graph(self, stock_code: str) -> Optional[CompanyKnowledgeGraph]:
        """
        获取完整的公司知识图谱
        
        Args:
            stock_code: 股票代码
            
        Returns:
            公司知识图谱或None
        """
        # 查询公司及其所有关联节点
        query = """
        MATCH (c:Company {stock_code: $stock_code})
        OPTIONAL MATCH (c)-[:HAS_VARIANT]->(v:NameVariant)
        OPTIONAL MATCH (c)-[:OPERATES_IN]->(b:Business)
        OPTIONAL MATCH (c)-[:BELONGS_TO]->(i:Industry)
        OPTIONAL MATCH (c)-[:PROVIDES]->(p:Product)
        OPTIONAL MATCH (c)-[:RELATES_TO]->(k:Keyword)
        OPTIONAL MATCH (c)-[:INVOLVES]->(con:Concept)
        RETURN c,
               collect(DISTINCT v) as variants,
               collect(DISTINCT b) as businesses,
               collect(DISTINCT i) as industries,
               collect(DISTINCT p) as products,
               collect(DISTINCT k) as keywords,
               collect(DISTINCT con) as concepts
        """
        
        try:
            results = self.neo4j.execute_query(query, {"stock_code": stock_code})
            
            if not results or not results[0]['c']:
                return None
            
            data = results[0]
            company_data = dict(data['c'])
            
            # 构建完整图谱
            graph = CompanyKnowledgeGraph(
                company=CompanyNode(**company_data),
                name_variants=[NameVariantNode(**dict(v)) for v in data['variants'] if v],
                businesses=[BusinessNode(**dict(b)) for b in data['businesses'] if b],
                industries=[IndustryNode(**dict(i)) for i in data['industries'] if i],
                products=[ProductNode(**dict(p)) for p in data['products'] if p],
                keywords=[KeywordNode(**dict(k)) for k in data['keywords'] if k],
                concepts=[ConceptNode(**dict(c)) for c in data['concepts'] if c]
            )
            
            return graph
            
        except Exception as e:
            logger.error(f"查询公司图谱失败: {e}")
            return None
    
    def get_search_keywords(self, stock_code: str) -> Optional[SearchKeywordSet]:
        """
        获取用于检索的关键词集合
        
        Args:
            stock_code: 股票代码
            
        Returns:
            检索关键词集合
        """
        graph = self.get_company_graph(stock_code)
        if not graph:
            return None
        
        # 构建检索关键词集合
        keyword_set = SearchKeywordSet(
            stock_code=stock_code,
            stock_name=graph.company.stock_name,
            name_keywords=[v.variant for v in graph.name_variants],
            business_keywords=[b.business_name for b in graph.businesses if b.status == "active"],
            industry_keywords=[i.industry_name for i in graph.industries],
            product_keywords=[p.product_name for p in graph.products],
            concept_keywords=[c.concept_name for c in graph.concepts]
        )
        
        # 生成组合查询
        keyword_set.combined_queries = keyword_set.generate_search_queries(max_queries=10)
        
        return keyword_set
    
    # ============ 图谱更新 ============
    
    def update_from_news(
        self,
        stock_code: str,
        news_content: str,
        extracted_info: Dict[str, Any]
    ) -> bool:
        """
        根据新闻更新图谱
        
        Args:
            stock_code: 股票代码
            news_content: 新闻内容
            extracted_info: 提取的信息（由 LLM 提取）
                {
                    "new_businesses": [...],
                    "stopped_businesses": [...],
                    "new_products": [...],
                    "new_concepts": [...]
                }
        
        Returns:
            是否成功
        """
        try:
            # 添加新业务线
            for biz_name in extracted_info.get("new_businesses", []):
                business = BusinessNode(
                    business_name=biz_name,
                    business_type="new",
                    status="active",
                    start_date=datetime.utcnow().strftime("%Y-%m-%d")
                )
                self.add_business(stock_code, business)
            
            # 停止业务线
            for biz_name in extracted_info.get("stopped_businesses", []):
                self.stop_business(stock_code, biz_name)
            
            # 添加新产品
            for prod_name in extracted_info.get("new_products", []):
                product = ProductNode(
                    product_name=prod_name,
                    product_type="service"
                )
                self._add_product(stock_code, product)
            
            # 添加新概念
            for concept_name in extracted_info.get("new_concepts", []):
                concept = ConceptNode(
                    concept_name=concept_name,
                    hot_level=5
                )
                self.add_concepts(stock_code, [concept])
            
            logger.info(f"✅ 图谱已更新（基于新闻）")
            return True
            
        except Exception as e:
            logger.error(f"❌ 图谱更新失败: {e}")
            return False
    
    # ============ 统计和管理 ============
    
    def get_graph_stats(self, stock_code: str) -> Dict[str, int]:
        """获取图谱统计信息"""
        query = """
        MATCH (c:Company {stock_code: $stock_code})
        OPTIONAL MATCH (c)-[:HAS_VARIANT]->(v:NameVariant)
        OPTIONAL MATCH (c)-[:OPERATES_IN]->(b:Business)
        OPTIONAL MATCH (c)-[:BELONGS_TO]->(i:Industry)
        OPTIONAL MATCH (c)-[:PROVIDES]->(p:Product)
        OPTIONAL MATCH (c)-[:RELATES_TO]->(k:Keyword)
        OPTIONAL MATCH (c)-[:INVOLVES]->(con:Concept)
        RETURN 
            count(DISTINCT v) as variants_count,
            count(DISTINCT b) as businesses_count,
            count(DISTINCT i) as industries_count,
            count(DISTINCT p) as products_count,
            count(DISTINCT k) as keywords_count,
            count(DISTINCT con) as concepts_count
        """
        
        try:
            results = self.neo4j.execute_query(query, {"stock_code": stock_code})
            if results:
                return dict(results[0])
            return {}
        except Exception as e:
            logger.error(f"查询图谱统计失败: {e}")
            return {}
    
    def delete_company_graph(self, stock_code: str) -> bool:
        """删除公司及其所有关联节点"""
        query = """
        MATCH (c:Company {stock_code: $stock_code})
        OPTIONAL MATCH (c)-[r]->(n)
        DETACH DELETE c, n
        """
        
        try:
            self.neo4j.execute_write(query, {"stock_code": stock_code})
            logger.info(f"✅ 公司图谱已删除: {stock_code}")
            return True
        except Exception as e:
            logger.error(f"❌ 图谱删除失败: {e}")
            return False
    
    def list_all_companies(self) -> List[Dict[str, str]]:
        """列出所有公司"""
        query = """
        MATCH (c:Company)
        RETURN c.stock_code as stock_code, 
               c.stock_name as stock_name, 
               c.industry as industry
        ORDER BY c.stock_code
        """
        
        try:
            return self.neo4j.execute_query(query)
        except Exception as e:
            logger.error(f"查询公司列表失败: {e}")
            return []


# 便捷函数
def get_graph_service() -> KnowledgeGraphService:
    """获取知识图谱服务实例"""
    return KnowledgeGraphService()

