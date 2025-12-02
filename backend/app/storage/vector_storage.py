"""
向量存储封装 - 基于 Milvus
"""
import logging
from typing import List, Dict, Any, Optional
from pymilvus import (
    connections,
    Collection,
    CollectionSchema,
    FieldSchema,
    DataType,
    utility,
)

from ..core.config import settings

logger = logging.getLogger(__name__)


class VectorStorage:
    """
    Milvus 向量存储封装类
    用于存储和检索新闻文本的向量表示
    """
    
    def __init__(
        self,
        host: str = None,
        port: int = None,
        collection_name: str = None,
        dim: int = None,
    ):
        """
        初始化向量存储
        
        Args:
            host: Milvus 主机地址
            port: Milvus 端口
            collection_name: 集合名称
            dim: 向量维度
        """
        self.host = host or settings.MILVUS_HOST
        self.port = port or settings.MILVUS_PORT
        self.collection_name = collection_name or settings.MILVUS_COLLECTION_NAME
        self.dim = dim or settings.MILVUS_DIM
        self.collection: Optional[Collection] = None
        
    def connect(self):
        """连接到 Milvus"""
        try:
            connections.connect(
                alias="default",
                host=self.host,
                port=self.port
            )
            logger.info(f"Connected to Milvus at {self.host}:{self.port}")
        except Exception as e:
            logger.error(f"Failed to connect to Milvus: {e}")
            raise
    
    def create_collection(self, drop_existing: bool = False):
        """
        创建集合
        
        Args:
            drop_existing: 是否删除已存在的集合
        """
        # 检查集合是否存在
        if utility.has_collection(self.collection_name):
            if drop_existing:
                utility.drop_collection(self.collection_name)
                logger.info(f"Dropped existing collection: {self.collection_name}")
            else:
                logger.info(f"Collection already exists: {self.collection_name}")
                self.collection = Collection(self.collection_name)
                return
        
        # 定义字段
        fields = [
            FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=True),
            FieldSchema(name="news_id", dtype=DataType.INT64),
            FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=self.dim),
            FieldSchema(name="text", dtype=DataType.VARCHAR, max_length=65535),
        ]
        
        # 创建集合模式
        schema = CollectionSchema(
            fields=fields,
            description="Financial news embeddings"
        )
        
        # 创建集合
        self.collection = Collection(
            name=self.collection_name,
            schema=schema,
            using="default"
        )
        
        logger.info(f"Created collection: {self.collection_name}")
        
        # 创建索引
        index_params = {
            "metric_type": "L2",
            "index_type": "IVF_FLAT",
            "params": {"nlist": 1024}
        }
        self.collection.create_index(
            field_name="embedding",
            index_params=index_params
        )
        logger.info("Created index for embedding field")
    
    def load_collection(self):
        """加载集合到内存"""
        if self.collection is None:
            self.collection = Collection(self.collection_name)
        self.collection.load()
        logger.info(f"Loaded collection: {self.collection_name}")
    
    def store_embedding(
        self,
        news_id: int,
        embedding: List[float],
        text: str
    ) -> int:
        """
        存储单个向量
        
        Args:
            news_id: 新闻ID
            embedding: 向量
            text: 原始文本
            
        Returns:
            插入的记录ID
        """
        if self.collection is None:
            self.load_collection()
        
        entities = [
            [news_id],
            [embedding],
            [text[:65535]],  # 截断文本以符合最大长度
        ]
        
        result = self.collection.insert(entities)
        self.collection.flush()
        
        return result.primary_keys[0]
    
    def store_embeddings_batch(
        self,
        news_ids: List[int],
        embeddings: List[List[float]],
        texts: List[str]
    ) -> List[int]:
        """
        批量存储向量
        
        Args:
            news_ids: 新闻ID列表
            embeddings: 向量列表
            texts: 文本列表
            
        Returns:
            插入的记录ID列表
        """
        if self.collection is None:
            self.load_collection()
        
        # 截断文本
        truncated_texts = [text[:65535] for text in texts]
        
        entities = [
            news_ids,
            embeddings,
            truncated_texts,
        ]
        
        result = self.collection.insert(entities)
        self.collection.flush()
        
        return result.primary_keys
    
    def search_similar(
        self,
        query_embedding: List[float],
        top_k: int = 10,
        filter_expr: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        搜索相似向量
        
        Args:
            query_embedding: 查询向量
            top_k: 返回的结果数量
            filter_expr: 过滤表达式（可选）
            
        Returns:
            相似结果列表
        """
        if self.collection is None:
            self.load_collection()
        
        search_params = {
            "metric_type": "L2",
            "params": {"nprobe": 10}
        }
        
        results = self.collection.search(
            data=[query_embedding],
            anns_field="embedding",
            param=search_params,
            limit=top_k,
            expr=filter_expr,
            output_fields=["news_id", "text"]
        )
        
        # 格式化结果
        formatted_results = []
        for hits in results:
            for hit in hits:
                formatted_results.append({
                    "id": hit.id,
                    "news_id": hit.entity.get("news_id"),
                    "text": hit.entity.get("text"),
                    "distance": hit.distance,
                    "score": 1 / (1 + hit.distance),  # 转换为相似度分数
                })
        
        return formatted_results
    
    def delete_by_news_id(self, news_id: int):
        """
        删除指定新闻的向量
        
        Args:
            news_id: 新闻ID
        """
        if self.collection is None:
            self.load_collection()
        
        expr = f"news_id == {news_id}"
        self.collection.delete(expr)
        logger.info(f"Deleted embeddings for news_id: {news_id}")
    
    def get_stats(self) -> Dict[str, Any]:
        """
        获取集合统计信息
        
        Returns:
            统计信息字典
        """
        if self.collection is None:
            self.load_collection()
        
        return {
            "num_entities": self.collection.num_entities,
            "collection_name": self.collection_name,
            "dim": self.dim,
        }
    
    def disconnect(self):
        """断开连接"""
        connections.disconnect("default")
        logger.info("Disconnected from Milvus")


# 全局实例
_vector_storage: Optional[VectorStorage] = None


def get_vector_storage() -> VectorStorage:
    """
    获取向量存储实例（单例模式）
    
    Returns:
        VectorStorage 实例
    """
    global _vector_storage
    if _vector_storage is None:
        _vector_storage = VectorStorage()
        _vector_storage.connect()
        _vector_storage.create_collection()
        _vector_storage.load_collection()
    return _vector_storage

