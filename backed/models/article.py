"""
文章数据模型

此文件由 SQL-to-FastAPI-Scaffold 自动生成
"""

from datetime import datetime
from sqlalchemy import (
    Column, String, Integer, BigInteger, Boolean,
    DateTime, Date, Time, Text, Numeric, Float, JSON,
    ForeignKey
)
from sqlalchemy import func
from sqlalchemy.orm import relationship
from models.base import BaseModel


class Article(BaseModel):
    """
    文章
    """
    __tablename__ = "article"

    
    id = Column(
        "id",
        Integer,
        primary_key=True,
        
        nullable=False,
        
        
        comment="文章ID"
    )
    
    title = Column(
        "title",
        String(512),
        
        
        nullable=False,
        
        
        comment="标题"
    )
    
    content_md = Column(
        "content_md",
        Text,
        
        
        nullable=False,
        
        
        comment="Markdown正文"
    )
    
    summary = Column(
        "summary",
        Text,
        
        
        nullable=True,
        
        
        comment="摘要"
    )
    
    tags = Column(
        "tags",
        String(255),
        
        
        nullable=True,
        
        
        comment="标签(逗号分隔)"
    )
    
    cover = Column(
        "cover",
        String(512),
        
        
        nullable=True,
        
        
        comment="封面图URL"
    )
    
    status = Column(
        "status",
        String(20),
        
        
        nullable=True,
        
        default='draft',
        comment="状态(draft/review/published/archived)"
    )
    
    source = Column(
        "source",
        String(20),
        
        
        nullable=True,
        
        default='human',
        comment="来源(human/ai/import)"
    )
    
    ai_model = Column(
        "ai_model",
        String(100),
        
        
        nullable=True,
        
        
        comment="AI模型"
    )
    
    origin_url = Column(
        "origin_url",
        String(512),
        
        
        nullable=True,
        
        
        comment="导入来源URL"
    )
    
    ext = Column(
        "ext",
        Text,
        
        
        nullable=True,
        
        default='{}',
        comment="扩展字段JSON"
    )
    
    created_at = Column(
        "created_at",
        DateTime,
        
        
        nullable=True,
        
        default=func.now(),
        comment="创建时间"
    )
    
    updated_at = Column(
        "updated_at",
        DateTime,
        
        
        nullable=True,
        
        default=func.now(),
        comment="更新时间"
    )
    

    

    
