"""
发布实例数据模型

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


class Publication(BaseModel):
    """
    发布实例
    """
    __tablename__ = "publication"

    
    id = Column(
        "id",
        Integer,
        primary_key=True,
        
        nullable=False,
        
        
        comment="主键ID"
    )
    
    article_id = Column(
        "article_id",
        Integer,
        
        
        nullable=False,
        
        
        comment="文章ID"
    )
    
    platform = Column(
        "platform",
        String(50),
        
        
        nullable=False,
        
        
        comment="平台"
    )
    
    account = Column(
        "account",
        String(50),
        
        
        nullable=True,
        
        default='default',
        comment="账号"
    )
    
    post_id = Column(
        "post_id",
        String(255),
        
        
        nullable=True,
        
        
        comment="平台文章ID"
    )
    
    post_url = Column(
        "post_url",
        String(1024),
        
        
        nullable=True,
        
        
        comment="文章链接"
    )
    
    edit_url = Column(
        "edit_url",
        String(1024),
        
        
        nullable=True,
        
        
        comment="编辑页链接"
    )
    
    status = Column(
        "status",
        String(20),
        
        
        nullable=True,
        
        default='pending',
        comment="状态(pending/ok/failed)"
    )
    
    draft_only = Column(
        "draft_only",
        Boolean,
        
        
        nullable=True,
        
        default=True,
        comment="仅草稿"
    )
    
    stats = Column(
        "stats",
        Text,
        
        
        nullable=True,
        
        default='{}',
        comment="阅读点赞等JSON"
    )
    
    last_error = Column(
        "last_error",
        Text,
        
        
        nullable=True,
        
        
        comment="错误信息"
    )
    
    content_hash = Column(
        "content_hash",
        String(128),
        
        
        nullable=True,
        
        
        comment="内容指纹"
    )
    
    published_at = Column(
        "published_at",
        DateTime,
        
        
        nullable=True,
        
        
        comment="发布时间"
    )
    
    updated_at = Column(
        "updated_at",
        DateTime,
        
        
        nullable=True,
        
        default=func.now(),
        comment="更新时间"
    )
    

    

    
