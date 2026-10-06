"""基础数据模型

设计约定：
- BaseModel 只提供通用工具方法（to_dict / update_from_dict），不含表字段。
- isDelete / addTime 等公共列下沉到各具体模型，便于按表维护与对齐真实 DDL。
"""

from sqlalchemy import Column, DateTime, Boolean
from sqlalchemy.sql import func
from core.database import Base


class BaseModel(Base):
    """ORM 基类（无公共业务字段）"""

    __abstract__ = True

    def to_dict(self, exclude_fields=None):
        """转换为字典格式（键使用 Python 属性名，与 ORM 映射一致）

        注意：column.key 是映射后的 Python 属性名（如 student_id），
        column.name 才是数据库列名（如 studentID）。使用 key 才能保证
        getattr 取到正确属性，且与响应层字段命名一致。
        """
        exclude_fields = exclude_fields or []
        result = {}

        for column in self.__table__.columns:
            key = column.key
            if key not in exclude_fields:
                value = getattr(self, key)
                if hasattr(value, "isoformat"):  # 处理日期时间
                    value = value.isoformat()
                result[key] = value

        return result

    def update_from_dict(self, data: dict, allowed_fields=None):
        """从字典更新对象属性"""
        allowed_fields = allowed_fields or []

        for key, value in data.items():
            if key in allowed_fields and hasattr(self, key):
                setattr(self, key, value)


class TimestampMixin:
    """时间戳混入类（按需混入，非默认）"""

    created_at = Column(DateTime, default=func.now(), comment="创建时间")
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), comment="更新时间")


class SoftDeleteMixin:
    """软删除混入类（按需混入，非默认）"""

    is_deleted = Column(Boolean, default=False, comment="是否已删除")
    deleted_at = Column(DateTime, nullable=True, comment="删除时间")
