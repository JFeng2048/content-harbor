"""API v1 路由包

脚手架生成表模块后，在此追加：
    from api.v1.xxx import router as xxx_router
    v1_router.include_router(xxx_router)
"""

from fastapi import APIRouter

from api.v1.article import router as article_router
from api.v1.publication import router as publication_router
from api.v1.account import router as account_router
from api.v1.job import router as job_router
from api.v1.task import router as task_router

v1_router = APIRouter()
v1_router.include_router(article_router)
v1_router.include_router(publication_router)
v1_router.include_router(account_router)
v1_router.include_router(job_router)
v1_router.include_router(task_router)

__all__ = ["v1_router"]
