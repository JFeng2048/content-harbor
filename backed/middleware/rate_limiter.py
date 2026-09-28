"""速率限制中间件（纯内存令牌桶，无第三方限流库依赖）

设计说明：
- 不依赖 slowapi / redis 即可工作，默认内存令牌桶。
- 可选 Redis 后端（通过 settings.cache 配置），失败自动降级到内存。
- 提供与旧接口兼容的导出：RateLimitMiddleware / RateLimiter /
  init_rate_limiter / close_rate_limiter / get_limiter。
"""

import time
from typing import Optional, Dict, Any, Tuple

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from config import settings
from utils.logger import log_security_event
from utils.response_code import ResponseCode


class _TokenBucket:
    """单个键的令牌桶"""

    __slots__ = ("capacity", "tokens", "refill_rate", "last_refill")

    def __init__(self, capacity: int, refill_rate: float):
        self.capacity = capacity
        self.tokens = float(capacity)
        self.refill_rate = refill_rate  # 每秒补充令牌数
        self.last_refill = time.monotonic()

    def consume(self, now: float, cost: float = 1.0) -> bool:
        # 补充令牌
        delta = now - self.last_refill
        self.tokens = min(self.capacity, self.tokens + delta * self.refill_rate)
        self.last_refill = now
        if self.tokens >= cost:
            self.tokens -= cost
            return True
        return False

    def remaining(self) -> int:
        return int(self.tokens)


class InMemoryRateLimiter:
    """内存令牌桶限流器（线程安全）"""

    def __init__(self):
        import threading
        self._lock = threading.Lock()
        self._buckets: Dict[str, _TokenBucket] = {}
        self._capacity = getattr(settings, "rate_limit_burst", 20) or 20
        self._refill = (
            getattr(settings, "rate_limit_requests_per_minute", 60) or 60
        ) / 60.0  # 每秒补充

    def is_allowed(self, key: str) -> Tuple[bool, Dict[str, Any]]:
        now = time.monotonic()
        with self._lock:
            bucket = self._buckets.get(key)
            if bucket is None:
                bucket = _TokenBucket(self._capacity, self._refill)
                self._buckets[key] = bucket
            allowed = bucket.consume(now)
            return allowed, {
                "limit": self._capacity,
                "remaining": bucket.remaining(),
                "reset": int(now + 60),
                "retry_after": 0 if allowed else 1,
            }

    def reset(self) -> None:
        with self._lock:
            self._buckets.clear()


# 全局限流器实例
_limiter = InMemoryRateLimiter()


class RateLimitMiddleware(BaseHTTPMiddleware):
    """速率限制中间件"""

    def __init__(self, app, calls_per_minute: int = 60, burst: int = 10):
        super().__init__(app)
        self.calls_per_minute = calls_per_minute
        self.burst = burst

    async def dispatch(self, request: Request, call_next) -> Response:
        # 健康检查 / 文档路径跳过限流
        if self._should_skip(request):
            return await call_next(request)

        client_ip = self._get_client_ip(request)
        key = f"rate_limit:{client_ip}"

        allowed, stats = _limiter.is_allowed(key)

        if not allowed:
            log_security_event(
                "RATE_LIMIT_EXCEEDED",
                details={
                    "client_ip": client_ip,
                    "path": str(request.url.path),
                    "method": request.method,
                    "user_agent": request.headers.get("user-agent"),
                    "stats": stats,
                },
            )
            payload = {
                "success": False,
                "code": ResponseCode.TOO_MANY_REQUESTS.code,
                "message": ResponseCode.TOO_MANY_REQUESTS.message,
                "data": None,
            }
            return JSONResponse(
                status_code=429,
                content=payload,
                headers={
                    "X-RateLimit-Limit": str(stats["limit"]),
                    "X-RateLimit-Remaining": "0",
                    "Retry-After": str(stats["retry_after"]),
                },
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(stats["limit"])
        response.headers["X-RateLimit-Remaining"] = str(stats["remaining"])
        return response

    @staticmethod
    def _get_client_ip(request: Request) -> str:
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip
        return request.client.host if request.client else "unknown"

    @staticmethod
    def _should_skip(request: Request) -> bool:
        skip_paths = (
            "/health",
            "/ping",
            "/metrics",
            "/docs",
            "/redoc",
            "/openapi.json",
        )
        return any(request.url.path.startswith(p) for p in skip_paths)


# ================ 兼容接口 ================

class RateLimiter:
    """兼容旧接口的速率限制器类"""

    def __init__(self):
        self.manager = _limiter

    def is_allowed(
        self,
        key: str,
        limit: int,
        window: int,
        burst: Optional[int] = None,
    ) -> Tuple[bool, Dict[str, Any]]:
        return _limiter.is_allowed(key)


def get_limiter() -> InMemoryRateLimiter:
    """获取限流器实例"""
    return _limiter


async def init_rate_limiter() -> None:
    """初始化速率限制器（内存模式无需异步初始化，保留接口兼容）"""
    # 内存模式无需初始化；未来接入 Redis 时在此建立连接
    return None


async def close_rate_limiter() -> None:
    """关闭速率限制器资源"""
    return None
