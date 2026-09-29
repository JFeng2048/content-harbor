"""JWT 工具（通用）

不绑定具体业务模型。密钥等参数由调用方注入；本项目通过底部懒加载读取 config。

业务认证依赖见 ``core.permissions.get_current_active_user``。
本模块的 ``get_token_payload`` 仅解析 JWT 载荷，不查库。
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, Optional

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from utils.custom_exceptions import AuthenticationException
from utils.logger import log_security_event

security = HTTPBearer()


class JWTAuthenticator:
    """通用 JWT 签发 / 校验器。"""

    def __init__(
        self,
        secret_key: str,
        algorithm: str = "HS256",
        access_token_expire_minutes: int = 30,
    ):
        self.secret_key = secret_key
        self.algorithm = algorithm
        self.access_token_expire_minutes = access_token_expire_minutes

    def create_access_token(
        self,
        data: Dict[str, Any],
        expires_delta: Optional[timedelta] = None,
    ) -> str:
        to_encode = data.copy()
        expire = datetime.utcnow() + (
            expires_delta
            if expires_delta is not None
            else timedelta(minutes=self.access_token_expire_minutes)
        )
        to_encode.update({"exp": expire, "iat": datetime.utcnow()})

        user_id = str(data.get("sub", "") or "")
        try:
            token = jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)
            log_security_event(
                "TOKEN_CREATED",
                user_id=user_id,
                details={"expires_at": expire.isoformat()},
            )
            return token
        except Exception as exc:
            log_security_event(
                "TOKEN_CREATION_FAILED",
                user_id=user_id,
                details={"error": str(exc)},
            )
            raise AuthenticationException("令牌创建失败") from exc

    def verify_token(self, token: str) -> Dict[str, Any]:
        try:
            payload = jwt.decode(
                token, self.secret_key, algorithms=[self.algorithm]
            )
            exp = payload.get("exp")
            if exp is None:
                raise AuthenticationException("令牌格式无效")
            if datetime.utcnow() > datetime.fromtimestamp(exp):
                log_security_event(
                    "TOKEN_EXPIRED",
                    user_id=str(payload.get("sub", "") or ""),
                    details={
                        "expired_at": datetime.fromtimestamp(exp).isoformat()
                    },
                )
                raise AuthenticationException("令牌已过期")
            return payload
        except AuthenticationException:
            raise
        except jwt.PyJWTError as exc:
            log_security_event(
                "TOKEN_VERIFICATION_FAILED",
                user_id="",
                details={
                    "error": str(exc),
                    "token_prefix": token[:20] if token else "",
                },
            )
            raise AuthenticationException("无效的令牌") from exc

    def get_user_id_from_token(self, token: str) -> str:
        payload = self.verify_token(token)
        user_id = payload.get("sub")
        if user_id is None:
            raise AuthenticationException("令牌中缺少用户信息")
        return str(user_id)

    def refresh_token(self, token: str) -> str:
        try:
            payload = self.verify_token(token)
            new_data = {
                k: v for k, v in payload.items() if k not in ("exp", "iat")
            }
            new_token = self.create_access_token(new_data)
            log_security_event(
                "TOKEN_REFRESHED",
                user_id=str(payload.get("sub", "") or ""),
            )
            return new_token
        except AuthenticationException:
            raise
        except Exception as exc:
            log_security_event(
                "TOKEN_REFRESH_FAILED",
                user_id="",
                details={"error": str(exc)},
            )
            raise AuthenticationException("令牌刷新失败") from exc


def create_jwt_authenticator_from_settings() -> JWTAuthenticator:
    """从项目 config 创建认证器（应用装配入口，非纯工具逻辑）。"""
    from config import settings

    return JWTAuthenticator(
        secret_key=settings.secret_key,
        algorithm=settings.algorithm,
        access_token_expire_minutes=settings.access_token_expire_minutes,
    )


# 项目默认实例（懒加载 settings）
jwt_authenticator = create_jwt_authenticator_from_settings()


def get_token_payload(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    """从 Bearer Token 解析出通用载荷 dict（不含业务表查询）。"""
    try:
        payload = jwt_authenticator.verify_token(credentials.credentials)
        user = {
            "user_id": payload.get("sub", ""),
            "username": payload.get("username", ""),
            "user_type": payload.get("user_type", 0),
            "permissions": payload.get("permissions", []),
        }
        if not user["user_id"]:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="无效的认证凭证",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return user
    except AuthenticationException as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="认证失败",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


# 兼容旧名（仅 JWT 载荷，不含 SsoUser；业务路由请改用 core.permissions）
get_current_user = get_token_payload
