"""
平台账号数据访问层（Repository）

【AUTO-GENERATED】由 sql-to-fastapi-restfulapi-scaffold 生成，可被 skill 覆盖。
禁止在此文件编写业务规则。
Resource/API 层不要直接依赖本 Repository。

职责边界（强制）：
- 本层只做「单表、单条记录」的基础 CRUD，方法名固定为（按增删改查顺序）：
  create / delete / update / get
- 列表分页、过滤、状态变更、跨表流程等一律视为业务逻辑，写在 Service。
"""

from typing import Any, Dict, Union

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.account import Account
from schemas.account import AccountCreate, AccountUpdate
from utils.custom_exceptions import NotFoundException


class AccountRepository:
    """
    平台账号仓储：仅负责单表单条记录的 CRUD（方法顺序：增删改查）
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, data: AccountCreate) -> Account:
        """增：插入一条记录并提交"""
        obj = Account(**data.model_dump(exclude_none=True))
        self.db.add(obj)
        await self.db.commit()
        await self.db.refresh(obj)
        return obj

    async def delete(self, id: int) -> None:
        """删：有软删字段则软删，否则硬删"""
        obj = await self.get(id)
        
        await self.db.delete(obj)
        await self.db.commit()
        

    async def update(
        self,
        id: int,
        data: Union[AccountUpdate, Dict[str, Any]],
    ) -> Account:
        """改：按主键更新一条记录（仅更新传入字段）"""
        if hasattr(data, "model_dump"):
            fields = data.model_dump(exclude_unset=True)
        else:
            fields = data
        obj = await self.get(id)
        for key, value in fields.items():
            setattr(obj, key, value)
        await self.db.commit()
        await self.db.refresh(obj)
        return obj

    async def get(self, id: int) -> Account:
        """查：按主键获取一条（软删除视为不存在）"""
        
        obj = await self.db.scalar(
            select(Account).where(
                Account.id == id
            )
        )
        
        if not obj:
            raise NotFoundException("平台账号不存在")
        return obj
