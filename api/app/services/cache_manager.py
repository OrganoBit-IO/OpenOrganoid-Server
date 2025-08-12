import json
import asyncio
from typing import Optional, Dict, Any, List, Union
from datetime import datetime, timedelta
import structlog

import redis.asyncio as redis
from redis.exceptions import ConnectionError, TimeoutError

logger = structlog.get_logger()


class CacheManager:
    """Redis-based cache management service"""
    
    def __init__(self, redis_url: str, default_ttl: int = 3600):
        self.redis_url = redis_url
        self.default_ttl = default_ttl
        self.redis: Optional[redis.Redis] = None
        self._initialized = False
    
    async def initialize(self) -> None:
        """Initialize Redis connection"""
        if self._initialized:
            return
        
        try:
            self.redis = redis.from_url(
                self.redis_url,
                encoding='utf-8',
                decode_responses=True,
                retry_on_timeout=True,
                health_check_interval=30
            )
            
            # Test connection
            await self.redis.ping()
            
            self._initialized = True
            logger.info("Cache manager initialized", redis_url=self.redis_url)
            
        except (ConnectionError, TimeoutError) as e:
            logger.error("Failed to connect to Redis", error=str(e))
            raise
    
    async def cleanup(self) -> None:
        """Cleanup Redis connection"""
        if self.redis:
            await self.redis.close()
            self._initialized = False
            logger.info("Cache manager cleaned up")
    
    def _ensure_initialized(self):
        """Ensure cache manager is initialized"""
        if not self._initialized or not self.redis:
            raise RuntimeError("Cache manager not initialized")
    
    # Dataset metadata caching
    async def cache_dataset_metadata(self, 
                                   dataset_id: str, 
                                   metadata: Dict[str, Any],
                                   ttl: Optional[int] = None) -> None:
        """Cache dataset metadata with structured keys"""
        self._ensure_initialized()
        
        cache_key = f"dataset:{dataset_id}:metadata"
        ttl = ttl or self.default_ttl
        
        try:
            # Store as hash for partial updates
            async with self.redis.pipeline() as pipe:
                await pipe.delete(cache_key)  # Clear existing data
                await pipe.hset(cache_key, mapping={
                    k: json.dumps(v) if isinstance(v, (dict, list)) else str(v)
                    for k, v in metadata.items()
                })
                await pipe.expire(cache_key, ttl)
                await pipe.execute()
                
            logger.debug("Dataset metadata cached", dataset_id=dataset_id)
            
        except Exception as e:
            logger.error("Failed to cache dataset metadata", 
                        dataset_id=dataset_id, error=str(e))
            raise
    
    async def get_dataset_metadata(self, dataset_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve cached dataset metadata"""
        self._ensure_initialized()
        
        cache_key = f"dataset:{dataset_id}:metadata"
        
        try:
            cached_data = await self.redis.hgetall(cache_key)
            
            if not cached_data:
                return None
            
            # Deserialize JSON fields
            metadata = {}
            for field, value in cached_data.items():
                try:
                    metadata[field] = json.loads(value)
                except json.JSONDecodeError:
                    metadata[field] = value
            
            logger.debug("Dataset metadata retrieved from cache", dataset_id=dataset_id)
            return metadata
            
        except Exception as e:
            logger.error("Failed to get dataset metadata", 
                        dataset_id=dataset_id, error=str(e))
            return None
    
    async def update_dataset_metadata_field(self, 
                                          dataset_id: str, 
                                          field: str, 
                                          value: Any,
                                          ttl: Optional[int] = None) -> None:
        """Update specific field in cached dataset metadata"""
        self._ensure_initialized()
        
        cache_key = f"dataset:{dataset_id}:metadata"
        ttl = ttl or self.default_ttl
        
        try:
            serialized_value = json.dumps(value) if isinstance(value, (dict, list)) else str(value)
            
            async with self.redis.pipeline() as pipe:
                await pipe.hset(cache_key, field, serialized_value)
                await pipe.expire(cache_key, ttl)
                await pipe.execute()
                
            logger.debug("Dataset metadata field updated", 
                        dataset_id=dataset_id, field=field)
            
        except Exception as e:
            logger.error("Failed to update dataset metadata field", 
                        dataset_id=dataset_id, field=field, error=str(e))
            raise
    
    # File metadata caching
    async def cache_file_metadata(self, 
                                dataset_id: str,
                                file_path: str,
                                metadata: Dict[str, Any],
                                ttl: Optional[int] = None) -> None:
        """Cache file metadata"""
        self._ensure_initialized()
        
        cache_key = f"dataset:{dataset_id}:file:{file_path}"
        ttl = ttl or self.default_ttl
        
        try:
            serialized_metadata = json.dumps(metadata)
            await self.redis.setex(cache_key, ttl, serialized_metadata)
            
            logger.debug("File metadata cached", 
                        dataset_id=dataset_id, file_path=file_path)
            
        except Exception as e:
            logger.error("Failed to cache file metadata", 
                        dataset_id=dataset_id, file_path=file_path, error=str(e))
            raise
    
    async def get_file_metadata(self, dataset_id: str, file_path: str) -> Optional[Dict[str, Any]]:
        """Retrieve cached file metadata"""
        self._ensure_initialized()
        
        cache_key = f"dataset:{dataset_id}:file:{file_path}"
        
        try:
            cached_data = await self.redis.get(cache_key)
            
            if cached_data:
                return json.loads(cached_data)
            
            return None
            
        except Exception as e:
            logger.error("Failed to get file metadata", 
                        dataset_id=dataset_id, file_path=file_path, error=str(e))
            return None
    
    # User session caching
    async def cache_user_session(self, 
                                user_id: str, 
                                session_data: Dict[str, Any],
                                ttl: int = 3600) -> None:
        """Cache user session data"""
        self._ensure_initialized()
        
        cache_key = f"session:{user_id}"
        
        try:
            serialized_data = json.dumps(session_data)
            await self.redis.setex(cache_key, ttl, serialized_data)
            
            logger.debug("User session cached", user_id=user_id)
            
        except Exception as e:
            logger.error("Failed to cache user session", user_id=user_id, error=str(e))
            raise
    
    async def get_user_session(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve cached user session"""
        self._ensure_initialized()
        
        cache_key = f"session:{user_id}"
        
        try:
            cached_data = await self.redis.get(cache_key)
            
            if cached_data:
                return json.loads(cached_data)
            
            return None
            
        except Exception as e:
            logger.error("Failed to get user session", user_id=user_id, error=str(e))
            return None
    
    # Dataset popularity tracking
    async def increment_dataset_access(self, dataset_id: str) -> None:
        """Track dataset access for popularity metrics"""
        self._ensure_initialized()
        
        try:
            # Daily access counter
            today = datetime.utcnow().strftime('%Y-%m-%d')
            daily_key = f"access:daily:{today}"
            
            # Overall access counter
            total_key = f"access:total"
            
            async with self.redis.pipeline() as pipe:
                await pipe.hincrby(daily_key, dataset_id, 1)
                await pipe.expire(daily_key, 86400 * 7)  # Keep for 7 days
                await pipe.hincrby(total_key, dataset_id, 1)
                await pipe.execute()
            
        except Exception as e:
            logger.error("Failed to track dataset access", 
                        dataset_id=dataset_id, error=str(e))
    
    async def get_popular_datasets(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get most popular datasets by access count"""
        self._ensure_initialized()
        
        try:
            # Get from daily stats first
            today = datetime.utcnow().strftime('%Y-%m-%d')
            daily_key = f"access:daily:{today}"
            
            daily_stats = await self.redis.hgetall(daily_key)
            
            if daily_stats:
                # Sort by access count
                popular = sorted(
                    [(dataset_id, int(count)) for dataset_id, count in daily_stats.items()],
                    key=lambda x: x[1],
                    reverse=True
                )[:limit]
                
                return [{"dataset_id": dataset_id, "access_count": count} 
                       for dataset_id, count in popular]
            
            return []
            
        except Exception as e:
            logger.error("Failed to get popular datasets", error=str(e))
            return []
    
    # Cache invalidation
    async def invalidate_dataset_cache(self, dataset_id: str) -> None:
        """Remove all cached data for a dataset"""
        self._ensure_initialized()
        
        try:
            pattern = f"dataset:{dataset_id}:*"
            
            # Use SCAN to find keys (more efficient than KEYS)
            keys_to_delete = []
            async for key in self.redis.scan_iter(match=pattern):
                keys_to_delete.append(key)
            
            if keys_to_delete:
                await self.redis.delete(*keys_to_delete)
                logger.info("Dataset cache invalidated", 
                           dataset_id=dataset_id, keys_deleted=len(keys_to_delete))
            
        except Exception as e:
            logger.error("Failed to invalidate dataset cache", 
                        dataset_id=dataset_id, error=str(e))
    
    async def invalidate_user_cache(self, user_id: str) -> None:
        """Remove all cached data for a user"""
        self._ensure_initialized()
        
        try:
            pattern = f"session:{user_id}*"
            
            keys_to_delete = []
            async for key in self.redis.scan_iter(match=pattern):
                keys_to_delete.append(key)
            
            if keys_to_delete:
                await self.redis.delete(*keys_to_delete)
                logger.info("User cache invalidated", 
                           user_id=user_id, keys_deleted=len(keys_to_delete))
            
        except Exception as e:
            logger.error("Failed to invalidate user cache", user_id=user_id, error=str(e))
    
    # Task queue support (for Celery integration)
    async def enqueue_task(self, 
                          queue_name: str, 
                          task_data: Dict[str, Any],
                          priority: int = 0) -> str:
        """Enqueue task for background processing"""
        self._ensure_initialized()
        
        try:
            task_id = f"task:{datetime.utcnow().timestamp()}:{queue_name}"
            task_payload = {
                "id": task_id,
                "data": task_data,
                "priority": priority,
                "created_at": datetime.utcnow().isoformat()
            }
            
            # Use sorted set for priority queue
            queue_key = f"queue:{queue_name}"
            await self.redis.zadd(queue_key, {json.dumps(task_payload): priority})
            
            logger.debug("Task enqueued", task_id=task_id, queue=queue_name)
            return task_id
            
        except Exception as e:
            logger.error("Failed to enqueue task", queue=queue_name, error=str(e))
            raise
    
    async def dequeue_task(self, queue_name: str) -> Optional[Dict[str, Any]]:
        """Dequeue highest priority task"""
        self._ensure_initialized()
        
        try:
            queue_key = f"queue:{queue_name}"
            
            # Get highest priority task (ZPOPMAX gets highest score)
            result = await self.redis.zpopmax(queue_key)
            
            if result:
                task_json, priority = result[0]
                task_data = json.loads(task_json)
                logger.debug("Task dequeued", task_id=task_data["id"], queue=queue_name)
                return task_data
            
            return None
            
        except Exception as e:
            logger.error("Failed to dequeue task", queue=queue_name, error=str(e))
            return None
    
    # Health check
    async def health_check(self) -> Dict[str, Any]:
        """Perform health check on cache system"""
        try:
            # Test basic operations
            test_key = "health_check"
            test_value = "ok"
            
            await self.redis.set(test_key, test_value, ex=60)
            retrieved = await self.redis.get(test_key)
            await self.redis.delete(test_key)
            
            # Get Redis info
            info = await self.redis.info()
            
            return {
                "status": "healthy" if retrieved == test_value else "degraded",
                "redis_version": info.get("redis_version"),
                "connected_clients": info.get("connected_clients"),
                "used_memory_human": info.get("used_memory_human"),
                "ops_per_sec": info.get("instantaneous_ops_per_sec")
            }
            
        except Exception as e:
            logger.error("Cache health check failed", error=str(e))
            return {
                "status": "unhealthy",
                "error": str(e)
            }