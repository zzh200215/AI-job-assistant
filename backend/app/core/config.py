# -*- coding: utf-8 -*-
"""Centralized application settings."""
from __future__ import annotations

from typing import List, Optional

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEFAULT_JWT_SECRET = "dev-jwt-secret-change-me-before-production-1234"
_WEAK_DB_PASSWORDS = {"", "root", "123456", "password"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    APP_ENV: str = "development"
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000
    APP_DEBUG: bool = False
    LOG_LEVEL: str = "INFO"
    AUTO_CREATE_TABLES: bool = True

    CORS_ORIGINS: str = ""
    ADMIN_USERNAMES: str = "admin"

    MYSQL_HOST: str = "127.0.0.1"
    MYSQL_PORT: int = 3306
    MYSQL_USER: str = "root"
    MYSQL_PASSWORD: str = ""
    MYSQL_DB: str = "llmXM"
    DATABASE_URL: Optional[str] = None

    UPLOAD_DIR: str = "uploads"
    MAX_UPLOAD_MB: int = 10

    LLM_PROVIDER: str = "mock"
    LLM_API_KEY: Optional[str] = None
    LLM_BASE_URL: Optional[str] = None
    LLM_MODEL: str = "gpt-3.5-turbo"
    LLM_TIMEOUT: int = 60
    LLM_FALLBACK_MODEL: Optional[str] = None
    LLM_ALLOW_MOCK_FALLBACK: bool = False
    LLM_INPUT_COST_PER_1K_CENTS: float = 0.0
    LLM_OUTPUT_COST_PER_1K_CENTS: float = 0.0

    ORCHESTRATION_STRATEGY: str = "linear"
    ORCHESTRATION_ENGINE: str = "native"
    ORCHESTRATION_BACKEND: str = "thread"
    ORCHESTRATION_MAX_WORKERS: int = 4
    ORCHESTRATION_STALE_TASK_MINUTES: int = 30
    ORCHESTRATION_QUEUE_NAME: str = "analysis-tasks"
    ORCHESTRATION_QUEUE_POLL_SECONDS: float = 1.0
    REDIS_URL: Optional[str] = None

    EMBEDDING_PROVIDER: str = "mock"
    EMBEDDING_API_KEY: Optional[str] = None
    EMBEDDING_BASE_URL: Optional[str] = None
    EMBEDDING_MODEL: str = "text-embedding-v3"
    EMBEDDING_TIMEOUT: int = 30
    EMBEDDING_MAX_RETRIES: int = 2

    RERANKER_PROVIDER: str = "auto"
    RERANKER_MODEL_PATH: Optional[str] = None
    RERANKER_BATCH_SIZE: int = 8

    JWT_SECRET: str = _DEFAULT_JWT_SECRET
    JWT_ACCESS_TOKEN_EXPIRE_DAYS: int = 7

    BCRYPT_ROUNDS: int = 12

    STRUCTURED_LOGS: bool = False
    RUN_SCHEDULER: bool = True

    # Rate limiting (slowapi). Empty/unset falls back to code defaults.
    RATE_LIMIT_GENERAL: Optional[str] = None
    RATE_LIMIT_AUTH: Optional[str] = None
    RATE_LIMIT_LOGIN: Optional[str] = None

    # Backup retention
    BACKUP_KEEP_DAYS: int = 7

    RAG_TOP_K: int = 5
    RAG_CHUNK_SIZE: int = 500
    RAG_CHUNK_OVERLAP: int = 50
    # Chroma 距离阈值：score(=distance) > 该值的 chunk 视为低相关被过滤；0.0 表示禁用
    RAG_SCORE_THRESHOLD: float = 0.0
    # 是否启用 LLM 检索路由（关闭则走启发式回退，对 mock provider 也安全）
    RAG_USE_PLANNER: bool = True

    @property
    def database_url(self) -> str:
        if self.DATABASE_URL:
            return self.DATABASE_URL
        return (
            f"mysql+pymysql://{self.MYSQL_USER}:{self.MYSQL_PASSWORD}"
            f"@{self.MYSQL_HOST}:{self.MYSQL_PORT}/{self.MYSQL_DB}"
            f"?charset=utf8mb4"
        )

    @property
    def cors_origins_list(self) -> List[str]:
        return [item.strip() for item in self.CORS_ORIGINS.split(",") if item.strip()]

    @property
    def admin_usernames_list(self) -> List[str]:
        return [item.strip() for item in self.ADMIN_USERNAMES.split(",") if item.strip()]

    @property
    def is_production(self) -> bool:
        return self.APP_ENV.strip().lower() in {"prod", "production"}

    @model_validator(mode="after")
    def _check_security_defaults(self):
        if len(self.JWT_SECRET or "") < 32:
            raise ValueError("JWT_SECRET must be at least 32 characters long.")

        if self.is_production and self.APP_DEBUG:
            raise ValueError("APP_DEBUG must be False when APP_ENV=production.")

        if self.is_production and self.AUTO_CREATE_TABLES:
            raise ValueError("AUTO_CREATE_TABLES must be False when APP_ENV=production. Run Alembic migrations instead.")

        if self.is_production and self.JWT_SECRET == _DEFAULT_JWT_SECRET:
            raise ValueError("Set a unique JWT_SECRET before running in production.")

        if self.is_production and (self.MYSQL_PASSWORD or "").strip() in _WEAK_DB_PASSWORDS:
            raise ValueError("Set a non-default MYSQL_PASSWORD before running in production.")

        if self.is_production and str(self.LLM_PROVIDER or "").strip().lower() == "mock":
            raise ValueError("LLM_PROVIDER cannot be 'mock' in production.")

        if self.is_production and str(self.EMBEDDING_PROVIDER or "").strip().lower() == "mock":
            raise ValueError("EMBEDDING_PROVIDER cannot be 'mock' in production.")

        if self.is_production and str(self.LLM_FALLBACK_MODEL or "").strip().lower() == "mock":
            raise ValueError("LLM_FALLBACK_MODEL cannot be 'mock' in production.")

        if self.is_production and str(self.LLM_PROVIDER or "").strip().lower() in {"openai", "qwen", "local"} and not (self.LLM_API_KEY or "").strip():
            raise ValueError("LLM_API_KEY is required for the configured LLM provider in production.")

        if self.is_production and str(self.EMBEDDING_PROVIDER or "").strip().lower() in {"openai", "qwen", "dashscope"} and not (self.EMBEDDING_API_KEY or self.LLM_API_KEY or "").strip():
            raise ValueError("EMBEDDING_API_KEY (or LLM_API_KEY) is required for the configured embedding provider in production.")

        return self


settings = Settings()
