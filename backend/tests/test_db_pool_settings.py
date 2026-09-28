"""连接池三个数必须真的传到引擎上（E27）。

§8 那行"连接池未配置"的前半（`pool_pre_ping`/`pool_recycle` 其实一直设着）E15 已经更正过，
这次补的是后半：`pool_size`/`max_overflow`/`pool_timeout` 以前完全没设，跑的是 SQLAlchemy 默认的
5 + 10 = 15 根、排队 30 秒 —— 而 E16 之后每条面试 WS 独占一根，那个隐式上限就是真实吞吐上限。
"""

from __future__ import annotations

import pytest

from app.core.config import settings
from app.core.database import engine_kwargs_for

MYSQL_URL = "mysql+pymysql://u:p@127.0.0.1:3306/db?charset=utf8mb4"


def test_pool_sizing_reaches_the_mysql_engine():
    kwargs = engine_kwargs_for(MYSQL_URL)

    assert kwargs["pool_size"] == settings.DB_POOL_SIZE
    assert kwargs["max_overflow"] == settings.DB_MAX_OVERFLOW
    assert kwargs["pool_timeout"] == settings.DB_POOL_TIMEOUT
    assert kwargs["pool_pre_ping"] is True and kwargs["pool_recycle"] == 3600


def test_sqlite_keeps_static_pool_and_no_sizing_kwargs():
    """StaticPool 不接 `pool_size` 这些关键字，传了就是 `create_engine` 直接报错 —— 所以这块必须分开。"""
    kwargs = engine_kwargs_for("sqlite://")

    assert "pool_size" not in kwargs and "max_overflow" not in kwargs and "pool_timeout" not in kwargs
    from sqlalchemy.pool import StaticPool

    assert kwargs["poolclass"] is StaticPool
    assert kwargs["connect_args"]["check_same_thread"] is False


@pytest.mark.parametrize(
    ("pool_size", "overflow", "timeout"),
    [(10, 10, 30), (25, 5, 45), (1, 0, 1)],
)
def test_configured_numbers_are_what_the_engine_gets(monkeypatch, pool_size, overflow, timeout):
    """换配置就得换到参数上：钉的是"读设置"，不是读到我抄的那三个默认值。"""
    monkeypatch.setattr(settings, "DB_POOL_SIZE", pool_size)
    monkeypatch.setattr(settings, "DB_MAX_OVERFLOW", overflow)
    monkeypatch.setattr(settings, "DB_POOL_TIMEOUT", timeout)

    kwargs = engine_kwargs_for(MYSQL_URL)

    assert (kwargs["pool_size"], kwargs["max_overflow"], kwargs["pool_timeout"]) == (pool_size, overflow, timeout)


def test_garbage_settings_cannot_produce_a_dead_pool(monkeypatch):
    """0 或负数会把池子设成"一根都不给"或"排队 0 秒"，这类值必须被夹到可用区间。"""
    monkeypatch.setattr(settings, "DB_POOL_SIZE", 0)
    monkeypatch.setattr(settings, "DB_MAX_OVERFLOW", -5)
    monkeypatch.setattr(settings, "DB_POOL_TIMEOUT", 0)

    kwargs = engine_kwargs_for(MYSQL_URL)

    assert kwargs["pool_size"] == 1
    assert kwargs["max_overflow"] == 0
    assert kwargs["pool_timeout"] == 1


def test_the_defaults_leave_room_for_http_alongside_the_ws_cap():
    """E16 的 WS 上限是照池子算的（12 留 8 根给 HTTP）。这两个数一旦被人各改各的就会互相咬，
    所以把它们的关系写成断言而不是注释。"""
    capacity = settings.DB_POOL_SIZE + settings.DB_MAX_OVERFLOW

    assert capacity >= 15, f"池子总容量 {capacity} 比改动前的隐式 15 还小"
    assert (
        capacity - settings.WS_MAX_LIVE_INTERVIEWS >= 5
    ), f"WS 占 {settings.WS_MAX_LIVE_INTERVIEWS} 根后只剩 {capacity - settings.WS_MAX_LIVE_INTERVIEWS} 根给 HTTP"
