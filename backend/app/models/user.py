# -*- coding: utf-8 -*-
"""用户 ORM 模型。"""
from sqlalchemy import BigInteger, Column, DateTime, String

from app.core.database import Base
from app.core.user_roles import CANDIDATE_ROLE
from app.utils.time_helper import utc_now


class User(Base):
    __tablename__ = "tb_user"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    username = Column(String(50), nullable=False, unique=True)
    password = Column(String(255), nullable=False)
    email = Column(String(100), unique=True)
    role = Column(String(20), nullable=False, default=CANDIDATE_ROLE, server_default=CANDIDATE_ROLE)
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)
