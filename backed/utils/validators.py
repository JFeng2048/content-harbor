"""通用字段校验工具（可独立于业务项目使用）

原先 validator.py / validators.py 已合并为本模块。
"""

from __future__ import annotations

import re
from typing import Any, Optional

EMAIL_PATTERN = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")
PHONE_PATTERN = re.compile(r"^1[3-9]\d{9}$")
USERNAME_PATTERN = re.compile(r"^[a-zA-Z0-9_]{3,32}$")


def validate_email(email: str | None) -> bool:
    """校验邮箱格式。"""
    if not email:
        return False
    return bool(EMAIL_PATTERN.match(str(email)))


def validate_phone(phone: str | None) -> bool:
    """校验中国大陆手机号格式。"""
    if not phone:
        return False
    return bool(PHONE_PATTERN.match(str(phone)))


def validate_username(username: str | None) -> bool:
    """校验用户名（字母/数字/下划线，3-32 位）。"""
    if not username:
        return False
    return bool(USERNAME_PATTERN.match(str(username)))


def validate_required(value: Any, field_name: str = "字段") -> bool:
    """校验必填（None 或空字符串非法）。"""
    if value is None or value == "":
        raise ValueError(f"{field_name}不能为空")
    return True


def validate_length(
    value: str | None,
    min_len: Optional[int] = None,
    max_len: Optional[int] = None,
    field_name: str = "字段",
) -> bool:
    """校验字符串长度范围。"""
    if value is None:
        raise ValueError(f"{field_name}不能为空")
    if min_len is not None and len(value) < min_len:
        raise ValueError(f"{field_name}长度不能少于{min_len}个字符")
    if max_len is not None and len(value) > max_len:
        raise ValueError(f"{field_name}长度不能超过{max_len}个字符")
    return True


class DataValidator:
    """面向对象封装，便于静态调用。"""

    validate_email = staticmethod(validate_email)
    validate_phone = staticmethod(validate_phone)
    validate_username = staticmethod(validate_username)
    validate_required = staticmethod(validate_required)
    validate_length = staticmethod(validate_length)
