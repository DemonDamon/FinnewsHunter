"""
向量存储封装 - 直接使用 agenticx.storage.vectordb_storages.milvus.MilvusStorage
提供简单的兼容性接口，充分利用 base 类的便利方法
"""
import logging
import asyncio
from typing import List, Dict, Any, Optional

from ..core.config import settings
from agenticx.storage.vectordb_storages.milvus import MilvusStorage
from agenticx.storage.vectordb_storages.base import VectorRecord, VectorDBQuery

logger = logging.getLogger(__name__)


class VectorStorage:
    """
    Milvus 向量存储封装类
    直接使用 agenticx.storage.vectordb_storages.milvus.MilvusStorage
    提供简单的兼容性接口，只做必要的接口转换
    """
    
    def __init__(
        self,
        host: str = None,
        port: int = None,
        collection_name: str = None,
        dim: int = None,
    ):
        """初始化向量存储"""
        self.host = host or settings.MILVUS_HOST
        self.port = port or settings.MILVUS_PORT
        self.collection_name = collection_name or settings.MILVUS_COLLECTION_NAME
        self.dim = dim or settings.MILVUS_DIM
        
        # 直接使用 agenticx MilvusStorage
        self.milvus_storage = MilvusStorage(
            dimension=self.dim,
            host=self.host,
            port=self.port,
            collection_name=self.collection_name
        )
        
        logger.info(f"Initialized VectorStorage using MilvusStorage: {self.collection_name}, dim={self.dim}")
    
    def _call_add_async(self, records: List[VectorRecord], timeout: int = 15) -> None:
        """辅助方法：在同步上下文中调用异步 add() 方法"""
        try:
            loop = asyncio.get_running_loop()
            future = asyncio.run_coroutine_threadsafe(self.milvus_storage.add(records), loop)
            try:
                future.result(timeout=timeout)
            except Exception:
                logger.warning(f"Vector insert timeout ({timeout}s), but data may have been inserted")
        except RuntimeError:
            try:
                asyncio.run(asyncio.wait_for(self.milvus_storage.add(records), timeout=timeout))
            except asyncio.TimeoutError:
                logger.warning(f"Vector insert timeout ({timeout}s), but data may have been inserted")
    
    def connect(self):
        """连接到 Milvus（兼容性方法）"""
        # MilvusStorage 在初始化时已经连接
        pass
    
    def create_collection(self, drop_existing: bool = False):
        """创建集合（兼容性方法）"""
        # MilvusStorage 在初始化时已经创建集合
        if drop_existing:
            self.milvus_storage.clear()
            self.milvus_storage = MilvusStorage(
                dimension=self.dim,
                host=self.host,
                port=self.port,
                collection_name=self.collection_name
            )
    
    def load_collection(self):
        """加载集合到内存（兼容性方法）"""
        self.milvus_storage.load()
    
    def store_embedding(
        self,
        news_id: int,
        embedding: List[float],
        text: str
    ) -> int:
        """存储单个向量（兼容性接口）"""
        record = VectorRecord(
            id=str(news_id),
            vector=embedding,
            payload={"news_id": news_id, "text": text[:65535]}
        )
        self._call_add_async([record], timeout=15)
        return news_id
    
    def store_embeddings_batch(
        self,
        news_ids: List[int],
        embeddings: List[List[float]],
        texts: List[str]
    ) -> List[int]:
        """批量存储向量（兼容性接口）"""
        records = [
            VectorRecord(
                id=str(news_id),
                vector=embedding,
                payload={"news_id": news_id, "text": text[:65535]}
            )
            for news_id, embedding, text in zip(news_ids, embeddings, texts)
        ]
        self._call_add_async(records, timeout=30)
        return news_ids
    
    def search_similar(
        self,
        query_embedding: List[float],
        top_k: int = 10,
        filter_expr: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """搜索相似向量（兼容性接口）"""
        query = VectorDBQuery(query_vector=query_embedding, top_k=top_k)
        results = self.milvus_storage.query(query)
        
        # 格式化结果
        formatted_results = []
        for result in results:
            payload = result.record.payload or {}
            news_id = payload.get("news_id")
            if news_id is None:
                try:
                    news_id = int(result.record.id)
                except (ValueError, TypeError):
                    continue
            
            # 简单的过滤支持
            if filter_expr and "news_id" in filter_expr:
                import re
                match = re.search(r'news_id\s*==\s*(\d+)', filter_expr)
                if match and news_id != int(match.group(1)):
                    continue
            
            formatted_results.append({
                "id": result.record.id,
                "news_id": news_id,
                "text": payload.get("text", ""),
                "distance": result.similarity,
                "score": 1 / (1 + result.similarity) if result.similarity > 0 else 1.0,
            })
        
        return formatted_results
    
    def delete_by_news_id(self, news_id: int):
        """删除指定新闻的向量（兼容性接口）"""
        self.milvus_storage.delete([str(news_id)])
    
    def verify_insert(self, news_id: int, wait_for_flush: bool = True) -> bool:
        """验证数据是否成功插入（兼容性接口）"""
        if wait_for_flush:
            import time
            time.sleep(3)
        
        # 使用 base 类的 get_payloads_by_vector 方法
        zero_vector = [0.0] * self.dim
        payloads = self.milvus_storage.get_payloads_by_vector(zero_vector, top_k=1000)
        
        for payload in payloads:
            if payload and payload.get("news_id") == news_id:
                return True
        return False
    
    def get_stats(self) -> Dict[str, Any]:
        """获取集合统计信息（兼容性接口）
        
        注意：如果 num_entities 为 0，会通过实际查询来获取真实数量
        （因为 flush 失败时 num_entities 可能不准确）
        """
        status = self.milvus_storage.status()
        num_entities = status.vector_count
        
        # 如果 num_entities 为 0，尝试通过查询获取真实数量
        # 这可以解决 flush 失败导致统计不准确的问题
        if num_entities == 0:
            try:
                from agenticx.storage.vectordb_storages.base import VectorDBQuery
                # 使用零向量查询，设置一个较大的 top_k 来获取实际数量
                zero_vector = [0.0] * status.vector_dim
                query = VectorDBQuery(query_vector=zero_vector, top_k=10000)  # 最多查询10000条
                results = self.milvus_storage.query(query)
                if results:
                    num_entities = len(results)
                    # 如果返回了10000条，说明可能还有更多，标记为近似值
                    if len(results) >= 10000:
                        num_entities = f"{len(results)}+ (近似值，实际可能更多)"
            except Exception as e:
                logger.debug(f"无法通过查询获取真实数量: {e}")
                # 如果查询失败，仍然使用 num_entities=0
        
        return {
            "num_entities": num_entities,
            "collection_name": self.collection_name,
            "dim": status.vector_dim,
        }
    
    def disconnect(self):
        """断开连接（兼容性方法）"""
        self.milvus_storage.close()
    
    @property
    def collection(self):
        """兼容性属性：返回底层的 Milvus collection 对象"""
        return self.milvus_storage.collection


# 全局实例
_vector_storage: Optional[VectorStorage] = None


def get_vector_storage() -> VectorStorage:
    """获取向量存储实例（单例模式）"""
    global _vector_storage
    if _vector_storage is None:
        _vector_storage = VectorStorage()
    return _vector_storage
