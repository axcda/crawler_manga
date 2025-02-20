import time
import logging
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

class CacheManager:
    def __init__(self, ttl: int = 3600):
        """初始化缓存管理器
        
        Args:
            ttl: 缓存过期时间（秒），默认1小时
        """
        self.ttl = ttl
        self.cache: Dict[str, Tuple[Any, float]] = {}
        
    def get(self, key: str) -> Optional[Any]:
        """获取缓存数据
        
        Args:
            key: 缓存键
            
        Returns:
            缓存的数据，如果不存在或已过期则返回None
        """
        try:
            if key in self.cache:
                data, timestamp = self.cache[key]
                if time.time() - timestamp < self.ttl:
                    logger.debug(f"Cache hit for key: {key}")
                    return data
                logger.debug(f"Cache expired for key: {key}")
                del self.cache[key]
            return None
        except Exception as e:
            logger.error(f"Error getting cache for key {key}: {str(e)}")
            return None
        
    def set(self, key: str, value: Any) -> None:
        """设置缓存数据
        
        Args:
            key: 缓存键
            value: 要缓存的数据
        """
        try:
            self.cache[key] = (value, time.time())
            logger.debug(f"Cache set for key: {key}")
        except Exception as e:
            logger.error(f"Error setting cache for key {key}: {str(e)}")
        
    def delete(self, key: str) -> None:
        """删除缓存数据
        
        Args:
            key: 要删除的缓存键
        """
        try:
            if key in self.cache:
                del self.cache[key]
                logger.debug(f"Cache deleted for key: {key}")
        except Exception as e:
            logger.error(f"Error deleting cache for key {key}: {str(e)}")
        
    def clear(self) -> None:
        """清空所有缓存"""
        try:
            self.cache.clear()
            logger.debug("Cache cleared")
        except Exception as e:
            logger.error(f"Error clearing cache: {str(e)}")
        
    def cleanup_expired(self) -> None:
        """清理过期的缓存数据"""
        try:
            current_time = time.time()
            expired_keys = [
                key for key, (_, timestamp) in self.cache.items()
                if current_time - timestamp >= self.ttl
            ]
            for key in expired_keys:
                del self.cache[key]
            if expired_keys:
                logger.debug(f"Cleaned up {len(expired_keys)} expired cache entries")
        except Exception as e:
            logger.error(f"Error cleaning up expired cache: {str(e)}") 