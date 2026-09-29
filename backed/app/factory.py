"""应用工厂：lifespan + 中间件 + 异常 + 路由。"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.trustedhost import TrustedHostMiddleware

from config import settings
from utils.logger import setup_logging, get_logger
from .config import AppConfig
from .middleware import setup_middleware
from .exceptions import setup_exception_handlers
from .routes import setup_routes
from api import register_routers
from api.hub import register_hub
from core.database import create_database_pool, close_database_pool, init_models
from core.cache import init_cache, close_cache
from core.queue import start_queue, stop_queue

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """日志 → DB → 缓存 → 队列。HTTPS/TLS 由反向代理负责，此处不强制跳转。"""
    logger.info("正在启动应用...")
    try:
        setup_logging(level=getattr(settings, "log_level", "INFO"))
        await create_database_pool()
        await init_models()
        await init_cache()
        await start_queue()
        logger.info("应用启动成功 - 环境: %s", settings.environment)
        yield
    except Exception as e:
        logger.error("应用启动失败: %s", e)
        raise
    finally:
        logger.info("正在关闭应用资源...")
        try:
            await stop_queue()
            await close_cache()
            await close_database_pool()
            logger.info("应用已安全关闭")
        except Exception as e:
            logger.error("关闭资源时出错: %s", e)


def create_app() -> FastAPI:
    app = FastAPI(**AppConfig.get_app_config(), lifespan=lifespan)

    # 非 debug 时限制 Host（Docker/本地可在 .env 配置 ALLOWED_HOSTS）
    if not settings.debug:
        app.add_middleware(
            TrustedHostMiddleware,
            allowed_hosts=getattr(settings, "allowed_hosts", ["*"]),
        )

    setup_middleware(app)
    setup_exception_handlers(app)
    setup_routes(app)
    register_routers(app)
    # 深度合并：把平台发布 REST API（server/api.py）挂进主后端，
    # 由本应用统一对外服务（主后端自带 /health，故此处不重复注册）。
    register_hub(app, include_health=False)
    return app
