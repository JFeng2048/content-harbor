"""
任务流水数据验证模型

此文件由 SQL-to-FastAPI-Scaffold 自动生成
"""

from typing import Optional
from datetime import datetime, date, time
from decimal import Decimal
from pydantic import BaseModel, ConfigDict, Field, field_validator


class JobBase(BaseModel):
    """
    任务流水基础模型
    """
    
    type: str = Field(
        ...,
        max_length=20,
        
        
        description="类型(publish/update/sync/import)"
    )
    
    article_id: int | None = Field(
        None,
        
        
        
        description="文章ID"
    )
    
    platform: str | None = Field(
        None,
        max_length=50,
        
        
        description="平台"
    )
    
    status: str | None = Field(
        None,
        max_length=20,
        
        
        description="状态(running/ok/failed)"
    )
    
    message: str | None = Field(
        None,
        
        
        
        description="消息"
    )
    
    created_at: datetime | None = Field(
        None,
        
        
        
        description="创建时间"
    )
    
    finished_at: datetime | None = Field(
        None,
        
        
        
        description="完成时间"
    )
    

    


class JobCreate(JobBase):
    """
    任务流水创建模型
    """
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                
                "type": "publish",
                
                "article_id": 1,
                
                "platform": "juejin",
                
                "status": "running",
                
                "message": "",
                
                "created_at": "2026-01-01T00:00:00",
                
                "finished_at": "2026-01-01T00:00:00",
                
            }
        }
    )


class JobUpdate(BaseModel):
    """
    任务流水更新模型

    注意：状态/标识位字段不在此模型中，请使用专用改状态接口。
    """
    
    
    type: str | None = Field(
        default=None,
        max_length=20,
        
        
        description="类型(publish/update/sync/import)"
    )
    
    
    
    article_id: int | None = Field(
        default=None,
        
        
        
        description="文章ID"
    )
    
    
    
    platform: str | None = Field(
        default=None,
        max_length=50,
        
        
        description="平台"
    )
    
    
    
    
    
    message: str | None = Field(
        default=None,
        
        
        
        description="消息"
    )
    
    
    
    created_at: datetime | None = Field(
        default=None,
        
        
        
        description="创建时间"
    )
    
    
    
    finished_at: datetime | None = Field(
        default=None,
        
        
        
        description="完成时间"
    )
    
    

    class Config:
        extra = "forbid"
        json_schema_extra = {
            "example": {
                
                
                "type": "publish",
                
                
                
                "article_id": 1,
                
                
                
                "platform": "juejin",
                
                
                
                
                
                "message": "",
                
                
                
                "created_at": "2026-01-01T00:00:00",
                
                
                
                "finished_at": "2026-01-01T00:00:00",
                
                
            }
        }



class JobStatusUpdate(BaseModel):
    """
    任务流水状态/标识位更新模型（专用）
    """
    
    status: str = Field(
        ...,
        max_length=20,
        
        
        description="状态(running/ok/failed)"
    )
    

    class Config:
        extra = "forbid"
        json_schema_extra = {
            "example": {
                
                "status": "running",
                
            }
        }



class JobResponse(BaseModel):
    """
    任务流水响应模型
    """
    
    id: int
    
    type: str
    
    article_id: int | None
    
    platform: str | None
    
    status: str | None
    
    message: str | None
    
    created_at: datetime | None
    
    finished_at: datetime | None
    

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                
                "id": 1,
                
                "type": "publish",
                
                "article_id": 1,
                
                "platform": "juejin",
                
                "status": "running",
                
                "message": "",
                
                "created_at": "2026-01-01T00:00:00",
                
                "finished_at": "2026-01-01T00:00:00",
                
            }
        }
