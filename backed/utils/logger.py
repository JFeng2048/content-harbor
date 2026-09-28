"""日志工具（通用，可独立于业务项目使用）

统一入口：原先 logger.py / loggings.py 已合并为本模块。

能力：
- setup_logging：配置根日志（控制台 + 滚动文件）
- get_logger / setup_logger：获取命名日志器
- log_security_event / log_api_access：结构化安全与访问日志
"""

from __future__ import annotations

import logging
import logging.handlers
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


_DEFAULT_FORMAT = (
    "%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s"
)
_SIMPLE_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"


def setup_logging(
    *,
    level: str | int = "INFO",
    log_dir: str | Path = "logs",
    app_log_name: str = "app.log",
    error_log_name: str = "error.log",
    security_log_name: str = "security.log",
    max_bytes: int = 10 * 1024 * 1024,
    backup_count: int = 5,
    security_backup_count: int = 10,
) -> logging.Logger:
    """配置根日志器：控制台 + app/error/security 滚动文件。

    不依赖项目 config；调用方可传入 level / log_dir。
    """
    if isinstance(level, str):
        level_value = getattr(logging, level.upper(), logging.INFO)
    else:
        level_value = level

    path = Path(log_dir)
    path.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter(_DEFAULT_FORMAT)
    root = logging.getLogger()
    root.setLevel(level_value)
    root.handlers.clear()

    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.INFO)
    console.setFormatter(formatter)
    root.addHandler(console)

    app_handler = logging.handlers.RotatingFileHandler(
        path / app_log_name,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    app_handler.setLevel(logging.DEBUG)
    app_handler.setFormatter(formatter)
    root.addHandler(app_handler)

    error_handler = logging.handlers.RotatingFileHandler(
        path / error_log_name,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(formatter)
    root.addHandler(error_handler)

    security_logger = logging.getLogger("security")
    security_logger.handlers.clear()
    security_handler = logging.handlers.RotatingFileHandler(
        path / security_log_name,
        maxBytes=max_bytes,
        backupCount=security_backup_count,
        encoding="utf-8",
    )
    security_handler.setLevel(logging.INFO)
    security_handler.setFormatter(formatter)
    security_logger.addHandler(security_handler)
    security_logger.setLevel(logging.INFO)
    security_logger.propagate = False

    return root


def get_logger(name: str) -> logging.Logger:
    """获取命名日志器。"""
    return logging.getLogger(name)


def setup_logger(
    name: Optional[str] = None,
    level: int = logging.INFO,
    format_string: Optional[str] = None,
) -> logging.Logger:
    """为指定名称配置一个仅含控制台输出的日志器（轻量场景）。"""
    logger_name = name or __name__
    logger = logging.getLogger(logger_name)
    logger.setLevel(level)
    if logger.handlers:
        return logger

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter(format_string or _SIMPLE_FORMAT))
    logger.addHandler(handler)
    return logger


def get_security_logger() -> logging.Logger:
    """获取安全事件日志器。"""
    return logging.getLogger("security")


def log_security_event(
    event_type: str,
    user_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    """记录安全事件。"""
    get_security_logger().info(
        "SECURITY_EVENT: %s",
        {
            "event_type": event_type,
            "timestamp": datetime.now().isoformat(),
            "user_id": user_id,
            "details": details or {},
        },
    )


def log_api_access(
    method: str,
    path: str,
    user_id: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    status_code: int | None = None,
    response_time: float | None = None,
) -> None:
    """记录 API 访问日志。"""
    logging.getLogger("access").info(
        "API_ACCESS: %s",
        {
            "method": method,
            "path": path,
            "user_id": user_id,
            "ip_address": ip_address,
            "user_agent": user_agent,
            "status_code": status_code,
            "response_time": response_time,
            "timestamp": datetime.now().isoformat(),
        },
    )
