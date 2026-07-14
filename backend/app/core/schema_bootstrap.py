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
        conn.execute(text("ALTER TABLE tb_user ADD COLUMN role VARCHAR(20) NOT NULL DEFAULT 'candidate'"))


def ensure_agent_message_usage_columns(engine: Engine) -> None:
    """Add tokens_used and cost_cents columns to agent_message table."""
    inspector = inspect(engine)
    if "agent_message" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("agent_message")}
    statements = []
    if "tokens_used" not in columns:
        statements.append("ALTER TABLE agent_message ADD COLUMN tokens_used INTEGER DEFAULT 0")
    if "cost_cents" not in columns:
        statements.append("ALTER TABLE agent_message ADD COLUMN cost_cents FLOAT DEFAULT 0.0")

    if not statements:
        return

    with engine.begin() as conn:
        for statement in statements:
            conn.execute(text(statement))


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


def ensure_user_profile_columns(engine: Engine) -> None:
    """Add job-seeking profile columns for tb_user."""
    inspector = inspect(engine)
    if "tb_user" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("tb_user")}
    additions = {
        "nickname": "VARCHAR(50) DEFAULT ''",
        "avatar_url": "VARCHAR(500) DEFAULT ''",
        "phone": "VARCHAR(20) DEFAULT ''",
        "bio": "TEXT",
        "expected_position": "VARCHAR(200) DEFAULT ''",
        "expected_city": "VARCHAR(200) DEFAULT ''",
        "expected_salary_min": "INTEGER DEFAULT 0",
        "expected_salary_max": "INTEGER DEFAULT 0",
        "expected_industry": "VARCHAR(200) DEFAULT ''",
        "work_years": "INTEGER DEFAULT 0",
        "education": "VARCHAR(20) DEFAULT ''",
        "current_employer": "VARCHAR(200) DEFAULT ''",
        "current_position": "VARCHAR(200) DEFAULT ''",
        "job_seeking_status": "VARCHAR(20) DEFAULT ''",
        "skill_tags": "JSON",
        "social_links": "JSON",
        "default_resume_id": "BIGINT",
        "default_target_id": "BIGINT",
        "notification_preferences": "JSON",
        "privacy_settings": "JSON",
        "language": "VARCHAR(10) DEFAULT 'zh-CN'",
        "theme": "VARCHAR(10) DEFAULT 'light'",
        "email_verified": "INTEGER NOT NULL DEFAULT 0",
    }

    statements = []
    for col_name, col_type in additions.items():
        if col_name not in columns:
            statements.append(f"ALTER TABLE tb_user ADD COLUMN {col_name} {col_type}")

    if not statements:
        return

    with engine.begin() as conn:
        for statement in statements:
            conn.execute(text(statement))


def ensure_job_bookmark_table(engine: Engine) -> None:
    """Create job_bookmark table if it does not exist."""
    inspector = inspect(engine)
    if "job_bookmark" in inspector.get_table_names():
        return

    with engine.begin() as conn:
        conn.execute(
            text("""
            CREATE TABLE job_bookmark (
                id BIGINT AUTO_INCREMENT PRIMARY KEY,
                user_id BIGINT NOT NULL,
                jd_id BIGINT NOT NULL,
                action VARCHAR(20) NOT NULL,
                note VARCHAR(500) DEFAULT '',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                INDEX ix_job_bookmark_user_id (user_id),
                INDEX ix_job_bookmark_jd_id (jd_id),
                INDEX ix_job_bookmark_action (action)
            )
        """)
        )


def ensure_notification_table(engine: Engine) -> None:
    """Create notification table if it does not exist."""
    inspector = inspect(engine)
    if "notification" in inspector.get_table_names():
        return

    with engine.begin() as conn:
        conn.execute(
            text("""
            CREATE TABLE notification (
                id BIGINT AUTO_INCREMENT PRIMARY KEY,
                user_id BIGINT NOT NULL,
                type VARCHAR(30) NOT NULL,
                title VARCHAR(200) NOT NULL,
                content TEXT,
                link VARCHAR(500) DEFAULT '',
                metadata JSON,
                is_read INTEGER DEFAULT 0,
                read_at DATETIME,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                INDEX ix_notification_user_id (user_id),
                INDEX ix_notification_type (type),
                INDEX ix_notification_is_read (is_read),
                INDEX ix_notification_created_at (created_at)
            )
        """)
        )


def ensure_interview_question_table(engine: Engine) -> None:
    """Create interview_question table if it does not exist."""
    inspector = inspect(engine)
    if "interview_question" in inspector.get_table_names():
        return

    with engine.begin() as conn:
        conn.execute(
            text("""
            CREATE TABLE interview_question (
                id BIGINT AUTO_INCREMENT PRIMARY KEY,
                category VARCHAR(30) NOT NULL,
                sub_category VARCHAR(50) DEFAULT '',
                difficulty VARCHAR(10) DEFAULT 'medium',
                question TEXT NOT NULL,
                intent VARCHAR(500) DEFAULT '',
                ref_answer TEXT,
                keywords JSON,
                tags JSON,
                source VARCHAR(50) DEFAULT 'system',
                use_count INTEGER DEFAULT 0,
                avg_score INTEGER DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                INDEX ix_interview_question_category (category),
                INDEX ix_interview_question_sub_category (sub_category),
                INDEX ix_interview_question_difficulty (difficulty)
            )
        """)
        )


def ensure_interview_evaluation_schema(engine: Engine) -> None:
    """Backfill P1 interview state columns for development databases predating Alembic."""
    inspector = inspect(engine)
    if "interview_session" in inspector.get_table_names():
        columns = {column["name"] for column in inspector.get_columns("interview_session")}
        additions = {
            "evaluation_status": "VARCHAR(20) DEFAULT 'idle'",
            "memory_snapshot": "JSON",
        }
        with engine.begin() as conn:
            for name, definition in additions.items():
                if name not in columns:
                    conn.execute(text(f"ALTER TABLE interview_session ADD COLUMN {name} {definition}"))

    if "interview_turn_evaluation" in inspector.get_table_names():
        return

    with engine.begin() as conn:
        conn.execute(
            text("""
            CREATE TABLE interview_turn_evaluation (
                id BIGINT AUTO_INCREMENT PRIMARY KEY,
                session_id BIGINT NOT NULL,
                turn_id VARCHAR(80) NOT NULL,
                question_index INTEGER NOT NULL DEFAULT 0,
                question TEXT,
                category VARCHAR(50) DEFAULT 'general',
                user_answer TEXT,
                is_follow_up INTEGER DEFAULT 0,
                status VARCHAR(20) NOT NULL DEFAULT 'pending',
                completeness INTEGER DEFAULT 0,
                accuracy INTEGER DEFAULT 0,
                depth INTEGER DEFAULT 0,
                expression INTEGER DEFAULT 0,
                overall_score INTEGER DEFAULT 0,
                feedback TEXT,
                improvement TEXT,
                evidence JSON,
                error_msg VARCHAR(500) DEFAULT '',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                completed_at DATETIME NULL,
                UNIQUE KEY uq_interview_turn_evaluation_turn (session_id, turn_id),
                INDEX ix_interview_turn_evaluation_session_id (session_id),
                INDEX ix_interview_turn_evaluation_status (status)
            )
        """)
        )


def ensure_job_journal_table(engine: Engine) -> None:
    """Create job_journal table if it does not exist."""
    inspector = inspect(engine)
    if "job_journal" in inspector.get_table_names():
        return

    with engine.begin() as conn:
        conn.execute(
            text("""
            CREATE TABLE job_journal (
                id BIGINT AUTO_INCREMENT PRIMARY KEY,
                user_id BIGINT NOT NULL,
                pipeline_id BIGINT,
                jd_id BIGINT,
                entry_type VARCHAR(20) NOT NULL,
                title VARCHAR(200) NOT NULL,
                content TEXT,
                tags JSON,
                mood VARCHAR(20) DEFAULT '',
                rating INTEGER DEFAULT 0,
                interview_role VARCHAR(100) DEFAULT '',
                interview_round INTEGER DEFAULT 0,
                interview_format VARCHAR(20) DEFAULT '',
                attachments JSON,
                is_private INTEGER DEFAULT 1,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                INDEX ix_job_journal_user_id (user_id),
                INDEX ix_job_journal_pipeline_id (pipeline_id),
                INDEX ix_job_journal_jd_id (jd_id),
                INDEX ix_job_journal_entry_type (entry_type),
                INDEX ix_job_journal_created_at (created_at)
            )
        """)
        )


def ensure_job_pipeline_columns(engine: Engine) -> None:
    """Add missing columns to job_application_pipeline for older databases."""
    inspector = inspect(engine)
    if "job_application_pipeline" not in inspector.get_table_names():
        return

    columns = {col["name"] for col in inspector.get_columns("job_application_pipeline")}
    additions = {
        "target_id": "BIGINT NULL",
        "experience_requirement": "VARCHAR(50) DEFAULT ''",
        "education_requirement": "VARCHAR(50) DEFAULT ''",
        "industry": "VARCHAR(100) DEFAULT ''",
        "skill_tags": "JSON",
        "priority_score": "INTEGER DEFAULT 0",
        "priority_label": "VARCHAR(50) DEFAULT ''",
        "note": "TEXT",
        "next_action": "VARCHAR(255) DEFAULT ''",
        "follow_up_at": "DATETIME NULL",
        "resume_name": "VARCHAR(255) DEFAULT ''",
        "stage_history": "JSON",
        "interview_at": "DATETIME NULL",
        "interview_type": "VARCHAR(20) DEFAULT ''",
        "interview_round": "INTEGER DEFAULT 0",
        "interview_location": "VARCHAR(255) DEFAULT ''",
        "interview_contact": "VARCHAR(100) DEFAULT ''",
        "offer_salary": "VARCHAR(100) DEFAULT ''",
        "offer_details": "JSON",
        "offer_deadline": "DATETIME NULL",
    }

    statements = []
    for col_name, col_type in additions.items():
        if col_name not in columns:
            statements.append(f"ALTER TABLE job_application_pipeline ADD COLUMN {col_name} {col_type}")

    if not statements:
        return

    with engine.begin() as conn:
        for statement in statements:
            conn.execute(text(statement))


def ensure_job_target_table(engine: Engine) -> None:
    """Create job_target table and add target_id to pipeline if needed."""
    inspector = inspect(engine)

    if "job_target" not in inspector.get_table_names():
        with engine.begin() as conn:
            conn.execute(
                text("""
                CREATE TABLE job_target (
                    id BIGINT AUTO_INCREMENT PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    name VARCHAR(100) NOT NULL,
                    position VARCHAR(100) DEFAULT '',
                    industry VARCHAR(50) DEFAULT '',
                    cities JSON,
                    salary_min INTEGER,
                    salary_max INTEGER,
                    skills JSON,
                    priority VARCHAR(10) DEFAULT 'medium',
                    status VARCHAR(15) DEFAULT 'active',
                    is_primary INTEGER DEFAULT 0,
                    notes TEXT,
                    config JSON,
                    application_count INTEGER DEFAULT 0,
                    interview_count INTEGER DEFAULT 0,
                    offer_count INTEGER DEFAULT 0,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    INDEX ix_job_target_user_id (user_id),
                    INDEX ix_job_target_status (status),
                    INDEX ix_job_target_is_primary (is_primary)
                )
            """)
            )

    # Add target_id column to job_application_pipeline
    if "job_application_pipeline" in inspector.get_table_names():
        columns = {col["name"] for col in inspector.get_columns("job_application_pipeline")}
        if "target_id" not in columns:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "ALTER TABLE job_application_pipeline ADD COLUMN target_id BIGINT NULL, "
                        "ADD INDEX ix_pipeline_target_id (target_id)"
                    )
                )


def ensure_resume_columns(engine: Engine) -> None:
    """Add missing columns to tb_resume for older databases."""
    inspector = inspect(engine)
    if "tb_resume" not in inspector.get_table_names():
        return

    columns = {col["name"] for col in inspector.get_columns("tb_resume")}
    additions = {
        "is_deleted": "INTEGER DEFAULT 0",
        "deleted_at": "DATETIME NULL",
        "optimized_content": "TEXT",
        "optimized_at": "DATETIME NULL",
    }

    statements = []
    for col_name, col_type in additions.items():
        if col_name not in columns:
            statements.append(f"ALTER TABLE tb_resume ADD COLUMN {col_name} {col_type}")

    if not statements:
        return

    with engine.begin() as conn:
        for statement in statements:
            conn.execute(text(statement))


def ensure_jd_columns(engine: Engine) -> None:
    """Add missing columns to tb_jd for older databases."""
    inspector = inspect(engine)
    if "tb_jd" not in inspector.get_table_names():
        return

    columns = {col["name"] for col in inspector.get_columns("tb_jd")}
    additions = {
        "source": "VARCHAR(20) DEFAULT 'manual'",
        "industry": "VARCHAR(100)",
        "is_active": "INTEGER DEFAULT 1",
        "external_url": "VARCHAR(500)",
        "external_id": "VARCHAR(100)",
        "skill_tags": "JSON",
        "education_requirement": "VARCHAR(50)",
        "experience_requirement": "VARCHAR(50)",
    }

    statements = []
    for col_name, col_type in additions.items():
        if col_name not in columns:
            statements.append(f"ALTER TABLE tb_jd ADD COLUMN {col_name} {col_type}")

    if not statements:
        return

    with engine.begin() as conn:
        for statement in statements:
            conn.execute(text(statement))


def ensure_analysis_record_columns(engine: Engine) -> None:
    """Add missing columns to tb_analysis_record for older databases."""
    inspector = inspect(engine)
    if "tb_analysis_record" not in inspector.get_table_names():
        return

    columns = {col["name"] for col in inspector.get_columns("tb_analysis_record")}
    additions = {
        "is_deleted": "INTEGER DEFAULT 0",
        "deleted_at": "DATETIME NULL",
    }

    statements = []
    for col_name, col_type in additions.items():
        if col_name not in columns:
            statements.append(f"ALTER TABLE tb_analysis_record ADD COLUMN {col_name} {col_type}")

    if not statements:
        return

    with engine.begin() as conn:
        for statement in statements:
            conn.execute(text(statement))
