"""
Embedding 服务封装
"""
import logging
from typing import List, Optional
import redis
import hashlib
import json

from ..core.config import settings

logger = logging.getLogger(__name__)


class EmbeddingService:
    """
    Embedding 服务封装类
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
            provider: 提供商（openai, huggingface）
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
        
        # 初始化客户端
        if self.provider == "openai":
            self._init_openai()
        elif self.provider == "huggingface":
            self._init_huggingface()
        else:
            raise ValueError(f"Unsupported embedding provider: {self.provider}")
        
        # 初始化Redis缓存
        if self.enable_cache:
            try:
                self.redis_client = redis.from_url(settings.REDIS_URL)
                self.cache_ttl = 86400 * 7  # 7天
                logger.info("Redis cache enabled for embeddings")
            except Exception as e:
                logger.warning(f"Failed to connect to Redis, cache disabled: {e}")
                self.enable_cache = False
    
    def _init_openai(self):
        """初始化 OpenAI 客户端"""
        try:
            from openai import OpenAI
            
            # 构建客户端配置
            client_kwargs = {"api_key": settings.OPENAI_API_KEY}
            
            # 如果设置了自定义 base_url（例如百炼）
            if self.base_url:
                client_kwargs["base_url"] = self.base_url
                logger.info(f"Using custom embedding base URL: {self.base_url}")
            
            self.client = OpenAI(**client_kwargs)
            logger.info(f"Initialized OpenAI embedding: {self.model}")
        except Exception as e:
            logger.error(f"Failed to initialize OpenAI: {e}")
            raise
    
    def _init_huggingface(self):
        """初始化 HuggingFace 模型"""
        try:
            from sentence_transformers import SentenceTransformer
            self.client = SentenceTransformer(self.model)
            logger.info(f"Initialized HuggingFace embedding: {self.model}")
        except Exception as e:
            logger.error(f"Failed to initialize HuggingFace: {e}")
            raise
    
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
        
        # 生成向量
        try:
            if self.provider == "openai":
                embedding = self._embed_openai(text)
            elif self.provider == "huggingface":
                embedding = self._embed_huggingface(text)
            else:
                raise ValueError(f"Unsupported provider: {self.provider}")
            
            # 保存到缓存
            self._save_to_cache(text, embedding)
            
            return embedding
        
        except Exception as e:
            logger.error(f"Embedding failed for text: {text[:100]}..., error: {e}")
            raise
    
    def _embed_openai(self, text: str) -> List[float]:
        """使用 OpenAI API 生成向量"""
        response = self.client.embeddings.create(
            model=self.model,
            input=text
        )
        return response.data[0].embedding
    
    def _embed_huggingface(self, text: str) -> List[float]:
        """使用 HuggingFace 模型生成向量"""
        embedding = self.client.encode(text, convert_to_numpy=True)
        return embedding.tolist()
    
    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """
        批量将文本转换为向量
        
        Args:
            texts: 文本列表
            
        Returns:
            向量列表
        """
        embeddings = []
        
        # 分批处理
        for i in range(0, len(texts), self.batch_size):
            batch = texts[i:i + self.batch_size]
            
            # 检查缓存
            batch_embeddings = []
            texts_to_embed = []
            cached_indices = []
            
            for idx, text in enumerate(batch):
                cached = self._get_from_cache(text)
                if cached is not None:
                    batch_embeddings.append((idx, cached))
                    cached_indices.append(idx)
                else:
                    texts_to_embed.append((idx, text))
            
            # 生成未缓存的向量
            if texts_to_embed:
                try:
                    if self.provider == "openai":
                        new_embeddings = self._embed_batch_openai([t[1] for t in texts_to_embed])
                    elif self.provider == "huggingface":
                        new_embeddings = self._embed_batch_huggingface([t[1] for t in texts_to_embed])
                    else:
                        raise ValueError(f"Unsupported provider: {self.provider}")
                    
                    # 保存到缓存并添加到结果
                    for (idx, text), embedding in zip(texts_to_embed, new_embeddings):
                        self._save_to_cache(text, embedding)
                        batch_embeddings.append((idx, embedding))
                
                except Exception as e:
                    logger.error(f"Batch embedding failed: {e}")
                    raise
            
            # 按原始顺序排序
            batch_embeddings.sort(key=lambda x: x[0])
            embeddings.extend([emb for _, emb in batch_embeddings])
        
        return embeddings
    
    def _embed_batch_openai(self, texts: List[str]) -> List[List[float]]:
        """批量使用 OpenAI API 生成向量"""
        response = self.client.embeddings.create(
            model=self.model,
            input=texts
        )
        return [item.embedding for item in response.data]
    
    def _embed_batch_huggingface(self, texts: List[str]) -> List[List[float]]:
        """批量使用 HuggingFace 模型生成向量"""
        embeddings = self.client.encode(texts, convert_to_numpy=True)
        return [emb.tolist() for emb in embeddings]


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

