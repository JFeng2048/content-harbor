"""通用安全工具（可独立于业务项目使用）

提供密码哈希、盐值/令牌生成、输入安全校验、输入清理、限流键生成等。
不读项目 config；JWT 装配见 utils.auth，业务 Depends 见 core.permissions。
"""

import hmac
import re
import secrets
from typing import Any

import bcrypt


# SQL 注入 / XSS 危险特征（大小写不敏感）
_SQL_XSS_PATTERNS = [
    r"(?i)(\bunion\b.*\bselect\b)",
    r"(?i)(\bselect\b.*\bfrom\b)",
    r"(?i)(\bdrop\b.*\btable\b)",
    r"(?i)(\binsert\b.*\binto\b)",
    r"(?i)(\bdelete\b.*\bfrom\b)",
    r"(?i)(\bor\b\s+\d+\s*=\s*\d+)",
    r"(?i)(\band\b\s+\d+\s*=\s*\d+)",
    r";\s*--",
    r"--\s",
    r"/\*.*\*/",
    r"(?i)(\bscript\b)",
    r"(?i)(\bonerror\b)",
    r"(?i)(\balert\s*\()",
    r"(?i)(\beval\s*\()",
]
_COMPILED_PATTERNS = [re.compile(p) for p in _SQL_XSS_PATTERNS]


class SecurityUtil:
    """通用安全工具类（静态方法集合）。"""

    @staticmethod
    def hash_password(password: str) -> str:
        """对密码进行 bcrypt 哈希（与 SsoUser.set_password 一致）。"""
        return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    @staticmethod
    def verify_password(password: str, hashed: str) -> bool:
        """校验密码与哈希是否匹配。"""
        try:
            if not password or not hashed:
                return False
            return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
        except Exception:
            return False

    @staticmethod
    def generate_salt() -> str:
        """生成随机盐值（hex）。"""
        return secrets.token_hex(16)

    @staticmethod
    def generate_token(length: int = 32) -> str:
        """生成安全的 URL 安全随机令牌。"""
        return secrets.token_urlsafe(length)

    @staticmethod
    def safe_compare(a: Any, b: Any) -> bool:
        """常量时间比较，降低时序攻击风险。"""
        if type(a) is not type(b):
            return False
        if isinstance(a, str):
            return hmac.compare_digest(a, b)
        return hmac.compare_digest(str(a), str(b))

    @staticmethod
    def validate_input(value: str) -> bool:
        """校验输入是否安全（无 SQL 注入 / XSS 特征）。

        安全返回 True，发现危险特征返回 False。
        """
        if value is None:
            return True
        text = str(value)
        for pattern in _COMPILED_PATTERNS:
            if pattern.search(text):
                return False
        return True

    @staticmethod
    def sanitize_input(value: str) -> str:
        """清理输入中的 HTML / 脚本标签。"""
        if value is None:
            return ""
        cleaned = re.sub(r"<[^>]*>", "", str(value))
        return cleaned.strip()

    @staticmethod
    def generate_rate_limit_key(ip: str, endpoint: str) -> str:
        """生成限流缓存键。"""
        safe_endpoint = endpoint.replace("/", "_").replace(":", "_")
        return f"ratelimit:{ip}:{safe_endpoint}"


# 模块级别名，便于直接 import
get_password_hash = SecurityUtil.hash_password
verify_password = SecurityUtil.verify_password
