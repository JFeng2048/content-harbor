"""
统一任务数据模型

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


class Task(BaseModel):
    """
    统一任务
    """
    __tablename__ = "task"

    
    id = Column(
        "id",
        Integer,
        primary_key=True,
        
        nullable=False,
        
        
        comment="主键ID"
    )
    
    task_id = Column(
        "task_id",
        String(20),
        
        
        nullable=False,
        unique=True,
        
        comment="短任务ID"
    )
    
    kind = Column(
        "kind",
        String(20),
        
        
        nullable=False,
        
        
        comment="类型(publish/update/sync/refresh/login/assist)"
    )
    
    article_id = Column(
        "article_id",
        Integer,
        
        
        nullable=True,
        
        
        comment="文章ID"
    )
    
    platforms = Column(
        "platforms",
        Text,
        
        
        nullable=True,
        
        default='[]',
        comment="平台列表JSON"
    )
    
    account = Column(
        "account",
        String(50),
        
        
        nullable=True,
        
        default='default',
        comment="账号"
    )
    
    draft_only = Column(
        "draft_only",
        Boolean,
        
        
        nullable=True,
        
        default=False,
        comment="仅草稿"
    )
    
    status = Column(
        "status",
        String(20),
        
        
        nullable=True,
        
        default='pending',
        comment="状态(pending/running/ok/failed/waiting_human)"
    )
    
    message = Column(
        "message",
        Text,
        
        
        nullable=True,
        
        
        comment="消息"
    )
    
    result = Column(
        "result",
        Text,
        
        
        nullable=True,
        
        default='{}',
        comment="结果JSON"
    )
    
    error = Column(
        "error",
        Text,
        
        
        nullable=True,
        
        
        comment="错误"
    )
    
    attempts = Column(
        "attempts",
        Integer,
        
        
        nullable=True,
        
        default=0,
        comment="尝试次数"
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
    
    finished_at = Column(
        "finished_at",
        DateTime,
        
        
        nullable=True,
        
        
        comment="完成时间"
    )
    

    

    
