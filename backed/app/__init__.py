"""应用初始化包"""

from .factory import create_app
from .config import AppConfig
from .middleware import setup_middleware
from .exceptions import setup_exception_handlers
from .routes import setup_routes

__all__ = [
    "create_app",
    "AppConfig",
    "setup_middleware",
    "setup_exception_handlers",
    "setup_routes",
]
