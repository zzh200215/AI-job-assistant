# -*- coding: utf-8 -*-
"""Embedding usage daily aggregate model."""
from sqlalchemy import BigInteger, Column, Date, DateTime, Integer, String, UniqueConstraint

from app.core.database import Base
from app.utils.time_helper import utc_now


class EmbeddingUsageDaily(Base):
    __tablename__ = "embedding_usage_daily"
    __table_args__ = (
        UniqueConstraint("stat_date", "provider", "model", name="uq_embedding_usage_daily"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    stat_date = Column(Date, nullable=False, index=True)
    provider = Column(String(50), nullable=False, index=True)
    model = Column(String(100), nullable=False, index=True)
    total_calls = Column(Integer, nullable=False, default=0)
    total_texts = Column(Integer, nullable=False, default=0)
    cache_hits = Column(Integer, nullable=False, default=0)
    cache_misses = Column(Integer, nullable=False, default=0)
    network_batches = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)
