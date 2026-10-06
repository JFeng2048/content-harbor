"""
发布实例数据验证模型

此文件由 SQL-to-FastAPI-Scaffold 自动生成
"""

from typing import Optional
from datetime import datetime, date, time
from decimal import Decimal
from pydantic import BaseModel, ConfigDict, Field, field_validator


class PublicationBase(BaseModel):
    """
    发布实例基础模型
    """
    
    article_id: int = Field(
        ...,
        
        
        
        description="文章ID"
    )
    
    platform: str = Field(
        ...,
        max_length=50,
        
        
        description="平台"
    )
    
    account: str | None = Field(
        None,
        max_length=50,
        
        
        description="账号"
    )
    
    post_id: str | None = Field(
        None,
        max_length=255,
        
        
        description="平台文章ID"
    )
    
    post_url: str | None = Field(
        None,
        max_length=1024,
        
        
        description="文章链接"
    )
    
    edit_url: str | None = Field(
        None,
        max_length=1024,
        
        
        description="编辑页链接"
    )
    
    status: str | None = Field(
        None,
        max_length=20,
        
        
        description="状态(pending/ok/failed)"
    )
    
    draft_only: bool | None = Field(
        None,
        
        
        
        description="仅草稿"
    )
    
    stats: str | None = Field(
        None,
        
        
        
        description="阅读点赞等JSON"
    )
    
    last_error: str | None = Field(
        None,
        
        
        
        description="错误信息"
    )
    
    content_hash: str | None = Field(
        None,
        max_length=128,
        
        
        description="内容指纹"
    )
    
    published_at: datetime | None = Field(
        None,
        
        
        
        description="发布时间"
    )
    
    updated_at: datetime | None = Field(
        None,
        
        
        
        description="更新时间"
    )
    

    


class PublicationCreate(PublicationBase):
    """
    发布实例创建模型
    """
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                
                "article_id": 1,
                
                "platform": "juejin",
                
                "account": "default",
                
                "post_id": "12345",
                
                "post_url": "https://x/123",
                
                "edit_url": "https://x/edit",
                
                "status": "pending",
                
                "draft_only": True,
                
                "stats": '{}',
                
                "last_error": "",
                
                "content_hash": "abc",
                
                "published_at": "2026-01-01T00:00:00",
                
                "updated_at": "2026-01-01T00:00:00",
                
            }
        }
    )


class PublicationUpdate(BaseModel):
    """
    发布实例更新模型

    注意：状态/标识位字段不在此模型中，请使用专用改状态接口。
    """
    
    
    article_id: int | None = Field(
        default=None,
        
        
        
        description="文章ID"
    )
    
    
    
    platform: str | None = Field(
        default=None,
        max_length=50,
        
        
        description="平台"
    )
    
    
    
    account: str | None = Field(
        default=None,
        max_length=50,
        
        
        description="账号"
    )
    
    
    
    post_id: str | None = Field(
        default=None,
        max_length=255,
        
        
        description="平台文章ID"
    )
    
    
    
    post_url: str | None = Field(
        default=None,
        max_length=1024,
        
        
        description="文章链接"
    )
    
    
    
    edit_url: str | None = Field(
        default=None,
        max_length=1024,
        
        
        description="编辑页链接"
    )
    
    
    
    
    
    draft_only: bool | None = Field(
        default=None,
        
        
        
        description="仅草稿"
    )
    
    
    
    stats: str | None = Field(
        default=None,
        
        
        
        description="阅读点赞等JSON"
    )
    
    
    
    last_error: str | None = Field(
        default=None,
        
        
        
        description="错误信息"
    )
    
    
    
    content_hash: str | None = Field(
        default=None,
        max_length=128,
        
        
        description="内容指纹"
    )
    
    
    
    published_at: datetime | None = Field(
        default=None,
        
        
        
        description="发布时间"
    )
    
    
    
    updated_at: datetime | None = Field(
        default=None,
        
        
        
        description="更新时间"
    )
    
    

    class Config:
        extra = "forbid"
        json_schema_extra = {
            "example": {
                
                
                "article_id": 1,
                
                
                
                "platform": "juejin",
                
                
                
                "account": "default",
                
                
                
                "post_id": "12345",
                
                
                
                "post_url": "https://x/123",
                
                
                
                "edit_url": "https://x/edit",
                
                
                
                
                
                "draft_only": True,
                
                
                
                "stats": '{}',
                
                
                
                "last_error": "",
                
                
                
                "content_hash": "abc",
                
                
                
                "published_at": "2026-01-01T00:00:00",
                
                
                
                "updated_at": "2026-01-01T00:00:00",
                
                
            }
        }



class PublicationStatusUpdate(BaseModel):
    """
    发布实例状态/标识位更新模型（专用）
    """
    
    status: str = Field(
        ...,
        max_length=20,
        
        
        description="状态(pending/ok/failed)"
    )
    

    class Config:
        extra = "forbid"
        json_schema_extra = {
            "example": {
                
                "status": "pending",
                
            }
        }



class PublicationResponse(BaseModel):
    """
    发布实例响应模型
    """
    
    id: int
    
    article_id: int
    
    platform: str
    
    account: str | None
    
    post_id: str | None
    
    post_url: str | None
    
    edit_url: str | None
    
    status: str | None
    
    draft_only: bool | None
    
    stats: str | None
    
    last_error: str | None
    
    content_hash: str | None
    
    published_at: datetime | None
    
    updated_at: datetime | None
    

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                
                "id": 1,
                
                "article_id": 1,
                
                "platform": "juejin",
                
                "account": "default",
                
                "post_id": "12345",
                
                "post_url": "https://x/123",
                
                "edit_url": "https://x/edit",
                
                "status": "pending",
                
                "draft_only": True,
                
                "stats": '{}',
                
                "last_error": "",
                
                "content_hash": "abc",
                
                "published_at": "2026-01-01T00:00:00",
                
                "updated_at": "2026-01-01T00:00:00",
                
            }
        }
