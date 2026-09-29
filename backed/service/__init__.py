"""Service 包（业务逻辑层）与服务工厂

分层约定：
- api/Resource ：只依赖 Service（通过下方 get_*_service 注入）
- service/    ：单条委托 Repository；列表 / 状态等业务写在本层
- repository/ ：仅单条 create / delete / update / get

新增表时，在下方追加对应的 get_*_service 即可。
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
