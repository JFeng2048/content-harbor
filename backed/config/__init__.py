"""配置模块 - 多环境配置（单轨）

约定：
- 唯一配置源：`config_unified.py`（BaseConfig + 各环境类）
- 入口：`config_factory.py` 按 FASTAPI_ENV 选环境，并导出兼容别名 `settings`
- 使用方式：`from config import settings`（扁平字段，如 settings.database_url）
- CLI：`python config/manage.py validate|export|compare|template|list-environments`

请勿再增加第二套嵌套 `settings.py`；业务侧统一走本包导出的 `settings`。
"""

import os

# 防止宿主环境中存在非法的布尔型环境变量（如某些系统 DEBUG=release）
# 导致 pydantic-settings 布尔字段校验失败。这里在加载配置前清理掉非法值。
def _sanitize_bool_env(*names: str) -> None:
    _valid = {"true", "false", "1", "0", "yes", "no", "t", "f", "y", "n"}
    for _n in names:
        _v = os.environ.get(_n)
        if _v is not None and _v.strip().lower() not in _valid:
            os.environ.pop(_n)


_sanitize_bool_env(
    "DEBUG",
    "CACHE_ENABLED",
    "CORS_ALLOW_CREDENTIALS",
    "MIDDLEWARE_SECURITY_HEADERS_ENABLED",
    "MIDDLEWARE_RATE_LIMIT_ENABLED",
    "MIDDLEWARE_AUDIT_ENABLED",
    "RATE_LIMIT_ENABLED",
)

from .config_unified import (
    BaseConfig,
    DevelopmentConfig,
    TestingConfig,
    StagingConfig,
    ProductionConfig,
    DockerConfig,
    Environment,
    LogLevel,
)

from .config_factory import (
    get_config,
    get_config_manager,
    reload_config,
    config,
    config_manager,
    settings,
    ConfigFactory,
    ConfigManager,
)

__all__ = [
    "config",
    "config_manager",
    "settings",
    "get_config",
    "get_config_manager",
    "reload_config",
    "ConfigFactory",
    "ConfigManager",
    "BaseConfig",
    "DevelopmentConfig",
    "TestingConfig",
    "StagingConfig",
    "ProductionConfig",
    "DockerConfig",
    "Environment",
    "LogLevel",
]
