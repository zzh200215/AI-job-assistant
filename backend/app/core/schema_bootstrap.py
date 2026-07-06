"""Helpers for small schema compatibility bootstraps."""

from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine


def ensure_user_role_column(engine: Engine) -> None:
    """Add tb_user.role for older databases that predate role-based routing."""
    inspector = inspect(engine)
    if "tb_user" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("tb_user")}
    if "role" in columns:
        return

    with engine.begin() as conn:
        conn.execute(
            text("ALTER TABLE tb_user ADD COLUMN role VARCHAR(20) NOT NULL DEFAULT 'candidate'")
        )


def ensure_agent_task_columns(engine: Engine) -> None:
    """Add lightweight task-center columns for older databases."""
    inspector = inspect(engine)
    if "agent_task" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("agent_task")}
    statements = []
    if "strategy_name" not in columns:
        statements.append("ALTER TABLE agent_task ADD COLUMN strategy_name VARCHAR(50)")
    if "retry_of_task_id" not in columns:
        statements.append("ALTER TABLE agent_task ADD COLUMN retry_of_task_id BIGINT")

    if not statements:
        return

    with engine.begin() as conn:
        for statement in statements:
            conn.execute(text(statement))


def ensure_agent_message_usage_columns(engine: Engine) -> None:
    """Add token/cost observability columns for older agent_message tables."""
    inspector = inspect(engine)
    if "agent_message" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("agent_message")}
    statements = []
    if "tokens_used" not in columns:
        statements.append("ALTER TABLE agent_message ADD COLUMN tokens_used INTEGER DEFAULT 0")
    if "cost_cents" not in columns:
        statements.append("ALTER TABLE agent_message ADD COLUMN cost_cents FLOAT DEFAULT 0")

    if not statements:
        return

    with engine.begin() as conn:
        for statement in statements:
            conn.execute(text(statement))
