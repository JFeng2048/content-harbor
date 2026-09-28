"""通用 ID / 令牌生成工具（可独立于业务项目使用）"""

from __future__ import annotations

import secrets
import uuid
from datetime import datetime


def new_uuid4_hex(length: int | None = None) -> str:
    """生成 uuid4 hex；可截断到指定长度。"""
    value = uuid.uuid4().hex
    return value if length is None else value[:length]


def new_business_id(prefix: str = "", max_length: int = 22) -> str:
    """时间戳 + 4 位随机数，可选前缀，总长不超过 max_length。"""
    stamp = datetime.now().strftime("%Y%m%d%H%M%S") + f"{secrets.randbelow(10000):04d}"
    value = f"{prefix}{stamp}" if prefix else stamp
    return value[:max_length]


def new_urlsafe_token(length: int = 32) -> str:
    """URL 安全随机令牌。"""
    return secrets.token_urlsafe(length)
