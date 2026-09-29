"""核心基础设施包

- database / cache / queue：运行时基础设施（lifespan 初始化）
- security：密码 / JWT 薄封装（实现在 utils）
- permissions：认证依赖（见 core.permissions）
- 服务工厂：定义在 ``service`` 包（见 service/__init__.py）

推荐显式导入，例如::

    from core.database import get_async_session
    from core.permissions import get_current_active_user
"""

from .database import (
    Base,
    metadata,
    async_engine,
    AsyncSessionLocal,
    pool_stats,
    create_database_pool,
    close_database_pool,
    get_async_session,
    check_database_health,
    get_pool_status,
)
from .cache import (
    MemoryCache,
    cache_manager,
    init_cache,
    close_cache,
)
from .queue import (
    MemoryQueue,
    task_queue,
    start_queue,
    stop_queue,
)
from .security import (
    SecurityHelper,
    get_password_hash,
    verify_password,
    create_access_token,
)
from .permissions import get_current_active_user

__all__ = [
    "Base",
    "metadata",
    "async_engine",
    "AsyncSessionLocal",
    "pool_stats",
    "create_database_pool",
    "close_database_pool",
    "get_async_session",
    "check_database_health",
    "get_pool_status",
    "MemoryCache",
    "cache_manager",
    "init_cache",
    "close_cache",
    "MemoryQueue",
    "task_queue",
    "start_queue",
    "stop_queue",
    "SecurityHelper",
    "get_password_hash",
    "verify_password",
    "create_access_token",
    "get_current_active_user",
]
