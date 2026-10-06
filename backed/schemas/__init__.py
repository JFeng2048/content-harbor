"""
Schemas 包：统一响应 + 按表生成的 Pydantic 模型
"""

from .response import (
    BaseResponse,
    SuccessResponse,
    ErrorResponse,
    PaginationResponse,
    PaginationMeta,
    success_response,
    error_response,
    paginated_response,
)

__all__ = [
    "BaseResponse",
    "SuccessResponse",
    "ErrorResponse",
    "PaginationResponse",
    "PaginationMeta",
    "success_response",
    "error_response",
    "paginated_response",
]
