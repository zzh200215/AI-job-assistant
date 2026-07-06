# -*- coding: utf-8 -*-
"""时间工具 — 统一替换 datetime.utcnow() 的 deprecated 用法

Python 3.12 起 datetime.utcnow() 已废弃，应使用 datetime.now(timezone.utc)。
本模块提供统一的 utc_now() 封装，避免各处重复 import timezone。
"""
from datetime import datetime, timezone


def utc_now() -> datetime:
    """获取当前 UTC 时间（带 tzinfo）"""
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    """获取当前 UTC 时间的 ISO 格式字符串"""
    return datetime.now(timezone.utc).isoformat()
