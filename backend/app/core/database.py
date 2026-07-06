# -*- coding: utf-8 -*-
"""数据库连接 + Session 工厂"""
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from app.core.config import settings


engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_recycle=3600,
    echo=False,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """FastAPI 依赖：每次请求一个 Session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
