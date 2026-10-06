"""测试公共夹具：SQLite 测试库 + FastAPI TestClient 用 app。"""

import os

os.environ.setdefault("FASTAPI_ENV", "testing")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./data/test_hub.db")
os.environ.setdefault("CACHE_ENABLED", "false")
os.environ.setdefault("REDIS_HOST", "")

import models  # 触发 ORM 元数据注册（create_all 需要）
from app.factory import create_app
from core import database

import pytest


@pytest.fixture(scope="session")
async def _db():
    """初始化连接池并建表（不存在则创建）。"""
    await database.create_database_pool()
    await database.init_models()
    yield
    if database.async_engine is not None:
        await database.async_engine.dispose()


@pytest.fixture(scope="session")
async def app(_db):
    return create_app()


@pytest.fixture
async def session(_db):
    async with database.AsyncSessionLocal() as s:
        yield s
