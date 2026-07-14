"""Tests for structured logging configuration."""

from __future__ import annotations

import logging

import pytest

from app.core.logging_utils import (
    RequestContextFilter,
    clear_logging_context,
    set_logging_context,
)
from app.core.request_context import get_request_id, set_request_id


@pytest.fixture(autouse=True)
def reset_context():
    """Reset request and logging context after each test."""
    yield
    set_request_id(None)
    clear_logging_context()


def test_request_context_filter_adds_fields():
    """Verify RequestContextFilter adds request_id and user_id to log records."""
    filter_instance = RequestContextFilter()
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="test.py",
        lineno=1,
        msg="Test message",
        args=(),
        exc_info=None,
    )

    set_request_id("test-req-123")
    set_logging_context("user_id", "42")

    result = filter_instance.filter(record)

    assert result is True
    assert record.request_id == "test-req-123"
    assert record.user_id == "42"


def test_request_context_filter_handles_missing_values():
    """Verify RequestContextFilter handles missing request_id and user_id."""
    filter_instance = RequestContextFilter()
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="test.py",
        lineno=1,
        msg="Test message",
        args=(),
        exc_info=None,
    )

    # Don't set any context
    result = filter_instance.filter(record)

    assert result is True
    assert record.request_id == "-"
    assert record.user_id == "-"


def test_context_isolation_between_requests():
    """Verify context is properly isolated and cleared."""
    set_request_id("req-1")
    set_logging_context("user_id", "1")
    assert get_request_id() == "req-1"

    clear_logging_context()
    set_request_id("req-2")
    set_logging_context("user_id", "2")

    assert get_request_id() == "req-2"

    set_request_id(None)
    assert get_request_id() is None
