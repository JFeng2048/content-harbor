"""
文章数据验证模型

此文件由 SQL-to-FastAPI-Scaffold 自动生成
"""

from typing import Optional
from datetime import datetime, date, time
from decimal import Decimal
from pydantic import BaseModel, ConfigDict, Field, field_validator


class ArticleBase(BaseModel):
    """
    文章基础模型
    """
    
    title: str = Field(
        ...,
        
        
        
        description="标题"
    )
    
    content_md: str = Field(
        ...,
        
        
        
        description="Markdown正文"
    )
    
    summary: str | None = Field(
        None,
        
        
        
        description="摘要"
    )
    
    tags: str | None = Field(
        None,
        max_length=255,
        
        
        description="标签(逗号分隔)"
    )
    
    cover: str | None = Field(
        None,
        max_length=512,
        
        
        description="封面图URL"
    )
    
    status: str | None = Field(
        None,
        max_length=20,
        
        
        description="状态(draft/review/published/archived)"
    )
    
    source: str | None = Field(
        None,
        max_length=20,
        
        
        description="来源(human/ai/import)"
    )
    
    ai_model: str | None = Field(
        None,
        max_length=100,
        
        
        description="AI模型"
    )
    
    origin_url: str | None = Field(
        None,
        max_length=512,
        
        
        description="导入来源URL"
    )
    
    ext: str | None = Field(
        None,
        
        
        
        description="扩展字段JSON"
    )
    
    created_at: datetime | None = Field(
        None,
        
        
        
        description="创建时间"
    )
    
    updated_at: datetime | None = Field(
        None,
        
        
        
        description="更新时间"
    )
    

    


class ArticleCreate(ArticleBase):
    """
    文章创建模型
    """
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                
                "title": "示例文章标题",
                
                "content_md": "# 内容",
                
                "summary": "摘要",
                
                "tags": "AI,Python",
                
                "cover": "https://x/y.png",
                
                "status": "draft",
                
                "source": "human",
                
                "ai_model": "deepseek-chat",
                
                "origin_url": "https://x",
                
                "ext": '{}',
                
                "created_at": "2026-01-01T00:00:00",
                
                "updated_at": "2026-01-01T00:00:00",
                
            }
        }
    )


class ArticleUpdate(BaseModel):
    """
    文章更新模型

    注意：状态/标识位字段不在此模型中，请使用专用改状态接口。
    """
    
    
    title: str | None = Field(
        default=None,
        
        
        
        description="标题"
    )
    
    
    
    content_md: str | None = Field(
        default=None,
        
        
        
        description="Markdown正文"
    )
    
    
    
    summary: str | None = Field(
        default=None,
        
        
        
        description="摘要"
    )
    
    
    
    tags: str | None = Field(
        default=None,
        max_length=255,
        
        
        description="标签(逗号分隔)"
    )
    
    
    
    cover: str | None = Field(
        default=None,
        max_length=512,
        
        
        description="封面图URL"
    )
    
    
    
    
    
    source: str | None = Field(
        default=None,
        max_length=20,
        
        
        description="来源(human/ai/import)"
    )
    
    
    
    ai_model: str | None = Field(
        default=None,
        max_length=100,
        
        
        description="AI模型"
    )
    
    
    
    origin_url: str | None = Field(
        default=None,
        max_length=512,
        
        
        description="导入来源URL"
    )
    
    
    
    ext: str | None = Field(
        default=None,
        
        
        
        description="扩展字段JSON"
    )
    
    
    
    created_at: datetime | None = Field(
        default=None,
        
        
        
        description="创建时间"
    )
    
    
    
    updated_at: datetime | None = Field(
        default=None,
        
        
        
        description="更新时间"
    )
    
    

    class Config:
        extra = "forbid"
        json_schema_extra = {
            "example": {
                
                
                "title": "示例文章标题",
                
                
                
                "content_md": "# 内容",
                
                
                
                "summary": "摘要",
                
                
                
                "tags": "AI,Python",
                
                
                
                "cover": "https://x/y.png",
                
                
                
                
                
                "source": "human",
                
                
                
                "ai_model": "deepseek-chat",
                
                
                
                "origin_url": "https://x",
                
                
                
                "ext": '{}',
                
                
                
                "created_at": "2026-01-01T00:00:00",
                
                
                
                "updated_at": "2026-01-01T00:00:00",
                
                
            }
        }



class ArticleStatusUpdate(BaseModel):
    """
    文章状态/标识位更新模型（专用）
    """
    
    status: str = Field(
        ...,
        max_length=20,
        
        
        description="状态(draft/review/published/archived)"
    )
    

    class Config:
        extra = "forbid"
        json_schema_extra = {
            "example": {
                
                "status": "draft",
                
            }
        }



class ArticleResponse(BaseModel):
    """
    文章响应模型
    """
    
    id: int
    
    title: str
    
    content_md: str
    
    summary: str | None
    
    tags: str | None
    
    cover: str | None
    
    status: str | None
    
    source: str | None
    
    ai_model: str | None
    
    origin_url: str | None
    
    ext: str | None
    
    created_at: datetime | None
    
    updated_at: datetime | None
    

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                
                "id": 1,
                
                "title": "示例文章标题",
                
                "content_md": "# 内容",
                
                "summary": "摘要",
                
                "tags": "AI,Python",
                
                "cover": "https://x/y.png",
                
                "status": "draft",
                
                "source": "human",
                
                "ai_model": "deepseek-chat",
                
                "origin_url": "https://x",
                
                "ext": '{}',
                
                "created_at": "2026-01-01T00:00:00",
                
                "updated_at": "2026-01-01T00:00:00",
                
            }
        }
