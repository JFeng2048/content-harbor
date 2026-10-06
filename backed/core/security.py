"""应用侧安全装配（薄封装）

密码哈希 → ``utils.security.SecurityUtil``
JWT 签发/校验 → ``utils.auth.jwt_authenticator``
脱敏 → ``utils.masking``
业务认证 Depends → ``core.permissions``

本模块不再实现独立算法，仅提供与历史 ``SecurityHelper`` 兼容的入口。
"""

from datetime import timedelta
from typing import Any, Dict, Optional

from utils.auth import jwt_authenticator
from utils.security import SecurityUtil


class SecurityHelper:
    """兼容旧调用方的静态门面（委托 utils）。"""

    @staticmethod
    def get_password_hash(password: str) -> str:
        return SecurityUtil.hash_password(password)

    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        return SecurityUtil.verify_password(plain_password, hashed_password)

    @staticmethod
    def hash_password(password: str) -> str:
        """bcrypt 哈希（与 get_password_hash 相同）。历史 PBKDF2+salt 已废弃。"""
        return SecurityUtil.hash_password(password)

    @staticmethod
    def generate_random_token(length: int = 32) -> str:
        return SecurityUtil.generate_token(length)

    @staticmethod
    def generate_random_string(length: int = 16) -> str:
        import secrets

        return secrets.token_hex(length)

    @staticmethod
    def create_access_token(
        data: Dict[str, Any], expires_delta: Optional[timedelta] = None
    ) -> str:
        return jwt_authenticator.create_access_token(data, expires_delta)

    @staticmethod
    def verify_token(token: str) -> Dict[str, Any]:
        return jwt_authenticator.verify_token(token)


security_helper = SecurityHelper()


def get_password_hash(password: str) -> str:
    return SecurityHelper.get_password_hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return SecurityHelper.verify_password(plain_password, hashed_password)


def create_access_token(
    data: Dict[str, Any], expires_delta: Optional[timedelta] = None
) -> str:
    return SecurityHelper.create_access_token(data, expires_delta)


def verify_token(token: str) -> Dict[str, Any]:
    return SecurityHelper.verify_token(token)
