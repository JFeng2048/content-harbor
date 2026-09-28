"""API 路由包：聚合各版本路由并挂载到应用。

factory 通过 `from api import register_routers` 调用本函数完成路由装配。
"""

from fastapi import FastAPI

from config import settings
from .v1 import v1_router

__all__ = ["v1_router", "register_routers"]


def register_routers(app: FastAPI) -> None:
    """将 v1 路由挂载到配置指定的 API 前缀（默认 /api/v1）。"""
    prefix = getattr(settings, "api_prefix", "/api/v1")
    app.include_router(v1_router, prefix=prefix)
