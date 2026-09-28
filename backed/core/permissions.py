"""认证 / 授权依赖（简化版：单用户 / 自托管场景）

说明：
- 本项目为自托管单用户内容中台，默认不做强制登录。
- 若 config 中配置了 api_token，则要求请求头 `X-API-Token` 与之匹配，否则放行。
- 多用户 / SSO 场景可在后续引入 models.sso_user 与 JWT，再替换本模块。
- 为兼容 core 包聚合导入，这里保留 get_current_user / require_* / PermissionChecker
  的「宽松占位」实现（均不强制校验），业务路由可按需替换。
"""

from typing import Optional

from fastapi import Depends, Header

from config import settings
from utils.custom_exceptions import AuthenticationException


async def get_current_active_user(
    x_api_token: Optional[str] = Header(default=None, alias="X-API-Token"),
) -> None:
    """获取当前活跃用户（单用户场景返回 None，不绑定用户实体）。

    若设置了 api_token，则校验请求头；未设置则视为开放访问。
    """
    token = getattr(settings, "api_token", None)
    if token and x_api_token != token:
        raise AuthenticationException("API Token 无效")
    return None


# 兼容别名
get_current_sso_user = get_current_active_user
get_current_user = get_current_active_user


class PermissionChecker:
    """权限检查器（宽松占位：单用户场景一律放行）。"""

    @staticmethod
    def check_user_access_to_resource(current_user: Optional[object], resource_owner_id: str, resource_type: str = "general") -> bool:
        return True

    @staticmethod
    def check_admin_permission(current_user: Optional[object]) -> bool:
        return True

    @staticmethod
    def check_teacher_permission(current_user: Optional[object]) -> bool:
        return True


async def require_admin(current_user: Optional[object] = Depends(get_current_active_user)) -> Optional[object]:
    return current_user


async def require_teacher(current_user: Optional[object] = Depends(get_current_active_user)) -> Optional[object]:
    return current_user


async def require_student(current_user: Optional[object] = Depends(get_current_active_user)) -> Optional[object]:
    return current_user
