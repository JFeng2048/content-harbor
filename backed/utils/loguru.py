"""日志配置模块

此文件由 SQL-to-FastAPI-Scaffold 自动生成
"""

import sys
from loguru import logger


def setup_logging():
    """
    配置日志系统
    """
    logger.remove()

    logger.add(
        sys.stdout,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        level="INFO"
    )

    logger.add(
        "logs/app.log",
        rotation="50 MB",
        retention="10 days",
        compression="zip",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        level="INFO"
    )

    return logger


def get_logger(name: str):
    """
    获取日志记录器

    Args:
        name: 模块名称
    """
    return logger.bind(name=name)
