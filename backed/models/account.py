"""
平台账号数据模型

此文件由 SQL-to-FastAPI-Scaffold 自动生成
"""

from datetime import datetime
from sqlalchemy import (
    Column, String, Integer, BigInteger, Boolean,
    DateTime, Date, Time, Text, Numeric, Float, JSON,
    ForeignKey
)
from sqlalchemy.orm import relationship
from models.base import BaseModel


class Account(BaseModel):
    """
    平台账号
    """
    __tablename__ = "account"

    
    id = Column(
        "id",
        Integer,
        primary_key=True,
        
        nullable=False,
        
        
        comment="主键ID"
    )
    
    platform = Column(
        "platform",
        String(50),
        
        
        nullable=False,
        
        
        comment="平台"
    )
    
    name = Column(
        "name",
        String(50),
        
        
        nullable=True,
        
        default='default',
        comment="账号名"
    )
    
    profile_dir = Column(
        "profile_dir",
        String(512),
        
        
        nullable=False,
        
        
        comment="浏览器profile目录"
    )
    
    status = Column(
        "status",
        String(20),
        
        
        nullable=True,
        
        default='unknown',
        comment="状态(unknown/logined/offline)"
    )
    
    last_check = Column(
        "last_check",
        DateTime,
        
        
        nullable=True,
        
        
        comment="上次检查时间"
    )
    

    

    
