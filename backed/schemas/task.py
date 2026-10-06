"""
统一任务数据验证模型

此文件由 SQL-to-FastAPI-Scaffold 自动生成
"""

from typing import Optional
from datetime import datetime, date, time
from decimal import Decimal
from pydantic import BaseModel, ConfigDict, Field, field_validator


class TaskBase(BaseModel):
    """
    统一任务基础模型
    """
    
    task_id: str = Field(
        ...,
        max_length=20,
        
        
        description="短任务ID"
    )
    
    kind: str = Field(
        ...,
        max_length=20,
        
        
        description="类型(publish/update/sync/refresh/login/assist)"
    )
    
    article_id: int | None = Field(
        None,
        
        
        
        description="文章ID"
    )
    
    platforms: str | None = Field(
        None,
        
        
        
        description="平台列表JSON"
    )
    
    account: str | None = Field(
        None,
        max_length=50,
        
        
        description="账号"
    )
    
    draft_only: bool | None = Field(
        None,
        
        
        
        description="仅草稿"
    )
    
    status: str | None = Field(
        None,
        max_length=20,
        
        
        description="状态(pending/running/ok/failed/waiting_human)"
    )
    
    message: str | None = Field(
        None,
        
        
        
        description="消息"
    )
    
    result: str | None = Field(
        None,
        
        
        
        description="结果JSON"
    )
    
    error: str | None = Field(
        None,
        
        
        
        description="错误"
    )
    
    attempts: int | None = Field(
        None,
        
        
        
        description="尝试次数"
    )
    
    created_at: datetime | None = Field(
        None,
        
        
        
        description="创建时间"
    )
    
    updated_at: datetime | None = Field(
        None,
        
        
        
        description="更新时间"
    )
    
    finished_at: datetime | None = Field(
        None,
        
        
        
        description="完成时间"
    )
    

    


class TaskCreate(TaskBase):
    """
    统一任务创建模型
    """
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                
                "task_id": "abc1234567",
                
                "kind": "publish",
                
                "article_id": 1,
                
                "platforms": '["juejin"]',
                
                "account": "default",
                
                "draft_only": False,
                
                "status": "pending",
                
                "message": "",
                
                "result": '{}',
                
                "error": "",
                
                "attempts": 0,
                
                "created_at": "2026-01-01T00:00:00",
                
                "updated_at": "2026-01-01T00:00:00",
                
                "finished_at": "2026-01-01T00:00:00",
                
            }
        }
    )


class TaskUpdate(BaseModel):
    """
    统一任务更新模型

    注意：状态/标识位字段不在此模型中，请使用专用改状态接口。
    """
    
    
    task_id: str | None = Field(
        default=None,
        max_length=20,
        
        
        description="短任务ID"
    )
    
    
    
    kind: str | None = Field(
        default=None,
        max_length=20,
        
        
        description="类型(publish/update/sync/refresh/login/assist)"
    )
    
    
    
    article_id: int | None = Field(
        default=None,
        
        
        
        description="文章ID"
    )
    
    
    
    platforms: str | None = Field(
        default=None,
        
        
        
        description="平台列表JSON"
    )
    
    
    
    account: str | None = Field(
        default=None,
        max_length=50,
        
        
        description="账号"
    )
    
    
    
    draft_only: bool | None = Field(
        default=None,
        
        
        
        description="仅草稿"
    )
    
    
    
    
    
    message: str | None = Field(
        default=None,
        
        
        
        description="消息"
    )
    
    
    
    result: str | None = Field(
        default=None,
        
        
        
        description="结果JSON"
    )
    
    
    
    error: str | None = Field(
        default=None,
        
        
        
        description="错误"
    )
    
    
    
    attempts: int | None = Field(
        default=None,
        
        
        
        description="尝试次数"
    )
    
    
    
    created_at: datetime | None = Field(
        default=None,
        
        
        
        description="创建时间"
    )
    
    
    
    updated_at: datetime | None = Field(
        default=None,
        
        
        
        description="更新时间"
    )
    
    
    
    finished_at: datetime | None = Field(
        default=None,
        
        
        
        description="完成时间"
    )
    
    

    class Config:
        extra = "forbid"
        json_schema_extra = {
            "example": {
                
                
                "task_id": "abc1234567",
                
                
                
                "kind": "publish",
                
                
                
                "article_id": 1,
                
                
                
                "platforms": '["juejin"]',
                
                
                
                "account": "default",
                
                
                
                "draft_only": False,
                
                
                
                
                
                "message": "",
                
                
                
                "result": '{}',
                
                
                
                "error": "",
                
                
                
                "attempts": 0,
                
                
                
                "created_at": "2026-01-01T00:00:00",
                
                
                
                "updated_at": "2026-01-01T00:00:00",
                
                
                
                "finished_at": "2026-01-01T00:00:00",
                
                
            }
        }



class TaskStatusUpdate(BaseModel):
    """
    统一任务状态/标识位更新模型（专用）
    """
    
    status: str = Field(
        ...,
        max_length=20,
        
        
        description="状态(pending/running/ok/failed/waiting_human)"
    )
    

    class Config:
        extra = "forbid"
        json_schema_extra = {
            "example": {
                
                "status": "pending",
                
            }
        }



class TaskResponse(BaseModel):
    """
    统一任务响应模型
    """
    
    id: int
    
    task_id: str
    
    kind: str
    
    article_id: int | None
    
    platforms: str | None
    
    account: str | None
    
    draft_only: bool | None
    
    status: str | None
    
    message: str | None
    
    result: str | None
    
    error: str | None
    
    attempts: int | None
    
    created_at: datetime | None
    
    updated_at: datetime | None
    
    finished_at: datetime | None
    

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                
                "id": 1,
                
                "task_id": "abc1234567",
                
                "kind": "publish",
                
                "article_id": 1,
                
                "platforms": '["juejin"]',
                
                "account": "default",
                
                "draft_only": False,
                
                "status": "pending",
                
                "message": "",
                
                "result": '{}',
                
                "error": "",
                
                "attempts": 0,
                
                "created_at": "2026-01-01T00:00:00",
                
                "updated_at": "2026-01-01T00:00:00",
                
                "finished_at": "2026-01-01T00:00:00",
                
            }
        }
