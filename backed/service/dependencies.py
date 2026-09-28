"""服务依赖工厂（FastAPI 原生 Depends）

约定：
- Resource 统一注入 get_*_service
- Service 内部组合 Repository（不要在 Resource 注入 Repository）
- 本文件由脚手架在生成新表时追加 get_*_service
"""

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_async_session
from service.article_service import ArticleService
from service.publication_service import PublicationService
from service.account_service import AccountService
from service.job_service import JobService
from service.task_service import TaskService


def get_article_service(db: AsyncSession = Depends(get_async_session)) -> ArticleService:
    return ArticleService(db)


def get_publication_service(db: AsyncSession = Depends(get_async_session)) -> PublicationService:
    return PublicationService(db)


def get_account_service(db: AsyncSession = Depends(get_async_session)) -> AccountService:
    return AccountService(db)


def get_job_service(db: AsyncSession = Depends(get_async_session)) -> JobService:
    return JobService(db)


def get_task_service(db: AsyncSession = Depends(get_async_session)) -> TaskService:
    return TaskService(db)
