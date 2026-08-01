"""数据库连接 + Session 工厂"""

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings

_engine_kwargs = {
    "pool_pre_ping": True,
    "pool_recycle": 3600,
    "echo": False,
}
# 内存 sqlite 必须用 StaticPool：否则每个连接都是全新空库，后台任务（SessionLocal 直连本引擎）
# 会报 "no such table"，多租户模型也无法共享表结构。生产 MySQL 不受影响。
if settings.database_url.startswith("sqlite://"):
    _engine_kwargs["poolclass"] = StaticPool
    _engine_kwargs.setdefault("connect_args", {})["check_same_thread"] = False

engine = create_engine(settings.database_url, **_engine_kwargs)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """FastAPI 依赖：每次请求一个 Session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
