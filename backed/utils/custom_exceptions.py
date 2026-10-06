"""自定义异常模块"""

from typing import Optional, Any
from utils.response_code import ResponseCode


class BaseAPIException(Exception):
    """API基础异常类"""
    
    def __init__(
        self,
        response_code: ResponseCode,
        detail: Optional[str] = None,
        data: Optional[Any] = None
    ):
        self.response_code = response_code
        self.detail = detail or response_code.message
        self.data = data
        super().__init__(self.detail)


class AuthenticationException(BaseAPIException):
    """认证异常"""
    
    def __init__(self, detail: Optional[str] = None, data: Optional[Any] = None):
        super().__init__(ResponseCode.UNAUTHORIZED, detail, data)


class AuthorizationException(BaseAPIException):
    """授权异常"""
    
    def __init__(self, detail: Optional[str] = None, data: Optional[Any] = None):
        super().__init__(ResponseCode.PERMISSION_DENIED, detail, data)


class ValidationException(BaseAPIException):
    """验证异常"""
    
    def __init__(self, detail: Optional[str] = None, data: Optional[Any] = None):
        super().__init__(ResponseCode.VALIDATION_ERROR, detail, data)


class NotFoundException(BaseAPIException):
    """资源不存在异常"""
    
    def __init__(self, detail: Optional[str] = None, data: Optional[Any] = None):
        super().__init__(ResponseCode.NOT_FOUND, detail, data)


class ConflictException(BaseAPIException):
    """资源冲突异常"""
    
    def __init__(self, detail: Optional[str] = None, data: Optional[Any] = None):
        super().__init__(ResponseCode.CONFLICT, detail, data)


class RateLimitException(BaseAPIException):
    """速率限制异常"""
    
    def __init__(self, detail: Optional[str] = None, data: Optional[Any] = None):
        super().__init__(ResponseCode.TOO_MANY_REQUESTS, detail, data)


class BusinessException(BaseAPIException):
    """业务异常"""
    
    def __init__(
        self,
        response_code: ResponseCode,
        detail: Optional[str] = None,
        data: Optional[Any] = None
    ):
        super().__init__(response_code, detail, data)


class DatabaseException(BaseAPIException):
    """数据库异常"""
    
    def __init__(self, detail: Optional[str] = None, data: Optional[Any] = None):
        super().__init__(ResponseCode.DATABASE_ERROR, detail, data)


class ResourceNotOwnedException(BaseAPIException):
    """资源不属于当前用户异常 - 防止对象级别授权失效"""
    
    def __init__(self, detail: Optional[str] = None, data: Optional[Any] = None):
        super().__init__(ResponseCode.RESOURCE_NOT_OWNED, detail, data)


# ================ 扩展业务异常类型 ================

class UserException(BaseAPIException):
    """用户相关异常基类"""
    pass


class UserNotFoundException(UserException):
    """用户不存在异常"""
    
    def __init__(self, detail: Optional[str] = None, data: Optional[Any] = None):
        super().__init__(ResponseCode.USER_NOT_FOUND, detail, data)


class InvalidPasswordException(UserException):
    """密码错误异常"""
    
    def __init__(self, detail: Optional[str] = None, data: Optional[Any] = None):
        super().__init__(ResponseCode.INVALID_PASSWORD, detail, data)


class UserDisabledException(UserException):
    """用户已禁用异常"""
    
    def __init__(self, detail: Optional[str] = None, data: Optional[Any] = None):
        super().__init__(ResponseCode.USER_DISABLED, detail, data)


class TokenException(BaseAPIException):
    """令牌相关异常基类"""
    pass


class TokenExpiredException(TokenException):
    """令牌过期异常"""
    
    def __init__(self, detail: Optional[str] = None, data: Optional[Any] = None):
        super().__init__(ResponseCode.TOKEN_EXPIRED, detail, data)


class InvalidTokenException(TokenException):
    """无效令牌异常"""
    
    def __init__(self, detail: Optional[str] = None, data: Optional[Any] = None):
        super().__init__(ResponseCode.INVALID_TOKEN, detail, data)


class DataException(BaseAPIException):
    """数据相关异常基类"""
    pass


class DataNotFoundException(DataException):
    """数据不存在异常"""
    
    def __init__(self, detail: Optional[str] = None, data: Optional[Any] = None):
        super().__init__(ResponseCode.DATA_NOT_FOUND, detail, data)


class DataAlreadyExistsException(DataException):
    """数据已存在异常"""
    
    def __init__(self, detail: Optional[str] = None, data: Optional[Any] = None):
        super().__init__(ResponseCode.DATA_ALREADY_EXISTS, detail, data)


class DataValidationException(DataException):
    """数据验证异常"""
    
    def __init__(self, detail: Optional[str] = None, data: Optional[Any] = None):
        super().__init__(ResponseCode.DATA_VALIDATION_ERROR, detail, data)


# ================ 异常快捷创建函数 ================

def raise_user_not_found(detail: str = "用户不存在") -> None:
    """抛出用户不存在异常"""
    raise UserNotFoundException(detail)


def raise_invalid_password(detail: str = "密码错误") -> None:
    """抛出密码错误异常"""
    raise InvalidPasswordException(detail)


def raise_token_expired(detail: str = "令牌已过期") -> None:
    """抛出令牌过期异常"""
    raise TokenExpiredException(detail)


def raise_permission_denied(detail: str = "权限不足") -> None:
    """抛出权限不足异常"""
    raise AuthorizationException(detail)


def raise_data_not_found(detail: str = "数据不存在") -> None:
    """抛出数据不存在异常"""
    raise DataNotFoundException(detail)


def raise_validation_error(detail: str = "数据验证失败") -> None:
    """抛出数据验证异常"""
    raise ValidationException(detail)


# 便捷的异常抛出函数
def raise_not_found(message: str = "资源不存在"):
    """抛出未找到异常"""
    raise DataNotFoundException(message)


def raise_bad_request(message: str = "请求参数错误"):
    """抛出请求错误异常"""
    raise BusinessException(ResponseCode.BAD_REQUEST, detail=message)


def raise_forbidden(message: str = "权限不足"):
    """抛出权限异常"""
    raise AuthorizationException(message)


def raise_unauthorized(message: str = "认证失败"):
    """抛出认证异常"""
    raise AuthenticationException(message)


# ================ 异常装饰器 ================

from functools import wraps
import logging


def handle_exceptions(
    default_message: str = "操作失败",
    log_errors: bool = True
):
    """异常处理装饰器"""
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except BaseAPIException:
                # 业务异常直接重新抛出
                raise
            except Exception as e:
                if log_errors:
                    logging.error(f"函数 {func.__name__} 发生未处理异常: {str(e)}")
                # 将未知异常转换为业务异常
                raise BusinessException(
                    ResponseCode.INTERNAL_SERVER_ERROR,
                    detail=default_message
                )
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except BaseAPIException:
                raise
            except Exception as e:
                if log_errors:
                    logging.error(f"函数 {func.__name__} 发生未处理异常: {str(e)}")
                raise BusinessException(
                    ResponseCode.INTERNAL_SERVER_ERROR,
                    detail=default_message
                )
        
        import inspect
        if inspect.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator


def handle_service_exceptions(func):
    """服务层异常处理装饰器"""
    from functools import wraps
    import inspect
    
    @wraps(func)
    async def async_wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except BaseAPIException:
            raise
        except Exception as e:
            raise BusinessException(
                ResponseCode.INTERNAL_SERVER_ERROR,
                detail=f"服务异常: {str(e)}"
            )
    
    @wraps(func)
    def sync_wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except BaseAPIException:
            raise
        except Exception as e:
            raise BusinessException(
                ResponseCode.INTERNAL_SERVER_ERROR,
                detail=f"服务异常: {str(e)}"
            )
    
    if inspect.iscoroutinefunction(func):
        return async_wrapper
    else:
        return sync_wrapper
