"""
应用配置模块

此文件由 SQL-to-FastAPI-Scaffold 自动生成
"""

from typing import Optional, List, Any
from pydantic import field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """
    应用配置类
    """
    APP_NAME: str = "FastAPI Project"
    APP_VERSION: str = "1.0.0"
    APP_DESCRIPTION: str = "FastAPI 项目"
    DEBUG: bool = True

    HOST: str = "0.0.0.0"
    PORT: int = 8000

    DATABASE_URL: str = "mysql+pymysql://user:password@localhost:3306/fastapi"

    SECRET_KEY: str = "your-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    CORS_ORIGINS: List[str] = ["*"]
    CORS_ALLOW_CREDENTIALS: bool = True
    CORS_ALLOW_METHODS: List[str] = ["*"]
    CORS_ALLOW_HEADERS: List[str] = ["*"]

    LOG_LEVEL: str = "INFO"
    LOG_FILE: str = "logs/app.log"

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def validate_cors_origins(cls, v: Any) -> List[str]:
        """
        解析CORS_ORIGINS，支持逗号分隔或单值
        """
        if isinstance(v, str):
            if v.strip() == "*":
                return ["*"]
            return [x.strip() for x in v.split(",") if x.strip()]
        return v if isinstance(v, list) else ["*"]

    @field_validator("CORS_ALLOW_METHODS", mode="before")
    @classmethod
    def validate_cors_methods(cls, v: Any) -> List[str]:
        """
        解析CORS_ALLOW_METHODS，支持逗号分隔或单值
        """
        if isinstance(v, str):
            if v.strip() == "*":
                return ["*"]
            return [x.strip() for x in v.split(",") if x.strip()]
        return v if isinstance(v, list) else ["*"]

    @field_validator("CORS_ALLOW_HEADERS", mode="before")
    @classmethod
    def validate_cors_headers(cls, v: Any) -> List[str]:
        """
        解析CORS_ALLOW_HEADERS，支持逗号分隔或单值
        """
        if isinstance(v, str):
            if v.strip() == "*":
                return ["*"]
            return [x.strip() for x in v.split(",") if x.strip()]
        return v if isinstance(v, list) else ["*"]

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
