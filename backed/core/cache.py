"""缓存系统（内存 / Redis）

约定：
- lifespan 中 ``init_cache`` / ``close_cache``
- Redis 初始化必须 ``ping`` 成功，否则回退内存
- 禁止 ``flushdb``；清空/失效仅删除带前缀的键（SCAN + UNLINK）
- MemoryCache 使用 ``asyncio.Lock``（适合单进程开发；多 worker 请用 Redis）
"""

from __future__ import annotations

import asyncio
import fnmatch
import json
import logging
import time
from functools import wraps
from typing import Any, Callable, Dict, Optional

try:
    import redis.asyncio as redis

    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

logger = logging.getLogger(__name__)


class CacheBackend:
    """缓存后端接口"""

    async def get(self, key: str) -> Optional[Any]:
        raise NotImplementedError

    async def set(self, key: str, value: Any, timeout: Optional[int] = None) -> None:
        raise NotImplementedError

    async def delete(self, key: str) -> bool:
        raise NotImplementedError

    async def delete_by_pattern(self, pattern: str) -> int:
        raise NotImplementedError

    async def clear(self) -> None:
        raise NotImplementedError

    async def exists(self, key: str) -> bool:
        raise NotImplementedError


class MemoryCache(CacheBackend):
    """进程内内存缓存（单进程开发用）"""

    def __init__(self, max_size: int = 10000, default_expire: int = 3600):
        self._cache: Dict[str, tuple] = {}  # key -> (value, expire_at, created_at)
        self._lock = asyncio.Lock()
        self.max_size = max_size
        self.default_expire = default_expire
        self._stats = {"hits": 0, "misses": 0, "sets": 0, "deletes": 0}

    async def get(self, key: str) -> Optional[Any]:
        async with self._lock:
            item = self._cache.get(key)
            if item is None:
                self._stats["misses"] += 1
                return None
            value, expire_time, _created = item
            if expire_time and time.time() > expire_time:
                del self._cache[key]
                self._stats["misses"] += 1
                return None
            self._stats["hits"] += 1
            return value

    async def set(self, key: str, value: Any, timeout: Optional[int] = None) -> None:
        async with self._lock:
            if len(self._cache) >= self.max_size:
                items_to_remove = max(1, len(self._cache) // 10)
                sorted_items = sorted(self._cache.items(), key=lambda x: x[1][2])
                for k, _ in sorted_items[:items_to_remove]:
                    del self._cache[k]

            expire_time = time.time() + timeout if timeout else None
            self._cache[key] = (value, expire_time, time.time())
            self._stats["sets"] += 1

    async def delete(self, key: str) -> bool:
        async with self._lock:
            if key in self._cache:
                del self._cache[key]
                self._stats["deletes"] += 1
                return True
            return False

    async def delete_by_pattern(self, pattern: str) -> int:
        async with self._lock:
            keys = [k for k in self._cache if fnmatch.fnmatch(k, pattern)]
            for k in keys:
                del self._cache[k]
                self._stats["deletes"] += 1
            return len(keys)

    async def clear(self) -> None:
        async with self._lock:
            self._cache.clear()

    async def exists(self, key: str) -> bool:
        return (await self.get(key)) is not None

    async def get_stats(self) -> Dict[str, Any]:
        async with self._lock:
            total = self._stats["hits"] + self._stats["misses"]
            hit_rate = (self._stats["hits"] / total * 100) if total else 0.0
            return {
                **self._stats,
                "type": "memory",
                "total_requests": total,
                "total_items": len(self._cache),
                "hit_rate": f"{hit_rate:.2f}%",
                "max_size": self.max_size,
            }


class RedisCache(CacheBackend):
    """Redis 缓存（键统一加前缀，清空不使用 flushdb）"""

    def __init__(
        self,
        client: Any,
        key_prefix: str = "fastapi",
    ):
        if not REDIS_AVAILABLE:
            raise ImportError("redis package is required for Redis cache")
        self.redis_client = client
        self.key_prefix = key_prefix.rstrip(":")

    def _full_key(self, key: str) -> str:
        if key.startswith(f"{self.key_prefix}:"):
            return key
        return f"{self.key_prefix}:{key}"

    @classmethod
    async def create(
        cls,
        host: str = "localhost",
        port: int = 6379,
        db: int = 0,
        password: Optional[str] = None,
        key_prefix: str = "fastapi",
    ) -> "RedisCache":
        client = redis.Redis(
            host=host,
            port=port,
            db=db,
            password=password or None,
            decode_responses=True,
        )
        await client.ping()
        return cls(client, key_prefix=key_prefix)

    async def get(self, key: str) -> Optional[Any]:
        try:
            value = await self.redis_client.get(self._full_key(key))
            if value is None:
                return None
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                return value
        except Exception as e:
            logger.error("Redis get error: %s", e)
            return None

    async def set(self, key: str, value: Any, timeout: Optional[int] = None) -> None:
        try:
            serialized = json.dumps(value, default=str)
            full_key = self._full_key(key)
            if timeout:
                await self.redis_client.setex(full_key, timeout, serialized)
            else:
                await self.redis_client.set(full_key, serialized)
        except Exception as e:
            logger.error("Redis set error: %s", e)

    async def delete(self, key: str) -> bool:
        try:
            return (await self.redis_client.delete(self._full_key(key))) > 0
        except Exception as e:
            logger.error("Redis delete error: %s", e)
            return False

    async def delete_by_pattern(self, pattern: str) -> int:
        """按 glob 模式删除（自动补前缀）。例：user:* → {prefix}:user:*"""
        match = pattern if pattern.startswith(f"{self.key_prefix}:") else self._full_key(pattern)
        deleted = 0
        try:
            async for key in self.redis_client.scan_iter(match=match, count=100):
                await self.redis_client.unlink(key)
                deleted += 1
        except Exception as e:
            logger.error("Redis delete_by_pattern error: %s", e)
        return deleted

    async def clear(self) -> None:
        """仅清除本应用前缀下的键，绝不 flushdb。"""
        removed = await self.delete_by_pattern("*")
        logger.info("Redis cache cleared prefix=%s removed=%s", self.key_prefix, removed)

    async def exists(self, key: str) -> bool:
        try:
            return bool(await self.redis_client.exists(self._full_key(key)))
        except Exception as e:
            logger.error("Redis exists error: %s", e)
            return False

    async def close(self) -> None:
        close_fn = getattr(self.redis_client, "aclose", None) or self.redis_client.close
        result = close_fn()
        if asyncio.iscoroutine(result):
            await result


class CacheManager:
    """缓存管理器"""

    def __init__(self):
        self._backend: Optional[CacheBackend] = None
        self._prefix: str = "fastapi"

    @property
    def backend_type(self) -> str:
        if isinstance(self._backend, RedisCache):
            return "redis"
        if isinstance(self._backend, MemoryCache):
            return "memory"
        return "uninitialized"

    async def init_cache(self) -> None:
        from config import settings

        self._prefix = getattr(settings, "cache_prefix", "fastapi_security") or "fastapi"
        max_size = getattr(settings, "cache_max_size", 10000)
        use_redis = False

        try:
            if (
                REDIS_AVAILABLE
                and getattr(settings, "cache_enabled", True)
                and getattr(settings, "redis_host", None)
            ):
                use_redis = True
        except Exception as e:
            logger.warning("检查 Redis 配置失败: %s", e)

        if use_redis:
            try:
                self._backend = await RedisCache.create(
                    host=getattr(settings, "redis_host", "localhost"),
                    port=getattr(settings, "redis_port", 6379),
                    db=getattr(settings, "redis_db", 0),
                    password=getattr(settings, "redis_password", None) or None,
                    key_prefix=self._prefix,
                )
                logger.info("Redis 缓存已就绪 (prefix=%s)", self._prefix)
                return
            except Exception as e:
                logger.error("Redis 缓存初始化失败，回退内存: %s", e)

        self._backend = MemoryCache(max_size=max_size)
        logger.info("内存缓存已就绪 (max_size=%s)", max_size)

    async def close_cache(self) -> None:
        if isinstance(self._backend, RedisCache):
            try:
                await self._backend.close()
                logger.info("Redis 缓存已关闭")
            except Exception as e:
                logger.error("关闭 Redis 缓存失败: %s", e)
        self._backend = None
        logger.info("缓存系统已关闭")

    def _ensure(self) -> CacheBackend:
        if not self._backend:
            raise RuntimeError("Cache not initialized；请确认 lifespan 已调用 init_cache")
        return self._backend

    async def get(self, key: str) -> Optional[Any]:
        return await self._ensure().get(key)

    async def set(self, key: str, value: Any, timeout: Optional[int] = None) -> None:
        from config import settings

        default_timeout = getattr(settings, "cache_ttl", 300)
        await self._ensure().set(key, value, timeout or default_timeout)

    async def delete(self, key: str) -> bool:
        return await self._ensure().delete(key)

    async def delete_by_pattern(self, pattern: str) -> int:
        return await self._ensure().delete_by_pattern(pattern)

    async def clear(self) -> None:
        await self._ensure().clear()

    async def exists(self, key: str) -> bool:
        return await self._ensure().exists(key)

    async def get_stats(self) -> Dict[str, Any]:
        backend = self._ensure()
        if isinstance(backend, MemoryCache):
            return await backend.get_stats()
        return {"type": "redis", "status": "connected", "prefix": self._prefix}


cache_manager = CacheManager()


def cache_result(timeout: Optional[int] = None, key_prefix: str = ""):
    """结果缓存装饰器（仅用于 async 函数）。"""

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            cache_key = (
                f"{key_prefix or func.__name__}:"
                f"{hash(str(args) + str(sorted(kwargs.items())))}"
            )
            cached = await cache_manager.get(cache_key)
            if cached is not None:
                logger.debug("Cache hit: %s", cache_key)
                return cached
            result = await func(*args, **kwargs)
            await cache_manager.set(cache_key, result, timeout)
            logger.debug("Cache miss: %s", cache_key)
            return result

        return wrapper

    return decorator


def cache_invalidate(pattern: str):
    """写操作后按模式失效缓存。pattern 支持 glob，如 ``user:*``。"""

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            result = await func(*args, **kwargs)
            removed = await cache_manager.delete_by_pattern(pattern)
            logger.debug("Cache invalidate pattern=%s removed=%s", pattern, removed)
            return result

        return wrapper

    return decorator


async def init_cache() -> None:
    await cache_manager.init_cache()


async def close_cache() -> None:
    await cache_manager.close_cache()
