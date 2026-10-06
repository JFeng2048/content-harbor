"""认证依赖（单用户 / 自托管场景）

- 本项目为自托管单用户内容中台，默认不做强制登录。
- 若 config 中配置了 api_token，则要求请求头 `X-API-Token` 与之匹配，否则放行。
- 多用户 / SSO 场景可后续引入用户模型与 JWT 再替换本模块。
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
