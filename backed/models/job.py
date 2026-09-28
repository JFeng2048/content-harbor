"""
任务流水数据模型

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


class Job(BaseModel):
    """
    任务流水
    """
    __tablename__ = "job"

    
    id = Column(
        "id",
        Integer,
        primary_key=True,
        
        nullable=False,
        
        
        comment="主键ID"
    )
    
    type = Column(
        "type",
        String(20),
        
        
        nullable=False,
        
        
        comment="类型(publish/update/sync/import)"
    )
    
    article_id = Column(
        "article_id",
        Integer,
        
        
        nullable=True,
        
        
        comment="文章ID"
    )
    
    platform = Column(
        "platform",
        String(50),
        
        
        nullable=True,
        
        
        comment="平台"
    )
    
    status = Column(
        "status",
        String(20),
        
        
        nullable=True,
        
        default='running',
        comment="状态(running/ok/failed)"
    )
    
    message = Column(
        "message",
        Text,
        
        
        nullable=True,
        
        
        comment="消息"
    )
    
    created_at = Column(
        "created_at",
        DateTime,
        
        
        nullable=True,
        
        default=func.now(),
        comment="创建时间"
    )
    
    finished_at = Column(
        "finished_at",
        DateTime,
        
        
        nullable=True,
        
        
        comment="完成时间"
    )
    

    

    
