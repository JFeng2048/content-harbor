"""Models 包

导出 ORM 基类；具体表模型由脚手架按 DDL 生成后在此追加 import。
"""

from .base import BaseModel, TimestampMixin, SoftDeleteMixin

# 与 core.database.Base 同源，便于 metadata.create_all / 测试建表
from core.database import Base

# 各表 ORM 模型（脚手架按 DDL 生成后在此追加 import）
from .article import Article
from .publication import Publication
from .account import Account
from .job import Job
from .task import Task

__all__ = [
    "Base",
    "BaseModel",
    "TimestampMixin",
    "SoftDeleteMixin",
    "Article",
    "Publication",
    "Account",
    "Job",
    "Task",
]
