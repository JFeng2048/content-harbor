"""通用工具包

约定：本包内模块应可脱离本项目业务模型独立复用。
业务权限（SsoUser 等）请使用 core.permissions。
"""

from utils.auth import JWTAuthenticator, create_jwt_authenticator_from_settings, jwt_authenticator
from utils.custom_exceptions import (
    AuthenticationException,
    AuthorizationException,
    BaseAPIException,
    BusinessException,
    ConflictException,
    DatabaseException,
    NotFoundException,
    RateLimitException,
    ResourceNotOwnedException,
    ValidationException,
)
from utils.ids import new_business_id, new_urlsafe_token, new_uuid4_hex
from utils.logger import (
    get_logger,
    get_security_logger,
    log_api_access,
    log_security_event,
    setup_logger,
    setup_logging,
)
from utils.masking import mask_email, mask_middle, mask_phone, mask_id_card
from utils.response_code import ResponseCode
from utils.security import SecurityUtil
from utils.validators import (
    DataValidator,
    validate_email,
    validate_length,
    validate_phone,
    validate_required,
    validate_username,
)

__all__ = [
    "JWTAuthenticator",
    "create_jwt_authenticator_from_settings",
    "jwt_authenticator",
    "BaseAPIException",
    "AuthenticationException",
    "AuthorizationException",
    "ValidationException",
    "NotFoundException",
    "ConflictException",
    "RateLimitException",
    "BusinessException",
    "DatabaseException",
    "ResourceNotOwnedException",
    "ResponseCode",
    "SecurityUtil",
    "DataValidator",
    "validate_email",
    "validate_phone",
    "validate_username",
    "validate_required",
    "validate_length",
    "setup_logging",
    "setup_logger",
    "get_logger",
    "get_security_logger",
    "log_security_event",
    "log_api_access",
    "mask_phone",
    "mask_email",
    "mask_middle",
    "mask_id_card",
    "new_uuid4_hex",
    "new_business_id",
    "new_urlsafe_token",
]
