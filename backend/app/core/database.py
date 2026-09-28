"""数据库连接 + Session 工厂"""

from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings


def engine_kwargs_for(database_url: str) -> dict[str, Any]:
    """按 URL 造 `create_engine` 的参数。

    抽成纯函数是因为"参数到底传没传进去"这件事只有在这里能测：连接池尺寸对内存 sqlite 是
    **不能传**的（StaticPool 不接这些关键字），而生产 MySQL 必须传 —— 之前一直是 SQLAlchemy 的
    默认 5+10，E16 把面试 WS 的上限定在 12 就是照那个隐式上限算的，不能让这个数字继续只活在注释里。
    """
    kwargs: dict[str, Any] = {
        "pool_pre_ping": True,
        "pool_recycle": 3600,
        "echo": False,
    }
    if database_url.startswith("sqlite://"):
        # 内存 sqlite 必须用 StaticPool：否则每个连接都是全新空库，后台任务（SessionLocal 直连本引擎）
        # 会报 "no such table"，多租户模型也无法共享表结构。生产 MySQL 不受影响。
        kwargs["poolclass"] = StaticPool
        kwargs.setdefault("connect_args", {})["check_same_thread"] = False
        return kwargs
    kwargs["pool_size"] = max(1, int(settings.DB_POOL_SIZE))
    kwargs["max_overflow"] = max(0, int(settings.DB_MAX_OVERFLOW))
    kwargs["pool_timeout"] = max(1, int(settings.DB_POOL_TIMEOUT))
    return kwargs


engine = create_engine(settings.database_url, **engine_kwargs_for(settings.database_url))

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """FastAPI 依赖：每次请求一个 Session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
