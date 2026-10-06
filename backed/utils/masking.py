"""通用脱敏工具（可独立于业务项目使用）"""

from __future__ import annotations


def mask_phone(phone: str | None, placeholder: str = "****") -> str:
    """手机号脱敏：前 3 + **** + 后 4。"""
    if not phone:
        return placeholder
    text = str(phone)
    if len(text) >= 11:
        return f"{text[:3]}{placeholder}{text[-4:]}"
    return placeholder


def mask_email(email: str | None, placeholder: str = "****") -> str:
    """邮箱脱敏：本地名部分打码。"""
    if not email or "@" not in str(email):
        return placeholder
    local, domain = str(email).split("@", 1)
    if len(local) <= 2:
        return f"**@{domain}"
    return f"{local[:2]}{placeholder}@{domain}"


def mask_middle(
    value: str | None,
    keep_start: int = 2,
    keep_end: int = 2,
    placeholder: str = "****",
) -> str:
    """通用中间打码。"""
    if not value:
        return placeholder
    text = str(value)
    if len(text) <= keep_start + keep_end:
        return placeholder
    return f"{text[:keep_start]}{placeholder}{text[-keep_end:]}"


def mask_id_card(id_card: str | None, placeholder: str = "****") -> str:
    """身份证号脱敏：前 3 + **** + 后 4。"""
    return mask_middle(id_card, keep_start=3, keep_end=4, placeholder=placeholder)
