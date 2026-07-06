# -*- coding: utf-8 -*-
"""岗位数据源适配器包"""
from .adapter import JobDataSourceAdapter, SourceRow
from .csv_source import CsvJobSource
from .json_source import JsonJobSource
from .mock_source import MockJobSource
from .api_source import ApiJobSource
from .arbeitnow_source import ArbeitnowJobSource
from .sync_service import SyncService, create_adapter

__all__ = [
    "JobDataSourceAdapter",
    "SourceRow",
    "CsvJobSource",
    "JsonJobSource",
    "MockJobSource",
    "ApiJobSource",
    "ArbeitnowJobSource",
    "SyncService",
    "create_adapter",
]
