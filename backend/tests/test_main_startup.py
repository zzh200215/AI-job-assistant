import importlib
import sys


def test_importing_main_does_not_create_tables(monkeypatch):
    import app.core.database as database_module

    calls = []

    def fake_create_all(*args, **kwargs):
        calls.append((args, kwargs))

    monkeypatch.setattr(database_module.Base.metadata, "create_all", fake_create_all)
    sys.modules.pop("app.main", None)

    try:
        importlib.import_module("app.main")
    finally:
        sys.modules.pop("app.main", None)

    assert calls == []
