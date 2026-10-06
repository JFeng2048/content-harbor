"""路由配置

此文件由 SQL-to-FastAPI-Scaffold 自动生成

导入并注册各个路由
"""

from fastapi import FastAPI

from config import settings


def register_routes(app: FastAPI) -> None:
    """
    注册所有路由

    Args:
        app: FastAPI应用实例
    """
    from api import api_router
    app.include_router(api_router, prefix="/api")

    @app.get("/health", include_in_schema=False)
    async def health_check():
        return {
            "status": "ok",
            "version": settings.APP_VERSION,
            "service": settings.APP_NAME
        }
