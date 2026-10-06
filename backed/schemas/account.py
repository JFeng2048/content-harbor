"""
平台账号数据验证模型

此文件由 SQL-to-FastAPI-Scaffold 自动生成
"""

from typing import Optional
from datetime import datetime, date, time
from decimal import Decimal
from pydantic import BaseModel, ConfigDict, Field, field_validator


class AccountBase(BaseModel):
    """
    平台账号基础模型
    """
    
    platform: str = Field(
        ...,
        max_length=50,
        
        
        description="平台"
    )
    
    name: str | None = Field(
        None,
        max_length=50,
        
        
        description="账号名"
    )
    
    profile_dir: str = Field(
        ...,
        max_length=512,
        
        
        description="浏览器profile目录"
    )
    
    status: str | None = Field(
        None,
        max_length=20,
        
        
        description="状态(unknown/logined/offline)"
    )
    
    last_check: datetime | None = Field(
        None,
        
        
        
        description="上次检查时间"
    )
    

    


class AccountCreate(AccountBase):
    """
    平台账号创建模型
    """
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                
                "platform": "juejin",
                
                "name": "default",
                
                "profile_dir": "data/profiles/juejin_default",
                
                "status": "unknown",
                
                "last_check": "2026-01-01T00:00:00",
                
            }
        }
    )


class AccountUpdate(BaseModel):
    """
    平台账号更新模型

    注意：状态/标识位字段不在此模型中，请使用专用改状态接口。
    """
    
    
    platform: str | None = Field(
        default=None,
        max_length=50,
        
        
        description="平台"
    )
    
    
    
    name: str | None = Field(
        default=None,
        max_length=50,
        
        
        description="账号名"
    )
    
    
    
    profile_dir: str | None = Field(
        default=None,
        max_length=512,
        
        
        description="浏览器profile目录"
    )
    
    
    
    
    
    last_check: datetime | None = Field(
        default=None,
        
        
        
        description="上次检查时间"
    )
    
    

    class Config:
        extra = "forbid"
        json_schema_extra = {
            "example": {
                
                
                "platform": "juejin",
                
                
                
                "name": "default",
                
                
                
                "profile_dir": "data/profiles/juejin_default",
                
                
                
                
                
                "last_check": "2026-01-01T00:00:00",
                
                
            }
        }



class AccountStatusUpdate(BaseModel):
    """
    平台账号状态/标识位更新模型（专用）
    """
    
    status: str = Field(
        ...,
        max_length=20,
        
        
        description="状态(unknown/logined/offline)"
    )
    

    class Config:
        extra = "forbid"
        json_schema_extra = {
            "example": {
                
                "status": "unknown",
                
            }
        }



class AccountResponse(BaseModel):
    """
    平台账号响应模型
    """
    
    id: int
    
    platform: str
    
    name: str | None
    
    profile_dir: str
    
    status: str | None
    
    last_check: datetime | None
    

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                
                "id": 1,
                
                "platform": "juejin",
                
                "name": "default",
                
                "profile_dir": "data/profiles/juejin_default",
                
                "status": "unknown",
                
                "last_check": "2026-01-01T00:00:00",
                
            }
        }
