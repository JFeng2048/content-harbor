"""通用响应模型

设计要点：
- 不使用自定义 __init__ 覆盖字段，避免 FastAPI 用 response_model 对返回实例
  做二次校验时出现 "got multiple values for keyword argument 'success'" 这类冲突。
- success / code / message / data / timestamp 均通过字段默认值声明。
- 构造响应统一走 success_response / error_response / paginated_response 等函数。
"""

import math
from typing import Any, Optional, Generic, TypeVar, List
from pydantic import BaseModel, Field
from datetime import datetime

from utils.response_code import ResponseCode

T = TypeVar('T')


class BaseResponse(BaseModel, Generic[T]):
    """基础响应模型"""

    success: bool = Field(default=False, description="操作是否成功")
    code: int = Field(default=200, description="响应码")
    message: str = Field(default="", description="响应消息")
    data: Optional[T] = Field(default=None, description="响应数据")
    timestamp: str = Field(
        default_factory=lambda: datetime.now().isoformat(),
        description="响应时间戳",
    )


class SuccessResponse(BaseResponse[T]):
    """成功响应模型"""

    success: bool = True
    code: int = 200


class ErrorResponse(BaseResponse[None]):
    """错误响应模型"""

    success: bool = False
    code: int = 500


class PaginationMeta(BaseModel):
    """分页元数据"""

    page: int = Field(..., description="当前页码", ge=1)
    page_size: int = Field(..., description="每页数量", ge=1, le=100)
    total: int = Field(..., description="总记录数", ge=0)
    total_pages: int = Field(..., description="总页数", ge=0)
    has_next: bool = Field(..., description="是否有下一页")
    has_prev: bool = Field(..., description="是否有上一页")


class PaginationResponse(BaseResponse[List[T]]):
    """分页响应模型"""

    meta: PaginationMeta = Field(..., description="分页信息")


class ValidationErrorDetail(BaseModel):
    """验证错误详情"""

    field: str = Field(..., description="字段名")
    message: str = Field(..., description="错误消息")
    value: Any = Field(default=None, description="错误值")


class ValidationErrorResponse(BaseResponse[List[ValidationErrorDetail]]):
    """验证错误响应模型"""

    pass


# ================ 便捷响应构造函数 ================

def success_response(data: Any = None, message: str = "操作成功", code: int = 200) -> SuccessResponse:
    """创建成功响应"""
    return SuccessResponse(data=data, message=message, code=code)


def error_response(response_code: ResponseCode, detail: str = None) -> ErrorResponse:
    """创建错误响应"""
    return ErrorResponse(
        code=response_code.code,
        message=detail or response_code.message,
        success=False,
        data=None,
    )


def paginated_response(
    items: List[Any],
    page: int,
    page_size: int,
    total: int,
    message: str = "查询成功",
) -> PaginationResponse:
    """创建分页响应"""
    total_pages = math.ceil(total / page_size) if total > 0 else 0
    meta = PaginationMeta(
        page=page,
        page_size=page_size,
        total=total,
        total_pages=total_pages,
        has_next=page < total_pages,
        has_prev=page > 1,
    )
    return PaginationResponse(data=items, meta=meta, message=message)


def validation_error_response(errors: List[ValidationErrorDetail]) -> ValidationErrorResponse:
    """创建验证错误响应"""
    return ValidationErrorResponse(data=errors, code=422, message="数据验证失败", success=False)


# ================ 常用业务响应 ================

def user_not_found_response(detail: str = None) -> ErrorResponse:
    """用户不存在响应"""
    return error_response(ResponseCode.USER_NOT_FOUND, detail)


def permission_denied_response(detail: str = None) -> ErrorResponse:
    """权限不足响应"""
    return error_response(ResponseCode.PERMISSION_DENIED, detail)


def token_expired_response(detail: str = None) -> ErrorResponse:
    """令牌过期响应"""
    return error_response(ResponseCode.TOKEN_EXPIRED, detail)


def data_not_found_response(detail: str = None) -> ErrorResponse:
    """数据不存在响应"""
    return error_response(ResponseCode.DATA_NOT_FOUND, detail)


def unauthorized_response(detail: str = None) -> ErrorResponse:
    """未授权访问响应"""
    return error_response(ResponseCode.UNAUTHORIZED, detail)


# ================ 响应装饰器 ================

from functools import wraps
from typing import Callable


def response_wrapper(success_message: str = "操作成功"):
    """响应包装装饰器"""
    def decorator(func: Callable):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            try:
                result = await func(*args, **kwargs)
                if isinstance(result, BaseResponse):
                    return result
                return success_response(data=result, message=success_message)
            except Exception as e:
                return error_response(ResponseCode.INTERNAL_SERVER_ERROR, str(e))

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            try:
                result = func(*args, **kwargs)
                if isinstance(result, BaseResponse):
                    return result
                return success_response(data=result, message=success_message)
            except Exception as e:
                return error_response(ResponseCode.INTERNAL_SERVER_ERROR, str(e))

        import inspect
        if inspect.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator
