"""审计日志系统"""

import json
import asyncio
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List
from functools import wraps
from enum import Enum
from dataclasses import dataclass, asdict
from fastapi import Request
from sqlalchemy.orm import Session

from utils.logger import get_logger, setup_logger
from config import settings

logger = get_logger(__name__)


class AuditLevel(str, Enum):
    """审计级别"""
    INFO = "info"           # 一般信息
    WARNING = "warning"     # 警告
    ERROR = "error"         # 错误
    CRITICAL = "critical"   # 严重


class AuditAction(str, Enum):
    """审计操作类型"""
    # 认证相关
    LOGIN = "login"
    LOGOUT = "logout"
    LOGIN_FAILED = "login_failed"
    PASSWORD_CHANGE = "password_change"
    
    # 数据操作
    CREATE = "create"
    READ = "read"
    UPDATE = "update"
    DELETE = "delete"
    
    # 系统操作
    SYSTEM_CONFIG = "system_config"
    USER_MANAGEMENT = "user_management"
    PERMISSION_CHANGE = "permission_change"
    
    # 安全事件
    SECURITY_VIOLATION = "security_violation"
    SUSPICIOUS_ACTIVITY = "suspicious_activity"
    ACCESS_DENIED = "access_denied"


@dataclass
class AuditEvent:
    """审计事件数据类"""
    
    # 基础信息
    timestamp: str
    level: AuditLevel
    action: AuditAction
    message: str
    
    # 用户信息
    user_id: Optional[str] = None
    username: Optional[str] = None
    user_role: Optional[str] = None
    
    # 请求信息
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    request_method: Optional[str] = None
    request_path: Optional[str] = None
    request_id: Optional[str] = None
    
    # 资源信息
    resource_type: Optional[str] = None
    resource_id: Optional[str] = None
    
    # 操作结果
    success: bool = True
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    
    # 附加数据
    metadata: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return asdict(self)
    
    def to_json(self) -> str:
        """转换为JSON字符串"""
        return json.dumps(self.to_dict(), ensure_ascii=False, default=str)


class AuditLogger:
    """审计日志记录器"""
    
    def __init__(self):
        self.logger = setup_logger("audit")
        self.events_queue: List[AuditEvent] = []
        self._setup_audit_logger()
    
    def _setup_audit_logger(self):
        """设置审计日志器"""
        import logging.handlers
        from pathlib import Path
        
        # 创建审计日志目录
        audit_log_dir = Path("logs/audit")
        audit_log_dir.mkdir(parents=True, exist_ok=True)
        
        # 审计日志格式
        audit_formatter = logging.Formatter(
            '%(asctime)s - AUDIT - %(levelname)s - %(message)s'
        )
        
        # 审计日志文件处理器
        audit_handler = logging.handlers.RotatingFileHandler(
            audit_log_dir / "audit.log",
            maxBytes=50 * 1024 * 1024,  # 50MB
            backupCount=10,
            encoding='utf-8'
        )
        audit_handler.setLevel(logging.INFO)
        audit_handler.setFormatter(audit_formatter)
        
        # 安全事件日志处理器
        security_handler = logging.handlers.RotatingFileHandler(
            audit_log_dir / "security.log",
            maxBytes=50 * 1024 * 1024,  # 50MB
            backupCount=10,
            encoding='utf-8'
        )
        security_handler.setLevel(logging.WARNING)
        security_handler.setFormatter(audit_formatter)
        
        # 配置审计日志器
        audit_logger = logging.getLogger("audit")
        audit_logger.setLevel(logging.INFO)
        audit_logger.addHandler(audit_handler)
        audit_logger.addHandler(security_handler)
        
        self.logger = audit_logger
    
    def log_event(self, event: AuditEvent):
        """记录审计事件"""
        try:
            # 添加到事件队列
            self.events_queue.append(event)
            
            # 根据级别选择日志级别
            log_level_map = {
                AuditLevel.INFO: logging.INFO,
                AuditLevel.WARNING: logging.WARNING,
                AuditLevel.ERROR: logging.ERROR,
                AuditLevel.CRITICAL: logging.CRITICAL
            }
            
            log_level = log_level_map.get(event.level, logging.INFO)
            
            # 记录到日志文件
            self.logger.log(log_level, event.to_json())
            
            # 异步处理（如发送到SIEM系统）
            if event.level in [AuditLevel.WARNING, AuditLevel.ERROR, AuditLevel.CRITICAL]:
                asyncio.create_task(self._handle_critical_event(event))
                
        except Exception as e:
            logger.error(f"审计日志记录失败: {e}")
    
    async def _handle_critical_event(self, event: AuditEvent):
        """处理关键事件"""
        try:
            # 这里可以集成到SIEM系统、发送告警邮件等
            logger.critical(f"关键安全事件: {event.message}")
            
            # 可以添加更多处理逻辑，如：
            # - 发送到Elasticsearch
            # - 推送到Slack/钉钉
            # - 发送邮件通知
            # - 触发自动防护措施
            
        except Exception as e:
            logger.error(f"关键事件处理失败: {e}")
    
    def log_authentication(
        self, 
        action: AuditAction, 
        username: str, 
        ip_address: str, 
        success: bool = True,
        error_message: str = None,
        request: Request = None
    ):
        """记录认证相关事件"""
        event = AuditEvent(
            timestamp=datetime.utcnow().isoformat(),
            level=AuditLevel.INFO if success else AuditLevel.WARNING,
            action=action,
            message=f"用户 {username} {action.value} {'成功' if success else '失败'}",
            username=username,
            ip_address=ip_address,
            user_agent=request.headers.get("user-agent") if request else None,
            request_method=request.method if request else None,
            request_path=str(request.url.path) if request else None,
            success=success,
            error_message=error_message
        )
        
        self.log_event(event)
    
    def log_data_operation(
        self,
        action: AuditAction,
        resource_type: str,
        resource_id: str,
        user_id: str = None,
        username: str = None,
        ip_address: str = None,
        success: bool = True,
        error_message: str = None,
        metadata: Dict[str, Any] = None,
        request: Request = None
    ):
        """记录数据操作事件"""
        event = AuditEvent(
            timestamp=datetime.utcnow().isoformat(),
            level=AuditLevel.INFO if success else AuditLevel.ERROR,
            action=action,
            message=f"{action.value} {resource_type} {resource_id} {'成功' if success else '失败'}",
            user_id=user_id,
            username=username,
            ip_address=ip_address or (request.client.host if request and request.client else None),
            user_agent=request.headers.get("user-agent") if request else None,
            request_method=request.method if request else None,
            request_path=str(request.url.path) if request else None,
            resource_type=resource_type,
            resource_id=resource_id,
            success=success,
            error_message=error_message,
            metadata=metadata
        )
        
        self.log_event(event)
    
    def log_security_event(
        self,
        action: AuditAction,
        message: str,
        level: AuditLevel = AuditLevel.WARNING,
        ip_address: str = None,
        user_id: str = None,
        username: str = None,
        metadata: Dict[str, Any] = None,
        request: Request = None
    ):
        """记录安全事件"""
        event = AuditEvent(
            timestamp=datetime.utcnow().isoformat(),
            level=level,
            action=action,
            message=message,
            user_id=user_id,
            username=username,
            ip_address=ip_address or (request.client.host if request and request.client else None),
            user_agent=request.headers.get("user-agent") if request else None,
            request_method=request.method if request else None,
            request_path=str(request.url.path) if request else None,
            success=False,  # 安全事件通常表示异常情况
            metadata=metadata
        )
        
        self.log_event(event)
    
    def log_system_event(
        self,
        action: AuditAction,
        message: str,
        user_id: str = None,
        username: str = None,
        ip_address: str = None,
        metadata: Dict[str, Any] = None,
        request: Request = None
    ):
        """记录系统事件"""
        event = AuditEvent(
            timestamp=datetime.utcnow().isoformat(),
            level=AuditLevel.INFO,
            action=action,
            message=message,
            user_id=user_id,
            username=username,
            ip_address=ip_address or (request.client.host if request and request.client else None),
            user_agent=request.headers.get("user-agent") if request else None,
            request_method=request.method if request else None,
            request_path=str(request.url.path) if request else None,
            metadata=metadata
        )
        
        self.log_event(event)
    
    def get_recent_events(self, limit: int = 100) -> List[AuditEvent]:
        """获取最近的审计事件"""
        return self.events_queue[-limit:] if self.events_queue else []
    
    def clear_events_queue(self):
        """清空事件队列"""
        self.events_queue.clear()


# 全局审计日志实例
audit_logger = AuditLogger()


def audit_operation(
    action: AuditAction,
    resource_type: str = None,
    level: AuditLevel = AuditLevel.INFO,
    include_request_data: bool = False,
    include_response_data: bool = False
):
    """审计操作装饰器"""
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            start_time = datetime.utcnow()
            request = None
            user_info = {}
            
            # 尝试从参数中提取Request对象和用户信息
            for arg in args:
                if isinstance(arg, Request):
                    request = arg
                    break
            
            # 从kwargs中提取更多信息
            if 'request' in kwargs:
                request = kwargs['request']
            if 'current_user' in kwargs:
                user = kwargs['current_user']
                user_info = {
                    'user_id': getattr(user, 'id', None),
                    'username': getattr(user, 'username', None)
                }
            
            try:
                # 执行函数
                result = await func(*args, **kwargs)
                
                # 记录成功的操作
                metadata = {
                    'execution_time': (datetime.utcnow() - start_time).total_seconds(),
                    'function_name': func.__name__
                }
                
                if include_request_data and request:
                    metadata['request_data'] = {
                        'method': request.method,
                        'path': str(request.url.path),
                        'query_params': dict(request.query_params)
                    }
                
                if include_response_data:
                    metadata['response_data'] = str(result)[:1000]  # 限制长度
                
                audit_logger.log_data_operation(
                    action=action,
                    resource_type=resource_type or func.__name__,
                    resource_id=kwargs.get('id', 'unknown'),
                    user_id=str(user_info.get('user_id')) if user_info.get('user_id') else None,
                    username=user_info.get('username'),
                    success=True,
                    metadata=metadata,
                    request=request
                )
                
                return result
                
            except Exception as e:
                # 记录失败的操作
                metadata = {
                    'execution_time': (datetime.utcnow() - start_time).total_seconds(),
                    'function_name': func.__name__,
                    'error_type': type(e).__name__
                }
                
                audit_logger.log_data_operation(
                    action=action,
                    resource_type=resource_type or func.__name__,
                    resource_id=kwargs.get('id', 'unknown'),
                    user_id=str(user_info.get('user_id')) if user_info.get('user_id') else None,
                    username=user_info.get('username'),
                    success=False,
                    error_message=str(e),
                    metadata=metadata,
                    request=request
                )
                
                raise
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            # 同步函数的包装器
            start_time = datetime.utcnow()
            
            try:
                result = func(*args, **kwargs)
                
                metadata = {
                    'execution_time': (datetime.utcnow() - start_time).total_seconds(),
                    'function_name': func.__name__
                }
                
                audit_logger.log_data_operation(
                    action=action,
                    resource_type=resource_type or func.__name__,
                    resource_id=kwargs.get('id', 'unknown'),
                    success=True,
                    metadata=metadata
                )
                
                return result
                
            except Exception as e:
                metadata = {
                    'execution_time': (datetime.utcnow() - start_time).total_seconds(),
                    'function_name': func.__name__,
                    'error_type': type(e).__name__
                }
                
                audit_logger.log_data_operation(
                    action=action,
                    resource_type=resource_type or func.__name__,
                    resource_id=kwargs.get('id', 'unknown'),
                    success=False,
                    error_message=str(e),
                    metadata=metadata
                )
                
                raise
        
        # 判断是否为异步函数
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator


def audit_security_event(
    action: AuditAction = AuditAction.SECURITY_VIOLATION,
    level: AuditLevel = AuditLevel.WARNING
):
    """安全事件审计装饰器"""
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            request = None
            
            # 提取Request对象
            for arg in args:
                if isinstance(arg, Request):
                    request = arg
                    break
            if 'request' in kwargs:
                request = kwargs['request']
            
            try:
                result = await func(*args, **kwargs)
                return result
                
            except Exception as e:
                # 记录安全事件
                audit_logger.log_security_event(
                    action=action,
                    message=f"安全事件: {func.__name__} - {str(e)}",
                    level=level,
                    metadata={
                        'function_name': func.__name__,
                        'error_type': type(e).__name__,
                        'error_message': str(e)
                    },
                    request=request
                )
                
                raise
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            try:
                result = func(*args, **kwargs)
                return result
                
            except Exception as e:
                audit_logger.log_security_event(
                    action=action,
                    message=f"安全事件: {func.__name__} - {str(e)}",
                    level=level,
                    metadata={
                        'function_name': func.__name__,
                        'error_type': type(e).__name__,
                        'error_message': str(e)
                    }
                )
                
                raise
        
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator
