"""审计日志中间件（仅保留 AuditMiddleware）

说明：
- SecurityAuditMiddleware 与已删除的 SQL 注入防护中间件重复检测可疑模式，
  且其依赖的 utils.audit 存在非异步上下文 create_task 隐患，故移除。
- 全量 HTTP 审计职责统一由 AuditMiddleware 承担。
"""

import time
import json
from typing import Dict, Any, Optional

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from utils.audit import audit_logger, AuditAction, AuditLevel
from utils.logger import setup_logger

logger = setup_logger(__name__)


class AuditMiddleware(BaseHTTPMiddleware):
    """审计日志中间件

    自动记录所有HTTP请求和响应的审计日志
    """

    def __init__(
        self,
        app,
        log_request_body: bool = False,
        log_response_body: bool = False,
        exclude_paths: list = None,
        sensitive_headers: list = None
    ):
        super().__init__(app)
        self.log_request_body = log_request_body
        self.log_response_body = log_response_body
        self.exclude_paths = exclude_paths or [
            '/health', '/metrics', '/docs', '/openapi.json',
            '/api/v1/auth/login', '/api/v1/auth/logout'
        ]
        self.sensitive_headers = sensitive_headers or ['authorization', 'cookie', 'x-api-key']

    async def dispatch(self, request: Request, call_next) -> Response:
        """处理请求和响应的审计日志"""
        start_time = time.time()

        # 检查是否需要排除此路径
        if self._should_exclude_path(request.url.path):
            return await call_next(request)

        # 记录请求开始
        request_data = await self._extract_request_data(request)

        try:
            # 处理请求
            response = await call_next(request)

            # 计算处理时间
            processing_time = time.time() - start_time

            # 记录成功的请求
            await self._log_request_response(
                request=request,
                response=response,
                request_data=request_data,
                processing_time=processing_time,
                success=True
            )

            return response

        except Exception as e:
            # 计算处理时间
            processing_time = time.time() - start_time

            # 记录失败的请求
            await self._log_request_response(
                request=request,
                response=None,
                request_data=request_data,
                processing_time=processing_time,
                success=False,
                error=e
            )

            raise

    def _should_exclude_path(self, path: str) -> bool:
        """检查是否应该排除此路径"""
        return any(excluded in path for excluded in self.exclude_paths)

    async def _extract_request_data(self, request: Request) -> Dict[str, Any]:
        """提取请求数据"""
        request_data = {
            'method': request.method,
            'url': str(request.url),
            'path': request.url.path,
            'query_params': dict(request.query_params),
            'headers': self._sanitize_headers(dict(request.headers)),
            'client_ip': request.client.host if request.client else None,
            'content_type': request.headers.get('content-type'),
            'content_length': request.headers.get('content-length')
        }

        # 记录请求体（如果启用）
        if self.log_request_body and request.method in ['POST', 'PUT', 'PATCH']:
            try:
                # 读取请求体
                body = await request.body()
                if body:
                    content_type = request.headers.get('content-type', '')

                    if 'application/json' in content_type:
                        try:
                            request_data['body'] = json.loads(body.decode('utf-8'))
                        except Exception:
                            request_data['body'] = body.decode('utf-8', errors='ignore')[:1000]
                    elif 'multipart/form-data' not in content_type:
                        request_data['body'] = body.decode('utf-8', errors='ignore')[:1000]
                    else:
                        request_data['body'] = f"<multipart-data:{len(body)} bytes>"
            except Exception as e:
                logger.warning(f"无法读取请求体: {e}")

        return request_data

    def _sanitize_headers(self, headers: Dict[str, str]) -> Dict[str, str]:
        """清理敏感头信息"""
        sanitized = {}
        for key, value in headers.items():
            if key.lower() in self.sensitive_headers:
                sanitized[key] = "***REDACTED***"
            else:
                sanitized[key] = value
        return sanitized

    async def _log_request_response(
        self,
        request: Request,
        response: Optional[Response],
        request_data: Dict[str, Any],
        processing_time: float,
        success: bool,
        error: Optional[Exception] = None
    ):
        """记录请求和响应的审计日志"""
        try:
            # 确定审计动作
            if request.method == 'GET':
                action = AuditAction.READ
            elif request.method == 'POST':
                action = AuditAction.CREATE
            elif request.method in ['PUT', 'PATCH']:
                action = AuditAction.UPDATE
            elif request.method == 'DELETE':
                action = AuditAction.DELETE
            else:
                action = AuditAction.READ

            # 构建审计元数据
            metadata = {
                'request': request_data,
                'processing_time': processing_time,
                'success': success
            }

            # 添加响应信息
            if response:
                metadata['response'] = {
                    'status_code': response.status_code,
                    'headers': dict(response.headers),
                    'content_length': response.headers.get('content-length')
                }

                # 记录响应体（如果启用且不是大文件）
                if self.log_response_body and hasattr(response, 'body'):
                    try:
                        if response.headers.get('content-type', '').startswith('application/json'):
                            body_text = (
                                response.body.decode('utf-8')
                                if hasattr(response.body, 'decode')
                                else str(response.body)
                            )
                            if len(body_text) < 10000:  # 限制大小
                                metadata['response']['body'] = body_text[:1000]
                    except Exception:
                        pass

            # 添加错误信息
            if error:
                metadata['error'] = {
                    'type': type(error).__name__,
                    'message': str(error)
                }

            # 确定审计级别
            if not success:
                level = AuditLevel.ERROR
            elif response and response.status_code >= 400:
                level = AuditLevel.WARNING
            else:
                level = AuditLevel.INFO

            # 提取用户信息（如果可用）
            user_id = None
            username = None

            # 尝试从请求中提取用户信息
            if hasattr(request.state, 'current_user'):
                user = request.state.current_user
                user_id = getattr(user, 'id', None)
                username = getattr(user, 'username', None)

            # 记录审计日志
            audit_logger.log_data_operation(
                action=action,
                resource_type='http_request',
                resource_id=f"{request.method} {request.url.path}",
                user_id=str(user_id) if user_id else None,
                username=username,
                success=success,
                error_message=str(error) if error else None,
                metadata=metadata,
                request=request
            )

        except Exception as e:
            logger.error(f"审计日志记录失败: {e}")


def create_audit_middleware(
    log_request_body: bool = False,
    log_response_body: bool = False,
    exclude_paths: list = None
) -> AuditMiddleware:
    """创建审计中间件实例"""
    return AuditMiddleware(
        app=None,
        log_request_body=log_request_body,
        log_response_body=log_response_body,
        exclude_paths=exclude_paths
    )
