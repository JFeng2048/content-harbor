"""应用生命周期管理

此文件由 SQL-to-FastAPI-Scaffold 自动生成

定义应用启动和关闭时的生命周期处理
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from loguru import logger
import os

from config import settings
from core.database import engine


@asynccontextmanager
async def lifespan_manager(app: FastAPI):
    """
    应用生命周期管理器

    在应用启动时创建数据库表，在关闭时执行清理操作
    """
    os.makedirs("logs", exist_ok=True)

    logger.info("🚀 应用正在启动...")

    from models import BaseMode
    BaseMode.metadata.create_all(bind=engine)
    logger.info("✅ 数据库表初始化完成")

    logger.info(f"🎉 应用启动成功 - {settings.APP_NAME} v{settings.APP_VERSION}")

    yield

    logger.info("🔄 应用正在关闭...")
    logger.info("👋 应用已安全关闭")
