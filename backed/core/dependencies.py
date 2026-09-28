"""
依赖注入（FastAPI Depends）

此文件由 SQL-to-FastAPI-Scaffold 自动生成。

约定：
- Resource 统一注入 get_{table}_service
- Service 内部组合 Repository；一般无需在 Resource 中注入 Repository
"""

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_async_session


{% for item in tables %}
def get_{{item.service_name}}(
    db: AsyncSession = Depends(get_async_session),
):
    """获取{{item.comment}}业务服务实例"""
    from service.{{item.table_name}}_service import {{item.class_name}}Service

    return {{item.class_name}}Service(db)


def get_{{item.repository_name}}(
    db: AsyncSession = Depends(get_async_session),
):
    """获取{{item.comment}}仓储实例（一般由 Service 内部使用；特殊场景可注入）"""
    from repository.{{item.table_name}}_repository import {{item.class_name}}Repository

    return {{item.class_name}}Repository(db)


{% endfor %}
