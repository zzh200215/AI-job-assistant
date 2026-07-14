"""Shared pytest fixtures."""

from __future__ import annotations

import os
from collections.abc import Generator

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

# Use in-memory SQLite for tests to avoid requiring a running MySQL instance.
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["REDIS_URL"] = ""

import contextlib

from app.core.database import Base
from app.core.database import SessionLocal as AppSessionLocal
from app.core.rate_limiter import get_limiter
from app.core.security import hash_password
from app.core.user_roles import ADMIN_ROLE, CANDIDATE_ROLE
from app.models.user import User
from app.services.embedding_service import set_embedding_stats_session_factory


def _sqlite_engine():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    return engine


@pytest.fixture(scope="session")
def db_engine():
    engine = _sqlite_engine()
    Base.metadata.create_all(bind=engine)
    yield engine
    engine.dispose()


@pytest.fixture(scope="function")
def db_session(db_engine) -> Generator[Session, None, None]:
    """Provide a transactional database session that rolls back after each test."""
    connection = db_engine.connect()
    transaction = connection.begin()
    session_factory = sessionmaker(bind=connection)
    session = session_factory()
    set_embedding_stats_session_factory(session_factory)

    # Ensure nested transactions use the same connection.
    nested = connection.begin_nested()

    @event.listens_for(session, "after_transaction_end")
    def end_savepoint(db_session, transaction):
        nonlocal nested
        if not nested.is_active:
            nested = connection.begin_nested()

    yield session

    set_embedding_stats_session_factory(AppSessionLocal)
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def override_db(db_session):
    """Override FastAPI's get_db dependency with the test session."""

    def _get_db():
        yield db_session

    return _get_db


@pytest.fixture
def normal_user(db_session: Session):
    user = User(
        username="normal_user",
        email="normal@example.com",
        password=hash_password("NormalPass123!"),
        role=CANDIDATE_ROLE,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def admin_user(db_session: Session):
    user = User(
        username="admin_user",
        email="admin@example.com",
        password=hash_password("AdminPass123!"),
        role=ADMIN_ROLE,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    """Keep slowapi's in-memory counters isolated between tests."""
    limiter = get_limiter()
    with contextlib.suppress(Exception):
        limiter.reset()
    yield
    with contextlib.suppress(Exception):
        limiter.reset()
