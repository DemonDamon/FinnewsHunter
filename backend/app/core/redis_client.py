"""
Redis Client for Caching and Task Queue
"""
import json
import logging
from typing import Optional, Any
from datetime import datetime, timedelta

import redis
from app.core.config import settings

logger = logging.getLogger(__name__)


class RedisClient:
    """Redis client wrapper with JSON serialization support"""
    
    def __init__(self):
        try:
            self.client = redis.Redis(
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                db=settings.REDIS_DB,
                password=settings.REDIS_PASSWORD if settings.REDIS_PASSWORD else None,
                decode_responses=True,  # 自动解码为字符串
                socket_connect_timeout=5,
                socket_timeout=5,
            )
            # 测试连接
            self.client.ping()
            logger.info(f"✅ Redis connected: {settings.REDIS_HOST}:{settings.REDIS_PORT}")
        except Exception as e:
            logger.error(f"❌ Redis connection failed: {e}")
            self.client = None
    
    def is_available(self) -> bool:
        """检查 Redis 是否可用"""
        try:
            if self.client:
                self.client.ping()
                return True
        except:
            pass
        return False
    
    def get_json(self, key: str) -> Optional[Any]:
        """获取 JSON 数据"""
        if not self.is_available():
            return None
        
        try:
            value = self.client.get(key)
            if value:
                return json.loads(value)
        except Exception as e:
            logger.error(f"Redis get_json error: {e}")
        return None
    
    def set_json(self, key: str, value: Any, ttl: int = None) -> bool:
        """存储 JSON 数据"""
        if not self.is_available():
            return False
        
        try:
            json_str = json.dumps(value, ensure_ascii=False, default=str)
            if ttl:
                self.client.setex(key, ttl, json_str)
            else:
                self.client.set(key, json_str)
            return True
        except Exception as e:
            logger.error(f"Redis set_json error: {e}")
            return False
    
    def get(self, key: str) -> Optional[str]:
        """获取字符串数据"""
        if not self.is_available():
            return None
        
        try:
            return self.client.get(key)
        except Exception as e:
            logger.error(f"Redis get error: {e}")
            return None
    
    def set(self, key: str, value: str, ttl: int = None) -> bool:
        """存储字符串数据"""
        if not self.is_available():
            return False
        
        try:
            if ttl:
                self.client.setex(key, ttl, value)
            else:
                self.client.set(key, value)
            return True
        except Exception as e:
            logger.error(f"Redis set error: {e}")
            return False
    
    def delete(self, key: str) -> bool:
        """删除键"""
        if not self.is_available():
            return False
        
        try:
            self.client.delete(key)
            return True
        except Exception as e:
            logger.error(f"Redis delete error: {e}")
            return False
    
    def exists(self, key: str) -> bool:
        """检查键是否存在"""
        if not self.is_available():
            return False
        
        try:
            return self.client.exists(key) > 0
        except Exception as e:
            logger.error(f"Redis exists error: {e}")
            return False
    
    def get_cache_metadata(self, key: str) -> Optional[dict]:
        """获取缓存元数据（时间戳）"""
        time_key = f"{key}:timestamp"
        timestamp_str = self.get(time_key)
        
        if timestamp_str:
            try:
                return {
                    "timestamp": datetime.fromisoformat(timestamp_str),
                    "age_seconds": (datetime.now() - datetime.fromisoformat(timestamp_str)).total_seconds()
                }
            except:
                pass
        return None
    
    def set_with_metadata(self, key: str, value: Any, ttl: int = None) -> bool:
        """存储数据并记录时间戳"""
        success = self.set_json(key, value, ttl)
        if success:
            time_key = f"{key}:timestamp"
            self.set(time_key, datetime.now().isoformat(), ttl)
        return success
    
    def clear_pattern(self, pattern: str) -> int:
        """清除匹配模式的所有键"""
        if not self.is_available():
            return 0
        
        try:
            keys = self.client.keys(pattern)
            if keys:
                return self.client.delete(*keys)
        except Exception as e:
            logger.error(f"Redis clear_pattern error: {e}")
        return 0


# 全局单例
redis_client = RedisClient()

