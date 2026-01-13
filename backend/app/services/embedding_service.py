"""
Embedding 服务封装
使用 agenticx.embeddings.BailianEmbeddingProvider
"""
import logging
import asyncio
from typing import List, Optional
import redis
import hashlib
import json

from ..core.config import settings
from agenticx.embeddings import BailianEmbeddingProvider

logger = logging.getLogger(__name__)


class EmbeddingService:
    """
    Embedding 服务封装类
    基于 agenticx.embeddings.BailianEmbeddingProvider
    提供文本向量化功能，支持缓存
    """
    
    def __init__(
        self,
        provider: str = None,
        model: str = None,
        batch_size: int = None,
        enable_cache: bool = True,
        base_url: str = None,
    ):
        """
        初始化 Embedding 服务
        
        Args:
            provider: 提供商（保留参数以兼容，实际使用 bailian）
            model: 模型名称
            batch_size: 批处理大小
            enable_cache: 是否启用Redis缓存
            base_url: 自定义 API 端点（用于百炼等第三方服务）
        """
        self.provider = provider or settings.EMBEDDING_PROVIDER
        self.model = model or settings.EMBEDDING_MODEL
        self.batch_size = batch_size or settings.EMBEDDING_BATCH_SIZE
        self.enable_cache = enable_cache
        self.base_url = base_url or settings.EMBEDDING_BASE_URL
        
        # 获取 API Key
        api_key = settings.DASHSCOPE_API_KEY
        if not api_key:
            # 如果没有 DASHSCOPE_API_KEY，尝试使用 OPENAI_API_KEY（向后兼容）
            api_key = settings.OPENAI_API_KEY
            if not api_key:
                raise ValueError("DASHSCOPE_API_KEY or OPENAI_API_KEY is required for embedding")
        
        # 设置 API URL
        api_url = self.base_url or settings.DASHSCOPE_BASE_URL or "https://dashscope.aliyuncs.com/compatible-mode/v1"
        
        # 初始化 agenticx BailianEmbeddingProvider
        self.provider_instance = BailianEmbeddingProvider(
            api_key=api_key,
            model=self.model,
            api_url=api_url,
            batch_size=self.batch_size,
            timeout=settings.EMBEDDING_TIMEOUT,
            retry_count=settings.EMBEDDING_MAX_RETRIES,
            dimensions=settings.MILVUS_DIM,  # 确保维度匹配
            use_dashscope_sdk=False  # 使用 HTTP API，避免 SDK 依赖问题
        )
        
        logger.info(f"Initialized BailianEmbeddingProvider: {self.model}, dimension={self.provider_instance.get_embedding_dim()}")
        
        # 初始化Redis缓存
        if self.enable_cache:
            try:
                self.redis_client = redis.from_url(settings.REDIS_URL)
                self.cache_ttl = 86400 * 7  # 7天
                logger.info("Redis cache enabled for embeddings")
            except Exception as e:
                logger.warning(f"Failed to connect to Redis, cache disabled: {e}")
                self.enable_cache = False
    
    def _get_cache_key(self, text: str) -> str:
        """生成缓存键"""
        # 使用文本的MD5哈希和模型名称作为键
        text_hash = hashlib.md5(text.encode()).hexdigest()
        return f"embedding:{self.model}:{text_hash}"
    
    def _get_from_cache(self, text: str) -> Optional[List[float]]:
        """从缓存获取向量"""
        if not self.enable_cache:
            return None
        
        try:
            cache_key = self._get_cache_key(text)
            cached = self.redis_client.get(cache_key)
            if cached:
                return json.loads(cached)
        except Exception as e:
            logger.warning(f"Failed to get from cache: {e}")
        
        return None
    
    def _save_to_cache(self, text: str, embedding: List[float]):
        """保存向量到缓存"""
        if not self.enable_cache:
            return
        
        try:
            cache_key = self._get_cache_key(text)
            self.redis_client.setex(
                cache_key,
                self.cache_ttl,
                json.dumps(embedding)
            )
        except Exception as e:
            logger.warning(f"Failed to save to cache: {e}")
    
    def embed_text(self, text: str) -> List[float]:
        """
        将文本转换为向量
        
        Args:
            text: 文本
            
        Returns:
            向量（List[float]）
        """
        # 检查缓存
        cached = self._get_from_cache(text)
        if cached is not None:
            return cached
        
        # 限制文本长度（避免超过模型限制）
        max_length = 6000
        if len(text) > max_length:
            logger.warning(f"Text too long ({len(text)} chars), truncating to {max_length} chars")
            text = text[:max_length]
        
        # 生成向量（使用 agenticx provider）
        # 注意：embed() 方法内部使用 asyncio.run()，在同步上下文中可以直接调用
        # 如果在异步上下文中调用此同步方法，应该在 ThreadPoolExecutor 中运行
        try:
            # 直接调用 embed()，它内部会使用 asyncio.run() 创建新的事件循环
            # 这在同步上下文中可以正常工作
            # 如果在异步上下文中，调用者应该在 ThreadPoolExecutor 中运行此方法
            embeddings = self.provider_instance.embed([text])
            embedding = embeddings[0] if embeddings else []
            
            # 保存到缓存
            self._save_to_cache(text, embedding)
            
            return embedding
        
        except Exception as e:
            logger.error(f"Embedding failed for text: {text[:100]}..., error: {e}")
            raise
    
    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """
        批量将文本转换为向量
        
        Args:
            texts: 文本列表
            
        Returns:
            向量列表
        """
        if not texts:
            return []
        
        # 检查缓存并分离需要处理的文本
        embeddings_map = {}  # {index: embedding}
        texts_to_embed = []  # [(index, text), ...]
        
        max_length = 6000
        for idx, text in enumerate(texts):
            # 检查缓存
            cached = self._get_from_cache(text)
            if cached is not None:
                embeddings_map[idx] = cached
            else:
                # 限制文本长度
                if len(text) > max_length:
                    logger.warning(f"Text too long ({len(text)} chars), truncating to {max_length} chars")
                    text = text[:max_length]
                texts_to_embed.append((idx, text))
        
        # 对未缓存的文本批量生成向量
        # 注意：BailianEmbeddingProvider.embed() 内部已经会分批处理，不需要我们再次分批
        if texts_to_embed:
            try:
                texts_list = [t[1] for t in texts_to_embed]
                # 直接调用 embed()，它内部会使用 asyncio.run() 创建新的事件循环
                # BailianEmbeddingProvider 内部会根据 batch_size 自动分批处理
                new_embeddings = self.provider_instance.embed(texts_list)
                
                # 保存到缓存并添加到结果
                for (idx, text), embedding in zip(texts_to_embed, new_embeddings):
                    self._save_to_cache(text, embedding)
                    embeddings_map[idx] = embedding
            
            except Exception as e:
                logger.error(f"Batch embedding failed: {e}")
                raise
        
        # 按原始顺序返回结果
        return [embeddings_map.get(i, []) for i in range(len(texts))]
    
    async def aembed_text(self, text: str) -> List[float]:
        """
        异步将文本转换为向量（推荐在异步上下文中使用）
        
        Args:
            text: 文本
            
        Returns:
            向量（List[float]）
        """
        # 检查缓存
        cached = self._get_from_cache(text)
        if cached is not None:
            return cached
        
        # 限制文本长度（避免超过模型限制）
        max_length = 6000
        if len(text) > max_length:
            logger.warning(f"Text too long ({len(text)} chars), truncating to {max_length} chars")
            text = text[:max_length]
        
        # 使用异步接口，避免 asyncio.run() 的问题
        try:
            embeddings = await self.provider_instance.aembed([text])
            embedding = embeddings[0] if embeddings else []
            
            # 保存到缓存
            self._save_to_cache(text, embedding)
            
            return embedding
        
        except Exception as e:
            logger.error(f"Embedding failed for text: {text[:100]}..., error: {e}")
            raise
    
    async def aembed_batch(self, texts: List[str]) -> List[List[float]]:
        """
        异步批量将文本转换为向量（推荐在异步上下文中使用）
        
        Args:
            texts: 文本列表
            
        Returns:
            向量列表
        """
        if not texts:
            return []
        
        # 检查缓存并分离需要处理的文本
        embeddings_map = {}  # {index: embedding}
        texts_to_embed = []  # [(index, text), ...]
        
        max_length = 6000
        for idx, text in enumerate(texts):
            # 检查缓存
            cached = self._get_from_cache(text)
            if cached is not None:
                embeddings_map[idx] = cached
            else:
                # 限制文本长度
                if len(text) > max_length:
                    logger.warning(f"Text too long ({len(text)} chars), truncating to {max_length} chars")
                    text = text[:max_length]
                texts_to_embed.append((idx, text))
        
        # 对未缓存的文本批量生成向量
        # BailianEmbeddingProvider.aembed() 内部已经会分批处理
        if texts_to_embed:
            try:
                texts_list = [t[1] for t in texts_to_embed]
                # 使用异步接口，避免 asyncio.run() 的问题
                new_embeddings = await self.provider_instance.aembed(texts_list)
                
                # 保存到缓存并添加到结果
                for (idx, text), embedding in zip(texts_to_embed, new_embeddings):
                    self._save_to_cache(text, embedding)
                    embeddings_map[idx] = embedding
            
            except Exception as e:
                logger.error(f"Batch embedding failed: {e}")
                raise
        
        # 按原始顺序返回结果
        return [embeddings_map.get(i, []) for i in range(len(texts))]


# 全局实例
_embedding_service: Optional[EmbeddingService] = None


def get_embedding_service() -> EmbeddingService:
    """
    获取 Embedding 服务实例（单例模式）
    
    Returns:
        EmbeddingService 实例
    """
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = EmbeddingService()
    return _embedding_service
