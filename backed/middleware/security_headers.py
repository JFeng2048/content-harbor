"""安全头中间件（仅保留 SecurityHeadersMiddleware）

说明：
- CORS 统一使用 Starlette 内置 CORSMiddleware（见 app/middleware.py），
  故移除原 hand-rolled 的 CORSSecurityMiddleware。
- 请求日志职责并入 AuditMiddleware，故移除原 RequestLoggingMiddleware。
"""

from typing import Dict

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from config import settings


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """安全HTTP头中间件"""

    def __init__(self, app):
        super().__init__(app)
        self.security_headers = self._get_security_headers()

    async def dispatch(self, request: Request, call_next) -> Response:
        """处理请求并添加安全头"""
        response = await call_next(request)
        # 针对文档相关路径，放宽CSP策略
        doc_paths = ["/docs", "/redoc", "/openapi.json"]
        if any(request.url.path.startswith(path) for path in doc_paths):
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net; "
                "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
                "img-src 'self' data: https:; "
                "font-src 'self' https:; "
                "connect-src 'self' https:; "
                "frame-ancestors 'none';"
            )
        else:
            for header_name, header_value in self.security_headers.items():
                response.headers[header_name] = header_value
        # 移除可能暴露服务器信息的头
        if "Server" in response.headers:
            del response.headers["Server"]
        if "X-Powered-By" in response.headers:
            del response.headers["X-Powered-By"]
        return response

    def _get_security_headers(self) -> Dict[str, str]:
        """获取安全头配置"""
        return {
            # 防止XSS攻击
            "X-Content-Type-Options": "nosniff",
            # 防止点击劫持
            "X-Frame-Options": "DENY",
            # XSS保护
            "X-XSS-Protection": "1; mode=block",
            # 引用者策略
            "Referrer-Policy": "strict-origin-when-cross-origin",
            # 内容安全策略
            "Content-Security-Policy": (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
                "style-src 'self' 'unsafe-inline'; "
                "img-src 'self' data: https:; "
                "font-src 'self' https:; "
                "connect-src 'self' https:; "
                "frame-ancestors 'none';"
            ),
            # 权限策略
            "Permissions-Policy": (
                "geolocation=(), "
                "microphone=(), "
                "camera=(), "
                "magnetometer=(), "
                "gyroscope=(), "
                "payment=(), "
                "usb=()"
            ),
            # 自定义安全头（兼容 skill Settings.API_VERSION 与 starter settings.api_version）
            "X-API-Version": str(
                getattr(settings, "API_VERSION", None)
                or getattr(settings, "api_version", None)
                or getattr(settings, "APP_VERSION", "v1")
            ),
        }
