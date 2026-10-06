"""数据库连接与会话管理（纯异步）

设计要点：
- 全链路异步：AsyncSession + async_sessionmaker
- 不在模块导入时建引擎，避免无 DB 时 import 即崩溃
- 引擎在 lifespan 的 create_database_pool() 中创建
- get_async_session() 作为 FastAPI 依赖注入点
- 保留 Base / metadata 供 models 使用（models/base.py 依赖）
"""

import logging
import os
from typing import Any, AsyncGenerator, Dict, Optional

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import declarative_base

from config import settings

logger = logging.getLogger(__name__)

# ORM 基类（models 包依赖）
Base = declarative_base()
metadata = Base.metadata

# 全局异步引擎与会话工厂（lifespan 中初始化）
async_engine: Optional[AsyncEngine] = None
AsyncSessionLocal: Optional[async_sessionmaker[AsyncSession]] = None

# 连接池监控数据
pool_stats: Dict[str, int] = {
    "total_connections": 0,
    "active_connections": 0,
    "idle_connections": 0,
    "overflow_connections": 0,
    "connection_errors": 0,
    "slow_queries": 0,
}


def _to_async_url(database_url: str) -> str:
    """同步 URL -> 异步 URL"""
    if database_url.startswith("mysql+pymysql"):
        return database_url.replace("mysql+pymysql", "mysql+aiomysql", 1)
    if database_url.startswith("mysql://"):
        return database_url.replace("mysql://", "mysql+aiomysql://", 1)
    # sqlite / postgres 等已具备异步 scheme 的原样返回
    return database_url


def _build_engine_kwargs(database_url: str) -> Dict[str, Any]:
    """构建异步引擎参数（MySQL 专用参数仅在 MySQL 下生效，SQLite 用最小集）"""
    kw: Dict[str, Any] = {
        "echo": getattr(settings, "db_echo", False),
        "echo_pool": getattr(settings, "db_echo_pool", False),
        # aiomysql 的 ping() 需要 reconnect 参数，与 SQLAlchemy 的 pool_pre_ping 不兼容，
        # 异步引擎必须关闭 pre_ping（用 pool_recycle 替代保活）
        "pool_pre_ping": False,
    }

    if database_url.startswith("mysql"):
        # 异步引擎默认使用 AsyncAdaptedQueuePool，仅传递池参数（不要传 sync poolclass）
        kw.update(
            {
                "isolation_level": getattr(settings, "db_isolation_level", "READ_COMMITTED"),
                "pool_size": getattr(settings, "db_pool_size", 10),
                "max_overflow": getattr(settings, "db_max_overflow", 20),
                "pool_timeout": getattr(settings, "db_pool_timeout", 30),
                "pool_recycle": getattr(settings, "db_pool_recycle", 3600),
                "pool_reset_on_return": getattr(settings, "db_pool_reset_on_return", "commit"),
            }
        )
        # MySQL 连接参数
        kw["connect_args"] = {
            "connect_timeout": getattr(settings, "db_connect_timeout", 60),
            "charset": getattr(settings, "db_charset", "utf8mb4"),
        }
    return kw


async def create_database_pool() -> None:
    """创建异步数据库连接池（在 lifespan 中调用）"""
    global async_engine, AsyncSessionLocal

    database_url = getattr(settings, "database_url", None)
    if not database_url:
        raise ValueError("数据库 URL 未配置 (settings.database_url)")

    async_url = _to_async_url(database_url)
    kwargs = _build_engine_kwargs(database_url)

    # SQLite 文件库：确保目录存在
    if async_url.startswith("sqlite") and ":memory:" not in async_url:
        db_file = async_url.replace("sqlite+aiosqlite:///", "", 1).replace("sqlite:///", "", 1)
        parent = os.path.dirname(db_file)
        if parent:
            os.makedirs(parent, exist_ok=True)

    async_engine = create_async_engine(async_url, **kwargs)
    AsyncSessionLocal = async_sessionmaker(
        async_engine, class_=AsyncSession, expire_on_commit=False
    )

    # 连接测试
    async with async_engine.connect() as conn:
        await conn.execute(text("SELECT 1"))

    # 连接池事件监听（同步 DBAPI 层）
    @event.listens_for(async_engine.sync_engine, "connect")
    def _on_connect(dbapi_connection, connection_record):  # noqa: D401
        pool_stats["total_connections"] += 1

    logger.info("异步数据库连接池创建成功: %s", async_url.split("@")[-1] if "@" in async_url else async_url)


async def init_models() -> None:
    """创建所有已注册模型对应的数据表（不存在才创建，等价轻量 migrate）。"""
    if async_engine is None:
        await create_database_pool()
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("数据表已就绪（如不存在则已创建）")


async def close_database_pool() -> None:
    """关闭异步数据库连接池"""
    global async_engine
    if async_engine is not None:
        await async_engine.dispose()
        async_engine = None
        logger.info("异步数据库连接池已关闭")


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI 依赖：获取异步数据库会话

    用法::

        @router.get("/x")
        async def foo(db: AsyncSession = Depends(get_async_session)):
            ...
    """
    if AsyncSessionLocal is None:
        raise RuntimeError("数据库未初始化，请检查应用启动生命周期")
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def check_database_health() -> Dict[str, Any]:
    """数据库健康检查"""
    if async_engine is None or AsyncSessionLocal is None:
        return {"status": "unhealthy", "error": "数据库未初始化"}
    try:
        import time

        start = time.time()
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
            await session.commit()
        return {
            "status": "healthy",
            "response_time": f"{time.time() - start:.3f}s",
            "pool_stats": pool_stats,
        }
    except Exception as e:
        return {"status": "unhealthy", "error": str(e), "pool_stats": pool_stats}


def get_pool_status() -> Dict[str, Any]:
    """获取连接池状态"""
    if async_engine is None:
        return {"status": "not_initialized"}
    pool = async_engine.pool
    try:
        return {
            "size": pool.size(),
            "checkedin": pool.checkedin(),
            "checkedout": pool.checkedout(),
            "overflow": pool.overflow(),
            "stats": pool_stats,
        }
    except Exception:
        return {"stats": pool_stats}
