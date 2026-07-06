# -*- coding: utf-8 -*-
"""动态岗位数据源模型"""
from sqlalchemy import (
    Column, BigInteger, String, Integer, DateTime, Text, JSON, Enum
)
from app.core.database import Base
from app.utils.time_helper import utc_now


class JobDataSource(Base):
    """岗位数据源配置表"""
    __tablename__ = "job_data_source"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, default=None, index=True, comment="所属用户")
    name = Column(String(100), nullable=False, comment="数据源名称")
    source_type = Column(String(20), nullable=False, comment="类型: csv/json/api/mock")
    config = Column(JSON, default=dict, comment="连接配置(JSON)")
    status = Column(Integer, default=1, comment="状态: 0-禁用 1-启用")
    last_sync_at = Column(DateTime, nullable=True, comment="上次同步时间")
    last_sync_log_id = Column(BigInteger, nullable=True, comment="上次同步日志ID")
    sync_interval = Column(Integer, default=0, comment="自动同步间隔(分钟), 0=手动")
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)


class JobSyncLog(Base):
    """同步日志表"""
    __tablename__ = "job_sync_log"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    source_id = Column(BigInteger, nullable=False, index=True, comment="数据源ID")
    user_id = Column(BigInteger, default=None, index=True)
    status = Column(String(20), default="running", comment="状态: running/success/failed/partial")
    total_count = Column(Integer, default=0, comment="读取总数")
    success_count = Column(Integer, default=0, comment="成功写入数")
    fail_count = Column(Integer, default=0, comment="失败数")
    duplicate_count = Column(Integer, default=0, comment="去重跳过数")
    embed_count = Column(Integer, default=0, comment="生成向量数")
    duration_ms = Column(Integer, default=0, comment="耗时(毫秒)")
    error_msg = Column(Text, nullable=True, comment="错误信息")
    detail = Column(JSON, default=list, comment="明细错误列表")
    started_at = Column(DateTime, default=utc_now)
    finished_at = Column(DateTime, nullable=True)


class JobImportBatch(Base):
    """导入批次记录（用于去重和溯源）"""
    __tablename__ = "job_import_batch"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    source_id = Column(BigInteger, nullable=False, index=True)
    sync_log_id = Column(BigInteger, nullable=False, index=True)
    user_id = Column(BigInteger, default=None, index=True)
    external_id = Column(String(100), index=True, comment="外部唯一标识")
    title = Column(String(200), nullable=False)
    company = Column(String(200))
    location = Column(String(100))
    jd_id = Column(BigInteger, nullable=True, comment="关联 tb_jd.id")
    status = Column(String(20), default="pending", comment="pending/success/failed")
    error_msg = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utc_now)
